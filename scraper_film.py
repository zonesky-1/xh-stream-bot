# language: Python 3.11, file: scraper_film.py — Film sub Indo gaya LK21
#
# Sumber: gashousegorillas.org (mesin WP asli; skin: iwcsantodomingo.org,
# form search两家 nembak ke sini juga).
#
# Fakta lapangan (bedah 2026-10-09, jangan diubah sembarangan):
# 1. REST API TERBUKA:
#      /wp-json/wp/v2/search?search=<q>&per_page=N
#      /wp-json/wp/v2/posts?search=<q>&page=N   (X-WP-Total = total film)
#      /wp-json/wp/v2/posts?slug=<slug>          (detail: excerpt=sinopsis,
#        featured_media=poster id, categories=genre ids)
#      /wp-json/wp/v2/categories?include=6,9     (nama genre)
#      /wp-json/wp/v2/media/<id>                 (source_url poster)
#    Taxonomy lain: muviyear, muvicountry, muviquality (HD/HDCAM),
#    muvidirector, muvicast. Total film: 5.044+ (live, bukan index lokal).
# 2. content.rendered POST TIDAK berisi player (cuma 580 char) — iframe ada di
#    HTML halaman penuh (GET /<slug>/ — status bisa 500 tapi BODY VALID,
#    tema GMR render player dari post meta):
#      <div id="player-1"><IFRAME SRC="https://morencius.com/embed/<id>">
# 3. Embed morencius = JWPlayer, script di-PACK eval(function(p,a,c,k,e,d))
#    (paker string-subst, base a, k dipisah '|') → depakel manual di Python:
#      links = {"hls3": …, "hls2": <signed>, "hls4": "/stream/<tok>/…/master.m3u8"}
#      jwplayer().setup({sources:[{file: links.hls4||links.hls3||links.hls2}]})
#    → prioritaskan hls4 (relatif → urljoin ke host embed); durasi film penuh
#    (contoh 7165s ≈ 2 jam); kualitas 720p.
# 4. Download: ffmpeg -c copy m3u8 + Referer embed — sama persis pola
#    scraper_nh / scraper_drbest. TANPA login, TANPA proxy.
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx

log = logging.getLogger("film")

API = "https://gashousegorillas.org/wp-json/wp/v2"
PAGE = "https://gashousegorillas.org"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _get(url: str, params: dict | None = None, referer: str | None = None,
         timeout: float = 35) -> httpx.Response:
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    last: Exception | None = None
    for i in range(3):
        try:
            r = httpx.get(url, params=params, headers=h, timeout=timeout,
                          follow_redirects=True, verify=False)
            # halaman film kadang status 500 tapi body valid (tema GMR)
            if r.status_code < 400 or (referer and len(r.text) > 40000):
                return r
            last = RuntimeError(f"HTTP {r.status_code} {url}")
        except Exception as e:
            last = e
        import time as _t
        _t.sleep(1.0 * (i + 1))
    raise last  # type: ignore[misc]


def _strip(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).replace("&hellip;",
                  "…").replace("&nbsp;", " ").replace("&amp;", "&").strip()


def _poster_ids(items: list[dict]) -> dict[int, str]:
    ids = [it.get("featured_media") for it in items if it.get("featured_media")]
    if not ids:
        return {}
    try:
        r = _get(f"{API}/media", params={"include": ",".join(map(str, ids)),
                                         "per_page": 100, "_fields": "id,source_url"})
        return {m["id"]: m.get("source_url", "") for m in r.json()}
    except Exception:
        return {}


def _cat_names(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    try:
        r = _get(f"{API}/categories",
                 params={"include": ",".join(map(str, ids)),
                         "per_page": 100, "_fields": "id,name"})
        return {c["id"]: c["name"] for c in r.json()}
    except Exception:
        return {}


# ── search (live REST; fallback nama genre persis) ────────────────────────
def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    def _run() -> tuple[list[dict], int]:
        params: dict = {"page": page, "per_page": per,
                        "_fields": "id,link,title,slug,excerpt,featured_media,categories"}
        term = q.strip()
        if term:
            params["search"] = term
        r = _get(f"{API}/posts", params=params)
        items_raw = r.json() if r.status_code == 200 else []
        total = int(r.headers.get("X-WP-Total") or 0)
        # fallback: query = nama genre persis (mis. "action") saat 0 hasil
        if term and total == 0:
            try:
                rc = _get(f"{API}/categories",
                          params={"search": term, "_fields": "id,name,slug",
                                  "per_page": 5}).json()
                hit = next((c for c in rc
                            if c["slug"].lower() == term.lower()
                            or c["name"].lower() == term.lower()), None)
                if hit:
                    r = _get(f"{API}/posts",
                             params={"categories": hit["id"], "page": page,
                                     "per_page": per,
                                     "_fields": "id,link,title,slug,excerpt,"
                                                "featured_media,categories"})
                    items_raw = r.json() if r.status_code == 200 else []
                    total = int(r.headers.get("X-WP-Total") or 0)
            except Exception:
                pass
        posters = _poster_ids(items_raw)
        catids: set[int] = set()
        for it in items_raw:
            catids.update(it.get("categories") or [])
        cats = _cat_names(list(catids))
        items = []
        for it in items_raw:
            items.append({
                "title": _strip(it["title"]["rendered"]),
                "url": it["link"],
                "thumb": posters.get(it.get("featured_media"), ""),
                "desc": _strip(it.get("excerpt", {}).get("rendered", ""))[:120],
                "provider": "LK21",
                "genres": ", ".join(cats.get(c, "") for c in
                                    (it.get("categories") or []) if c in cats),
            })
        return items, total
    return _run()


def index_info() -> dict:
    r = _get(f"{API}/posts", params={"per_page": 1, "_fields": "id"})
    return {"count": int(r.headers.get("X-WP-Total") or 0), "mode": "live REST"}


# ── detail: meta REST + iframe server dari HTML penuh ─────────────────────
RE_IFRAME = re.compile(r'<iframe[^>]+src="(https?://[^"]+)"', re.I)
RE_PYEAR = re.compile(r"/year/(\d{4})")
RE_PQUAL = re.compile(r"/quality/([a-z0-9]+)", re.I)


def parse_detail(page_url: str, meta: dict, html: str) -> dict:
    servers = list(dict.fromkeys(RE_IFRAME.findall(html)))
    ys = sorted(set(RE_PYEAR.findall(html)), reverse=True)
    qs = {q.upper() for q in RE_PQUAL.findall(html)}
    ogp = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html) \
        or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html)
    return {
        "title": _strip(meta["title"]["rendered"]),
        "url": page_url,
        "sinopsis": _strip(meta.get("excerpt", {}).get("rendered", ""))[:600],
        "genres": meta.get("genre_names", []),
        "year": ys[0] if ys else "",
        "quality": "/".join(sorted(qs)) or "",
        "poster": (meta.get("poster_url")
                   or (ogp.group(1) if ogp else "")),
        "servers": servers,          # iframe embed (server 1, 2, …)
        "eps": {1: servers[0]} if servers else {},   # film = EP tunggal
        "total": 1,
    }


async def detail(url: str) -> dict:
    def _run() -> dict:
        m = re.search(r"/wp-json/", url)
        slug = url.rstrip("/").split("/")[-1].split("?")[0]
        r = _get(f"{API}/posts", params={"slug": slug,
                                         "_fields": "id,link,title,slug,excerpt,"
                                                    "featured_media,categories"})
        arr = r.json() if r.status_code == 200 else []
        if not arr:
            raise RuntimeError("film nggak ketemu di REST (slug salah?)")
        p = arr[0]
        cats = _cat_names(p.get("categories") or [])
        posters = _poster_ids([p])
        meta = {"title": p["title"], "excerpt": p.get("excerpt", {}),
                "genre_names": [cats.get(c, "") for c in
                                (p.get("categories") or []) if c in cats],
                "poster_url": posters.get(p.get("featured_media"), "")}
        # HTML penuh (status bisa 500 tapi body valid — lihat _get)
        h = _get(p["link"], referer=PAGE)
        d = parse_detail(p["link"], meta, h.text)
        if not d["servers"]:
            raise RuntimeError("halaman film nggak punya player server")
        return d
    return await asyncio.to_thread(_run)


# ── segmen: rotasi farm proxy (CDN acek/vidhide punya token-bucket per-IP
#    super-kecil: ~5 request lalu 404 semua — bedah 2026-10-09). 80 proxy
#    dari .ws_farm_proxies.txt bikin tiap unduhan punya bucket sendiri.
PROXY_FILE = os.path.expanduser("~/xh-bot/.ws_farm_proxies.txt")
_PROXIES: list | None = None
_PROXY_DEAD = False   # sekali 402/quota habis → stop pakai proxy (buang waktu)


def _load_proxies() -> list[str]:
    global _PROXIES
    if _PROXIES is None:
        try:
            with open(PROXY_FILE) as f:
                _PROXIES = [l.strip() for l in f
                            if l.strip().startswith("http")]
        except Exception:
            _PROXIES = []
    return _PROXIES


# ── stream: dispatch per jenis server embed ───────────────────────────────
RE_IFRAME = re.compile(r'<iframe[^>]+src="(https?://[^"]+)"', re.I)
RE_CONFIG = re.compile(r"var config = (\{.*?\});", re.S)

# keluarga juicycodes (barplay/bezplay): payload HARUS di-embed-an Chrome,
# decode di page — lihat juicy_resolve.py (bedah 2026-10-09)
JUICY_HOSTS = ("barplay.xyz", "bezplay.xyz")

RE_EVAL = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\(('(?:[^'\\]|\\.)*'),\s*(\d+),"
    r"\s*(\d+),\s*('(?:[^'\\]|\\.)*')\.split\('\|'\)", re.S)
RE_LINKS = re.compile(r'var links=(\{.*?\});', re.S)


def unpack_packer(p_raw: str, a: int, c: int, k_raw: str) -> str:
    """Depakel eval(function(p,a,c,k,e,d)…) — string-substitution standar."""
    def unesc(s: str) -> str:
        return s.replace("\\'", "'").replace("\\\\", "\\").replace("\\n", "\n")
    p = unesc(p_raw[1:-1])
    words = unesc(k_raw[1:-1]).split("|")
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    for i in range(c - 1, -1, -1):
        if i < len(words) and words[i]:
            n, token = i, ""
            if n == 0:
                token = "0"
            else:
                while n:
                    token = digits[n % a] + token
                    n //= a
            p = re.sub(r"\b" + re.escape(token) + r"\b",
                       lambda _m, w=words[i]: w, p)
    return p


def _vidhide_stream(embed_url: str, html: str) -> str:
    """morencius & keluarga vidhide: JWPlayer packed → depakel python."""
    m = RE_EVAL.search(html)
    if not m:
        raise RuntimeError("packed script nggak ketemu")
    js = unpack_packer(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))
    lm = RE_LINKS.search(js)
    if not lm:
        raise RuntimeError("objek links nggak ketemu setelah depakel")
    links = json.loads(lm.group(1))
    src = links.get("hls4") or links.get("hls3") or links.get("hls2")
    if not src:
        raise RuntimeError("sumber HLS kosong")
    if src.startswith("/"):
        src = urljoin(embed_url, src)
    return src


def parse_embed(embed_html: str, embed_url: str) -> str:
    """legacy — dipakai kalau _pick_vidhide gagal parse."""
    links = _embed_links(embed_html)
    src = links.get("hls4") or links.get("hls3") or links.get("hls2")
    if not src:
        raise RuntimeError("sumber HLS kosong")
    if src.startswith("/"):
        src = urljoin(embed_url, src)
    return src


def _embed_links(embed_html: str) -> dict:
    m = RE_EVAL.search(embed_html)
    if not m:
        raise RuntimeError("script packed player nggak ketemu")
    js = unpack_packer(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))
    lm = RE_LINKS.search(js)
    if not lm:
        raise RuntimeError("objek links nggak ketemu setelah depakel")
    return json.loads(lm.group(1))


AD_HOST_HINTS = ("tiktokcdn", "ad-site", "-ad-", "ads.")


def _pick_vidhide(embed_url: str, embed_html: str) -> str:
    """Pilih sumber HLS vidhide yang BUKAN slot iklan. Terbukti: hls4 bisa
    berisi 100% iklan PNG (tiktokcdn) sementara hls2 = konten asli acek-cdn.
    Validasi: fetch master+index, cek host segmen sample."""
    links = _embed_links(embed_html)
    cands = []
    for k in ("hls4", "hls3", "hls2"):
        c = links.get(k)
        if c:
            cands.append(urljoin(embed_url, c) if c.startswith("/") else c)
    if not cands:
        raise RuntimeError("sumber HLS kosong")
    last: Exception = RuntimeError("nggak ada kandidat")
    for n, c in enumerate(cands):
        try:
            r = _get(c, referer=embed_url)          # master
            rel = [l for l in r.text.splitlines() if l and not l.startswith("#")]
            if not rel:
                last = RuntimeError("master kosong")
                continue
            iu = rel[0] if rel[0].startswith("http") \
                else c.rsplit("/", 1)[0] + "/" + rel[0]
            rx = _get(iu, referer=embed_url)        # index/media
            segs = [l for l in rx.text.splitlines() if l and not l.startswith("#")]
            if not segs:
                last = RuntimeError("index kosong")
                continue
            sample = segs[:30]
            hosts = set()
            for s in sample:
                s_abs = s if s.startswith("http") else iu.rsplit("/", 1)[0] + "/" + s
                mm = re.match(r"https?://([^/]+)", s_abs)
                if mm:
                    hosts.add(mm.group(1))
            if any(any(h in host for h in AD_HOST_HINTS) for host in hosts):
                log.info("vidhide: lewati sumber iklan (%s) → %s",
                         ",".join(sorted(hosts))[:60], c[:60])
                last = RuntimeError("sumber = slot iklan")
                continue
            # cek MAGIC BYTES segmen contoh (hls3 = .woff2 sampah, hls4 = PNG
            # iklan — host saja nggak cukup). Paksa host = host master (decoy
            # subdomain acek suka mati).
            mh = re.match(r"https?://([^/]+)", c).group(1)
            s0 = sample[0] if sample[0].startswith("http") \
                else iu.rsplit("/", 1)[0] + "/" + sample[0]
            s0 = re.sub(r"^https?://[^/]+", "https://" + mh, s0)
            try:
                sr = _get(s0, referer=embed_url)
                head = sr.content[:8]
                ok_magic = (sr.content[0] == 0x47) or (head[4:8] == b"ftyp")
            except Exception as e:
                ok_magic = False
                head = f"ERR {e}"[:40].encode()
            if not ok_magic:
                log.info("vidhide: lewati sumber (magic segmen bukan video: %r)",
                         head[:12])
                last = RuntimeError("segmen bukan video")
                continue
            return c
        except Exception as e:
            last = e
            log.info("vidhide kandidat %s gagal: %s", c[:70], str(e)[:80])
    raise last


async def stream_url(server_url: str) -> str:
    """URL iframe server → master m3u8. Dispatch per keluarga player."""
    def _run() -> str:
        # 1) juicycodes (85% film) — wajib lewat Chrome
        if any(h in server_url for h in JUICY_HOSTS):
            # cek dulu: embed sering MATI ("Video not found") — jangan buang
            # waktu Chrome untuk itu
            try:
                r0 = _get(server_url, referer=PAGE)
                if "Video not found" in r0.text or "not found" in r0.text[:400]:
                    raise RuntimeError("server embed mati (Video not found)")
            except RuntimeError:
                raise
            except Exception:
                pass  # masalah jaringan biar chrome yang coba
            import juicy_resolve
            # validasi: URL juicy bisa basi/403 sesaat → resolve ulang sampai
            # master 200 (max4). Direct python utk zippy = proven cepat; jangan
            # jatuh ke browser (chrome blob utk zippy = SANGAT lambat).
            ref_o = re.match(r"https?://[^/]+", server_url).group(0) + "/"
            last_m = ""
            for k in range(4):
                m3 = juicy_resolve.resolve(server_url)
                last_m = m3
                try:
                    r2 = httpx.get(m3, headers={"User-Agent": UA,
                                                "Referer": ref_o},
                                   timeout=25, verify=False,
                                   follow_redirects=True)
                    if r2.status_code == 200 and "#EXTM3U" in r2.text:
                        return m3
                except Exception:
                    pass
                import time as _t
                _t.sleep(3)
            raise RuntimeError("master juicy nggak sehat: " + last_m[:80])
        # 2) vidhide-family (morencius) — depakel python, tanpa browser;
        #    pilih sumber non-iklan (hls4 bisa = slot iklan tiktokcdn)
        r = _get(server_url, referer=PAGE)
        r.raise_for_status()
        if RE_EVAL.search(r.text):
            return _pick_vidhide(server_url, r.text)
        # 3) playerp2p & lainnya — jujur: belum didukung
        raise RuntimeError(
            "server " + (re.match(r"https?://([^/]+)", server_url)
                         .group(1) if re.match(r"https?://([^/]+)",
                                               server_url) else "?")
            + " belum didukung (coba Server lain / judul lain)")
    return await asyncio.to_thread(_run)


# ── download: SEMUA segmen di python → playlist lokal → ffmpeg remux ──────
# Kenapa bukan ffmpeg langsung nembak URL: stack HTTP ffmpeg di-403 nginx
# vidhide (curl & httpx 200 — bedah 2026-10-09). Jadi python yang narik
# segmen (header referer=embed, terbukti stabil) → ffmpeg cuma ngeremux file.
async def download(master_m3u8: str, out_path: str,
                   referer: str | None = None,
                   progress: Optional[Callable[[int, Optional[int]], None]] = None
                   ) -> tuple[str, bool]:
    """referer = URL iframe embed ASLI (vidhide ngecek di semua level)."""
    import shutil
    import tempfile

    ref = referer or (re.match(r"https?://[^/]+", master_m3u8).group(0) + "/")
    hdrs = {"User-Agent": UA, "Referer": ref,
            "Accept-Language": "en-US,en;q=0.9"}

    def _get(url: str) -> httpx.Response:
        last: Exception | None = None
        for i in range(5):
            try:
                r = httpx.get(url, headers=hdrs, timeout=60, verify=False,
                              follow_redirects=True)
                if r.status_code in (200, 206):
                    return r
                last = RuntimeError(f"HTTP {r.status_code}")
            except Exception as e:
                last = e
            import time as _t
            _t.sleep(2.0 * (i + 1))
        raise last  # type: ignore[misc]

    def _run() -> tuple[str, bool]:
        # 0) coba master via httpx; kalau kena blokir transport (ambar/
        #    bezplay: "Unauthorized: invalid" — fingerprint TLS/H2) → semua
        #    lewat Chrome (browser_fetch)
        via_browser = False
        try:
            master = _get(master_m3u8).text
        except Exception as first_err:
            if "HTTP 401" in str(first_err) or "HTTP 403" in str(first_err):
                # coba direct lagi 2× (403 zippy/morencius = sesaat) — jangan
                # buru-buru ke browser (chrome utk zippy = sangat lambat)
                import time as _t
                got = None
                for k in range(2):
                    _t.sleep(5)
                    try:
                        got = _get(master_m3u8).text
                        break
                    except Exception:
                        continue
                if got is not None:
                    master = got
                else:
                    import browser_fetch
                    master = browser_fetch.fetch_text(referer or master_m3u8,
                                                      master_m3u8)
                    via_browser = True
                    log.info("host nolak non-Chrome — jalur browser utk segmen")
            else:
                raise
        # 1) master → pilih varian terbaik (baris pertama non-#)
        lines = master.splitlines()
        rel = [l for l in lines if l and not l.startswith("#")]
        if rel and "EXT-X-STREAM-INF" in master:
            idx_url = rel[0] if rel[0].startswith("http") \
                else master_m3u8.rsplit("/", 1)[0] + "/" + rel[0]
            if via_browser:
                import browser_fetch
                media = browser_fetch.fetch_text(referer or idx_url, idx_url)
            else:
                media = _get(idx_url).text
        else:
            idx_url = master_m3u8
            media = master
        # 2) daftar segmen (+ EXT-X-MAP bila ada)
        mlines = media.splitlines()
        urls: list[str] = []
        map_url = None
        for i, l in enumerate(mlines):
            if l.startswith("#EXT-X-MAP:"):
                mm = re.search(r'URI="([^"]+)"', l)
                if mm:
                    map_url = mm.group(1)
            elif l and not l.startswith("#"):
                urls.append(l if l.startswith("http")
                            else idx_url.rsplit("/", 1)[0] + "/" + l)
        if not urls:
            raise RuntimeError("playlist nggak punya segmen")
        if any(u.startswith("data:") for u in urls):
            raise RuntimeError("segmen byterange/data URI belum didukung")
        # 2b) BUANG segmen iklan — playlist LK21 nyelipin preroll dari host
        #     lain (mis. tiktokcdn PNG) → kalau ikut, ffmpeg "does not contain
        #     any stream" (bedah 2026-10-09). Simpan host MAYORITAS saja
        #     (konten); iklan cuma segelintir segmen.
        from collections import Counter
        idx_host = re.match(r"https?://([^/]+)", idx_url).group(1)

        def seg_host(u: str) -> str:
            mm = re.match(r"https?://([^/]+)", u)
            return mm.group(1) if mm else idx_host

        cnt = Counter(seg_host(u) for u in urls)
        main_host, main_n = cnt.most_common(1)[0]
        kept = [u for u in urls if seg_host(u) == main_host]
        if len(kept) != len(urls):
            log.info("film: lewati %d segmen iklan/host non-konten "
                     "(simpan host %s: %d/%d)",
                     len(urls) - len(kept), main_host, main_n, len(urls))
        urls = kept
        if not urls:
            raise RuntimeError("semua segmen terfilter — playlist aneh")
        # 3) tarik semua segmen (python — httpx terbukti 200/206;
        #    atau Chrome kalau host nolak non-Chrome)
        tmp = tempfile.mkdtemp(prefix="filmd_")
        paths: list[str] = []

        # acek-cdn: playlist nyelipin subdomain AC random — sebagian MATI
        # (404). Trik: paksa host = host MASTER (sehat) — terbukti 200/200.
        master_host = re.match(r"https?://([^/]+)", master_m3u8).group(1)

        def _force_host(u: str) -> str:
            return re.sub(r"^https?://[^/]+", "https://" + master_host, u)

        def _get_seg(url: str, n: int) -> bytes:
            """Segmen: (1) URL asli, (2) dipaksa ke host master (decoy acek),
            (3) lewat proxy rotasi."""
            global _PROXY_DEAD
            pl = [] if _PROXY_DEAD else _load_proxies()
            attempts: list[tuple[str, str | None]] = [(url, None)]
            fu = _force_host(url)
            if fu != url:
                attempts.append((fu, None))
            if pl:
                attempts.append((fu, pl[(n * 3) % len(pl)]))
            last: Exception | None = None
            for target, px in attempts:
                try:
                    r = httpx.get(target, headers=hdrs, timeout=90,
                                  verify=False, follow_redirects=True,
                                  proxy=px)
                    if r.status_code in (200, 206):
                        return r.content
                    if px and r.status_code in (402, 407):
                        _PROXY_DEAD = True     # kuota farm habis
                        log.warning("farm proxy mati (%s) — dimatikan",
                                    r.status_code)
                    last = RuntimeError(f"HTTP {r.status_code}")
                except Exception as e:
                    if px:
                        _PROXY_DEAD = True     # proxy error koneksi
                    last = e
            raise last  # type: ignore[misc]

        def fetch_one(n_u):
            n, u = n_u
            try:
                data = _get_seg(u, n)
            except Exception as e:
                log.warning("segmen %d gagal setelah retry (%s) — dilewati",
                            n, str(e)[:60])
                return None
            if len(data) < 1024 or data[:15].lower().startswith(b"<!doctype") \
                    or data[:6].lower() == b"<html>":
                log.warning("segmen %d = halaman error — dilewati", n)
                return None
            ext = ".mp4" if data[4:8] == b"ftyp" else ".ts"
            p = os.path.join(tmp, f"seg{n:05d}{ext}")
            with open(p, "wb") as f:
                f.write(data)
            return p

        # 4 thread paralel (urutan via executor.map) — serial cuma ~0.75MB/s,
        # film 2GB ≈ 40 menit; paralel ≈ 10-12 menit
        from concurrent.futures import ThreadPoolExecutor
        import threading
        total = len(urls) + (1 if map_url else 0)
        done = 0
        _lk = threading.Lock()

        def bump():
            nonlocal done
            with _lk:
                done += 1
                d = done
            if progress:
                progress(d, total)

        if via_browser:
            # jalur Chrome: page fetch → blob → download native ke disk
            import browser_fetch
            files: dict[str, str] = {}
            if map_url:
                files["init.mp4"] = map_url
            for n, u in enumerate(urls, start=1):
                files[f"seg{n:05d}.bin"] = u
            bf_errs = browser_fetch.download_files(
                referer or master_m3u8, files, tmp)
            if len(bf_errs) > max(3, len(files) * 0.10):
                raise RuntimeError(
                    "segmen browser gagal terlalu banyak: "
                    + str(bf_errs)[:250])
            if bf_errs:
                log.info("film(browser): %d segmen dilewati", len(bf_errs))
            if map_url:
                paths.append(os.path.join(tmp, "init.mp4"))
            for n in range(1, len(urls) + 1):
                paths.append(os.path.join(tmp, f"seg{n:05d}.bin"))
            for _ in range(total):
                bump()
        else:
            # acek/vidhide: token segmen EXPIRE (~1 menit / ~10-15 request
            # lalu 404 semua — bedah 2026-10-09). Unduh per-chunk; kalau
            # gagal menumpuk → REFRESH index (token segar) + ulangi gagal.
            bumped: set[int] = set()

            def bump_n(n: int):
                if n in bumped:
                    return
                bumped.add(n)
                bump()

            def refresh_urls() -> None:
                nonlocal urls
                if via_browser:
                    import browser_fetch
                    txt = browser_fetch.fetch_text(referer or idx_url, idx_url)
                else:
                    # NB: _get lokal download() — header Referer sudah bawaan
                    txt = _get(idx_url).text
                segs2 = []
                for l in txt.splitlines():
                    if l and not l.startswith("#"):
                        segs2.append(l if l.startswith("http")
                                     else idx_url.rsplit("/", 1)[0] + "/" + l)
                segs2 = [s for s in segs2 if seg_host(s) == main_host]
                if len(segs2) == len(urls):
                    urls[:] = segs2
                    log.info("film: index di-refresh (token segmen segar)")
                else:
                    raise RuntimeError("index refresh: jumlah segmen berubah")

            got_map: dict[int, str] = {}

            def run_chunk(nums: list[int]) -> list[int]:
                fails: list[int] = []
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futs = [(n, ex.submit(fetch_one, (n, urls[n - 1])))
                            for n in nums]
                    for n, f in futs:
                        p = f.result()
                        if p:
                            got_map[n] = p
                        else:
                            fails.append(n)
                        bump_n(n)
                return fails

            if map_url:
                mp = fetch_one((0, map_url))
                if mp:
                    os.rename(mp, os.path.join(tmp, "init.mp4"))
                    paths.append(os.path.join(tmp, "init.mp4"))
                bump_n(0)
            # Strategi token acek: budget ~10 request/index sebelum expire.
            # Refresh PRE-EMPTIF tiap 8 segmen (1 index + 8 seg = 9 req,
            # di bawah budget) → hemat roundtrip gagal-retry yang mahal.
            CHUNK = 8
            refresh_budget = 120
            nums_all = list(range(1, len(urls) + 1))
            i = 0
            while i < len(nums_all):
                if i > 0 and refresh_budget > 0:
                    try:
                        refresh_urls()
                        refresh_budget -= 1
                    except Exception as e:
                        log.warning("refresh index gagal: %s", str(e)[:80])
                        refresh_budget -= 1
                chunk = nums_all[i:i + CHUNK]
                fails = run_chunk(chunk)
                tries = 0
                while fails and tries < 3:
                    # token acek expire cepat (~10-15 request) — refresh agresif
                    if len(fails) >= 3 and refresh_budget > 0:
                        try:
                            refresh_urls()
                            refresh_budget -= 1
                        except Exception as e:
                            log.warning("refresh index gagal: %s",
                                        str(e)[:80])
                            refresh_budget -= 1
                    fails = run_chunk(fails)
                    tries += 1
                i += CHUNK
            paths += [got_map[n] for n in sorted(got_map)]
        if not paths:
            raise RuntimeError("semua segmen gagal diunduh")
        lost = total - len(paths)
        if lost > max(3, total * 0.10):
            raise RuntimeError(
                f"segmen hilang terlalu banyak ({lost}/{total}) — "
                f"CDN kemungkinan lagi nge-blok")
        if lost:
            log.info("film: %d/%d segmen dilewati (CDN flaky) — lanjut",
                     lost, total)
        # 4) playlist lokal
        local_pl = os.path.join(tmp, "local.m3u8")
        head = [l for l in mlines if l.startswith("#") and
                not l.startswith(("#EXT-X-MAP", "#EXT-X-KEY"))]
        with open(local_pl, "w") as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:10\n"
                    "#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
            for p in paths:
                f.write("#EXTINF:10.0,\n" + p + "\n")
            f.write("#EXT-X-ENDLIST\n")
        # 5) remux lokal (tanpa jaringan sama sekali)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", local_pl,
               "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        ok = p.returncode == 0 and os.path.isfile(out_path) \
            and os.path.getsize(out_path) > 0
        shutil.rmtree(tmp, ignore_errors=True)
        if not ok:
            raise RuntimeError("ffmpeg remux gagal: " + (p.stderr or "")[:240])
        sz = os.path.getsize(out_path)
        if progress:
            progress(sz, sz)
        log.info("film unduh: %s %.1f MB", os.path.basename(out_path),
                 sz / 1048576)
        return out_path, False
    return await asyncio.to_thread(_run)


# ── CLI ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio as _a
    import sys as _s
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _main():
        cmd = _s.argv[1] if len(_s.argv) > 1 else "help"
        if cmd == "search":
            items, total = search(" ".join(_s.argv[2:]), 1)
            print(f"total={total}")
            for it in items:
                print(" ", it["title"], "|", it["genres"], "|", it["url"])
        elif cmd == "info":
            print(index_info())
        elif cmd == "detail":
            d = await detail(_s.argv[2])
            print(json.dumps({k: v for k, v in d.items() if k != "sinopsis"},
                             ensure_ascii=False, indent=1)[:900])
            print("sinopsis:", d["sinopsis"][:200])
        elif cmd == "stream":
            print(await stream_url(_s.argv[2]))
        else:
            print("usage: search|info|detail|stream")

    _a.run(_main())
