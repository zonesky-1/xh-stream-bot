"""Scraper film layarkaca21.dev — film/series bersih sub Indo.

Alur:
  search(q)      → REST wp/v2/posts (27k katalog film mainstream)
  detail(link)   → judul, tahun, poster, genre, embed puterin
  resolve(emb)   → AES-256-GCM decode config → HLS m3u8
  fetch_subs()   → OpenSubtitles legacy REST → gzip → .srt Indonesia
  download()     → segmen python → remux mp4 → burn sub ffmpeg

Kontrak sama seperti scraper_film (dipakai bot.py).
"""
import base64, gzip, json, os, re, socket, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import httpx

# VPS tanpa route IPv6 — DNS balikin AAAA dulu → paksa semua resolusi IPv4
_orig_gai = socket.getaddrinfo


def _gai_v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_gai(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _gai_v4

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

SITE = "https://layarkaca21.dev"
API = SITE + "/wp-json/wp/v2/posts"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _c(referer=SITE):
    return httpx.Client(headers={"User-Agent": UA, "Referer": referer},
                        timeout=30, verify=False, follow_redirects=True)


def _get(url, referer=SITE, timeout=30):
    last = None
    for _ in range(3):
        try:
            r = httpx.get(url, headers={"User-Agent": UA, "Referer": referer},
                          timeout=timeout, verify=False, follow_redirects=True)
            if r.status_code == 200:
                return r
            last = Exception(f"HTTP {r.status_code} {url[:80]}")
        except Exception as e:
            last = e
        time.sleep(1.2)
    raise last


# ── filter arsip (genre / tahun / negara) ────────────────────────────────
GENRE_ALIAS = {
    "drama": "drama", "aksi": "aksi", "action": "aksi", "thriller": "aksi",
    "komedi": "komedi", "comedy": "komedi", "lucu": "komedi",
    "horror": "kengerian", "hantu": "kengerian", "kengerian": "kengerian",
    "seru": "cerita-seru", "cerita seru": "cerita-seru",
    "kriminal": "kejahatan", "crime": "kejahatan", "kejahatan": "kejahatan",
    "romance": "percintaan", "cinta": "percintaan", "percintaan": "percintaan",
    "petualangan": "petualangan", "adventure": "petualangan",
    "scifi": "cerita-fiksi", "sci-fi": "cerita-fiksi", "fiksi ilmiah": "cerita-fiksi",
    "fantasi": "fantasi", "fantasy": "fantasi",
    "keluarga": "keluarga", "family": "keluarga",
    "animasi": "animasi", "animation": "animasi", "anime": "animasi",
    "sejarah": "sejarah", "history": "sejarah",
    "dokumenter": "dokumenter", "documentary": "dokumenter", "dokumentari": "dokumenter",
    "misteri": "misteri", "mystery": "misteri",
}
COUNTRY_ALIAS = {
    "amerika": "united-states-of-america", "usa": "united-states-of-america",
    "us": "united-states-of-america", "amerika serikat": "united-states-of-america",
    "inggris": "united-kingdom", "uk": "united-kingdom",
    "jepang": "japan", "japan": "japan",
    "india": "india",
    "prancis": "france", "perancis": "france", "france": "france",
    "kanada": "canada", "canada": "canada",
    "china": "china", "cina": "china", "tiongkok": "china",
    "korea": "south-korea", "korea selatan": "south-korea",
    "jerman": "germany", "germany": "germany",
    "hongkong": "hong-kong", "hong kong": "hong-kong",
    "spanyol": "spain", "spain": "spain",
    "australia": "australia", "italia": "italy", "italy": "italy",
    "thailand": "thailand",
}

_FILT_RE = re.compile(
    r"(?:genre\s*:\s*|negara\s*:\s*|country\s*:\s*|tahun\s*:\s*|thn\s*:\s*|year\s*:\s*)\S+",
    re.I)


def parse_query(q):
    """Deteksi filter arsip di query.
    → {"kind": "genre|year|country", "slug": ..., "label": ..., "text": sisa}
    atau {"kind": None, "text": q} kalau murni search."""
    q = (q or "").strip()
    kind = slug = None
    m = re.search(r"genre\s*:\s*([^\s]+(?:\s[^\s]+)?)", q, re.I)
    if m:
        kind, slug = "genre", GENRE_ALIAS.get(m.group(1).strip().lower(),
                                             m.group(1).strip().lower())
    if not kind:
        m = re.search(r"(?:negara|country)\s*:\s*([^\s]+(?:\s[^\s]+)?)", q, re.I)
        if m:
            key = m.group(1).strip().lower()
            kind, slug = "country", COUNTRY_ALIAS.get(key, key)
    if not kind:
        m = re.search(r"(?:tahun|thn|year)\s*:\s*(\d{4})", q, re.I)
        if not m:
            m = re.fullmatch(r".*?(19\d{2}|20\d{2})", q)   # "drama 2024" murni
        if m and re.fullmatch(r"\d{4}", m.group(1)):
            kind, slug = "year", m.group(1)
    text = _FILT_RE.sub("", q).strip()
    if not kind:
        return {"kind": None, "text": q}
    label = {"genre": f"Genre {slug}", "year": f"Tahun {slug}",
             "country": f"Negara {slug}"}[kind]
    return {"kind": kind, "slug": slug, "label": label, "text": text}


def _grid(html):
    """Parser kartu film (a.lk-kartu) → items."""
    items = []
    for m in re.finditer(
            r'<a class="lk-kartu" href="(https://layarkaca21\.dev/[^"]+)"'
            r'\s+title="([^"]+)"', html):
        url, title = m.group(1), m.group(2)
        title = (title.replace("&#8217;", "'").replace("&amp;", "&")
                 .replace("&#038;", "&").strip())
        items.append({"title": title, "url": url,
                      "slug": url.rstrip("/").split("/")[-1], "year": ""})
    return items


_MAXP_CACHE: dict = {}             # (kind, slug) → halaman valid terakhir


def _page_ok(kind, slug, n):
    try:
        html = _get(f"{SITE}/{kind}/{slug}/page/{n}/").text
        return bool(_grid(html))
    except Exception:
        return False


def _maxpage(kind, slug):
    """Pagination WP nunjuk halaman GLOBAL (misleading) → cari batas asli."""
    key = (kind, slug)
    if key in _MAXP_CACHE:
        return _MAXP_CACHE[key]
    hi = 1                          # eksponen: 1,2,4,8… sampai mentok
    while hi <= 8192 and _page_ok(kind, slug, hi):
        hi *= 2
    lo, hi = 1, hi
    while lo < hi:                  # binary search batas valid
        mid = (lo + hi + 1) // 2
        if _page_ok(kind, slug, mid):
            lo = mid
        else:
            hi = mid - 1
    _MAXP_CACHE[key] = max(1, lo)
    return _MAXP_CACHE[key]


def _archive(kind, slug, page=1):
    """Arsip LK21 (genre/tahun/negara) → (items, total)."""
    base = f"{SITE}/{kind}/{slug}/"
    url = base if page == 1 else f"{base}page/{page}/"
    html = _get(url).text
    items = _grid(html)
    mp = _maxpage(kind, slug)
    total = (mp - 1) * 24 + len(_grid(
        _get(f"{base}page/{mp}/").text)) if mp > 1 else len(items)
    return items, total


# ── search ────────────────────────────────────────────────────────────────
def search(q="", page=1):
    """Cari film. → (items, total). items: {title, year, url, slug}
    Query mendukung filter arsip: genre:aksi • tahun:2024 • negara:jepang."""
    fq = parse_query(q)
    if fq.get("kind"):
        return _archive(fq["kind"], fq["slug"], page)
    c = _c()
    if q:
        params = {"search": q, "per_page": 20, "page": page, "_fields": "id,title,link,slug"}
        r = c.get(API, params=params)
    else:
        r = c.get(API, params={"per_page": 20, "page": page, "_fields": "id,title,link,slug"})
    r.raise_for_status()
    total = int(r.headers.get("X-WP-Total", 0))
    items = []
    for p in r.json():
        title = re.sub(r"\s+", " ", p["title"]["rendered"]).strip()
        items.append({"title": title, "url": p["link"], "slug": p["slug"], "year": ""})
    return items, total


# ── detail ────────────────────────────────────────────────────────────────
def detail(url):
    """Detail film: {title, year, poster, synopsis, genres, embed}"""
    html = _get(url).text

    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html)
    poster = m.group(1) if m else ""

    m = re.search(r"<title>Nonton Film (.+?) Sub Indo", html)
    title = m.group(1).strip() if m else ""
    m = re.search(r"\((\d{4})\)", title)
    year = m.group(1) if m else ""
    title_clean = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()

    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
    synop = m.group(1).strip() if m else ""

    # embed player puterin/putarin (dua host, protokol sama)
    m = re.search(r'(https://put(?:e|a)rin\.biz/e/[A-Za-z0-9]+)', html)
    embed = m.group(1) if m else ""

    genres = []
    m = re.search(r"bergenre (.*?)\s*(?:produksi|, produksi|$)", synop)
    if m:
        genres = [g.strip(" .…") for g in m.group(1).split(",") if g.strip(" .…")][:6]
        genres = [g for g in genres if g.lower() != "produksi"]

    return {"title": title_clean or "Film", "year": year, "poster": poster,
            "synopsis": synop, "genres": genres, "embed": embed, "url": url}


# ── resolve stream (puterin AES-GCM) ──────────────────────────────────────
def resolve_stream(embed):
    """Embed puterin → HLS m3u8 URL (config didecrypt AES-256-GCM)."""
    if AESGCM is None:
        raise RuntimeError("cryptography belum terpasang")
    c = _c(embed)
    origin = "/".join(embed.split("/")[:3])
    html = c.get(embed).text
    m = re.search(r"window\.__PX=(\{.*?\});", html, re.S)
    if not m:
        m = re.search(r"__PX=(\{[^;]+\})", html)
    px = json.loads(m.group(1))
    key_hex = c.get(f"{origin}/api/pk?n={px['n']}",
                    headers={"Referer": embed}).text.strip()
    raw = base64.b64decode(px["d"])
    cfg = json.loads(AESGCM(bytes.fromhex(key_hex)).decrypt(raw[:12], raw[12:], None))
    hls = cfg["file"]
    if hls.startswith("/"):
        hls = origin + hls
    return hls, cfg.get("image", "")


# ── subtitle Indonesia ────────────────────────────────────────────────────
def fetch_subs(title, year="", out_dir=None, timeout=40):
    """OpenSubtitles legacy REST → .srt Indonesia. → path atau None."""
    # REST ini redirect query berhuruf KAPITAL ke host aneh → wajib lowercase
    q = quote(title.lower().replace(" ", "+"))
    url = f"https://rest.opensubtitles.org/search/query-{q}/sublanguageid-ind"
    data = None
    for attempt in range(4):          # DNS resolved kadang flaky → retry
        for path in ("httpx", "curl"):
            try:
                if path == "httpx":
                    r = _get(url, referer="https://www.opensubtitles.org/",
                             timeout=timeout)
                    data = r.json()
                else:
                    p = subprocess.run(
                        ["curl", "-4", "-sfL", "--max-time", str(timeout), url],
                        capture_output=True)
                    if p.returncode == 0 and p.stdout:
                        data = json.loads(p.stdout.decode("utf-8", "ignore"))
                if data:
                    break
            except Exception:
                data = None
        if data:
            break
        time.sleep(2 + attempt * 2)
    if not data:
        return None

    name_l = title.lower()
    cands = [x for x in data if str(x.get("MovieName", "")).lower() == name_l]
    if not cands:
        cands = [x for x in data if name_l in str(x.get("MovieName", "")).lower()]
    if not cands:
        return None
    if year:
        exact = [x for x in cands if str(x.get("MovieYear", "")) == str(year)]
        cands = exact or cands
    hit = cands[0]

    dl = hit.get("SubDownloadLink", "")
    if not dl:
        return None
    raw = None
    try:
        rb = _get(dl, referer="https://www.opensubtitles.org/", timeout=timeout)
        raw = rb.content
    except Exception:
        try:
            p = subprocess.run(
                ["curl", "-4", "-sfL", "--max-time", str(timeout), dl],
                capture_output=True)
            if p.returncode == 0:
                raw = p.stdout
        except Exception:
            return None
    if not raw:
        return None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            return None
    txt = raw.decode("utf-8", "ignore")
    if "-->" not in txt:
        return None
    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="lk21sub_")
    path = os.path.join(out_dir, "sub.srt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt.lstrip("\ufeff"))
    return path


# ── download ──────────────────────────────────────────────────────────────
def download(url, out_path=None, with_sub=True, progress=None):
    """Download film penuh: segmen → remux → burn sub Indonesia.
    → (path, dur_detik)"""
    d = detail(url)
    if not d["embed"]:
        raise RuntimeError("player tidak ditemukan")
    hls, _ = resolve_stream(d["embed"])
    c = _c(d["embed"])
    pl = c.get(hls).text
    segs = [("https:" + l.strip()) if l.strip().startswith("//") else l.strip()
            for l in pl.splitlines()
            if l and not l.startswith("#")
            and (l.strip().startswith("//") or "http" in l)]
    if not segs:
        raise RuntimeError("playlist kosong")

    workdir = tempfile.mkdtemp(prefix="lk21_")

    def fetch(i_s):
        i, s = i_s
        for attempt in range(3):
            try:
                r = c.get(s)
                if r.status_code == 200 and len(r.content) > 1000:
                    p = os.path.join(workdir, f"seg{i:05d}.ts")
                    with open(p, "wb") as f:
                        f.write(r.content)
                    return True
            except Exception:
                pass
            time.sleep(0.8 + attempt)
        return False

    total = len(segs)
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for ok in ex.map(fetch, enumerate(segs)):
            done += 1
            if progress and done % 25 == 0:
                try:
                    progress(done, total)
                except Exception:
                    pass
    files = sorted(f for f in os.listdir(workdir) if f.endswith(".ts"))
    if len(files) < 3:
        raise RuntimeError(f"segmen gagal ({len(files)}/{total})")

    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        for fn in files:
            f.write(f"file '{fn}'\n")
    raw_mp4 = os.path.join(workdir, "raw.mp4")
    p = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", "-movflags", "+faststart", raw_mp4],
        cwd=workdir, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("remux gagal: " + (p.stderr or "")[:200])

    if out_path is None:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", d["title"])[:40]
        out_path = f"/tmp/lk21_{slug}_{int(time.time())}.mp4"

    srt = None
    if with_sub:
        srt = fetch_subs(d["title"], d["year"], out_dir=workdir)

    if srt:
        style = "FontSize=17,Outline=2,MarginV=28"
        p = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_mp4,
             "-vf", f"subtitles=sub.srt:force_style='{style}'",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
             "-c:a", "copy", "-movflags", "+faststart", out_path],
            cwd=workdir, capture_output=True, text=True)
        if p.returncode != 0:
            p = subprocess.run(
                ["ffmpeg", "-y", "-i", raw_mp4, "-c", "copy",
                 "-movflags", "+faststart", out_path],
                cwd=workdir, capture_output=True, text=True)
            srt = None
    if not srt:
        os.replace(raw_mp4, out_path)

    dur = 0
    try:
        q = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out_path], capture_output=True, text=True)
        dur = int(float(q.stdout.strip() or 0))
    except Exception:
        pass
    return out_path, dur, bool(srt)
