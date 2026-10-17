"""Scraper SERIES — sparkott.com (WGFILM21 theme, kategori 'series' 629 judul).

Rantai (sudah E2E):
1. REST WP: /wp-json/wp/v2/posts?search=Q&categories=<series_id>
2. detail: halaman /tv/<slug>/ → link EP dari div.gmr-listseries (/eps/<slug>/)
3. stream: halaman /eps/<url>/ → data-id → POST admin-ajax.php
   action=muvipro_player_content&tab=p1&post_id=<id> → iframe minochinos.com
4. minochinos /embed/<id> → packed JS (radix 36) → unpack →
   master.m3u8 (acek-cdn/dramiyos-cdn hls2, token t=) + .vtt sub Indo
5. media playlist → segmen .ts (token fresh; refresh kalau >10 menit)
6. remux -c copy → burn sub vtt (ffmpeg subtitles=) → mp4

Jebakan:
- unpack pakai regex p.a.c.k.e.r: }('payload',radix,count,'w1|w2'.split('|'))
- URL segmen HARUS diambil utuh dari baris playlist (jangan regex potong)
- host CDN di playlist lowercase — request apa adanya (200 OK)
- token t= sekali-pakai-ish: jangan cache segmen URL lama
"""
import os
import re
import subprocess
import time
import warnings
from urllib.parse import urljoin

import httpx
from curl_cffi import requests as cr

warnings.filterwarnings("ignore")

SITE = "https://sparkott.com"
AJAX = SITE + "/wp-admin/admin-ajax.php"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _c():
    return httpx.Client(
        headers={"User-Agent": UA}, timeout=30, verify=False,
        follow_redirects=True)


# ── search: CPT /tv/ via REST (964 series) ───────────────────────────────
def search(q="", page=1):
    """→ (items, total). items: {title, url, slug, id}"""
    c = _c()
    params = {"search": q, "per_page": 20, "page": page,
              "_fields": "id,title,link,slug"}
    r = c.get(SITE + "/wp-json/wp/v2/tv", params=params)
    r.raise_for_status()
    total = int(r.headers.get("X-WP-Total", 0))
    items = []
    for p in r.json():
        title = re.sub(r"\s+", " ", p["title"]["rendered"]).strip()
        title = re.sub(r"<[^>]+>", "", title).strip()
        items.append({"title": title, "url": p["link"], "slug": p["slug"],
                      "id": p["id"], "year": ""})
    return items, total


# ── detail: daftar episode ────────────────────────────────────────────────
def detail(url, tv_id=None):
    """→ {title, eps: [(label, eps_url), ...]}
    Sumber utama: REST episode?parent=<tv_id> (semua episode, diurut)."""
    c = _c()
    if tv_id:
        # NOTE: param 'parent' gak difilter WP → filter manual per slug tv
        slug = url.rstrip("/").split("/")[-1].split("-season")[0]
        qk = slug.replace("-", " ")[:40]
        eps, pg = [], 1
        while pg <= 6:
            r = c.get(SITE + "/wp-json/wp/v2/episode",
                      params={"search": qk, "per_page": 100, "page": pg,
                              "_fields": "title,link"}).json()
            if not isinstance(r, list) or not r:
                break
            cocok = 0
            for p in r:
                if f"/eps/{slug}-" not in p["link"]:
                    continue
                cocok += 1
                lbl = re.sub(r"<[^>]+>", "", p["title"]["rendered"]).strip()
                m = re.search(r"(?:Season\s*(\d+).*?[Ee]p(?:isode)?\s*(\d+)"
                              r"|[Ee]p(?:isode)?\s*(\d+))", lbl)
                if m:
                    lbl = (f"S{m.group(1)}E{m.group(2)}" if m.group(1)
                           else f"EP{m.group(3)}")
                eps.append((lbl, p["link"]))
            kosong = 0 if cocok else kosong + 1
            if len(r) < 100:
                break
            pg += 1
        if eps:
            og = c.get(url).text
            mo = re.search(r'<meta property="og:title" content="([^"]+)"', og)
            title = (mo.group(1) if mo else url.rstrip("/").split("/")[-1])
            title = re.sub(r"\s*-\s*sparkott\.com\s*$", "", title)
            return {"title": title, "eps": eps}
    t = c.get(url).text
    og = re.search(r'<meta property="og:title" content="([^"]+)"', t)
    title = (og.group(1) if og else "tanpa judul")
    title = re.sub(r"\s*-\s*sparkott\.com\s*$", "", title)
    eps = []
    for m in re.finditer(
            r'href="(https://sparkott\.com/eps/[^"]+)"[^>]*title="[^"]*"\s*'
            r'>\s*(S\d+\s*Eps\d+)</a>', t):
        eps.append((m.group(2).replace(" ", ""), m.group(1)))
    if not eps:      # fallback: kumpulin semua link /eps/
        seen = set()
        for m in re.finditer(r'href="(https://sparkott\.com/eps/[^"]+)"', t):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                eps.append((f"EP{len(eps) + 1}", m.group(1)))
    return {"title": title, "eps": eps}


def _unbase(x, b):
    r = 0
    for ch in x:
        r = r * b + _DIGITS.index(ch)
    return r


def _unpack_minochinos(html):
    """Decode packed JS (p.a.c.k.e.r radix 36) → cari m3u8 + vtt."""
    i = html.find("eval(function(p,a,c,k,e,d)")
    if i < 0:
        return None
    raw = html[i:html.find("</script>", i)]
    # boundary ',<radix>,<count>,' unik → greedy aman walau payload berisi quote
    m = re.search(r"\}\('(.*)',\s*(\d+),\s*(\d+),\s*'(.*)'\.split",
                  raw, re.S)
    if not m:
        return None
    payload, radix, words = (m.group(1), int(m.group(2)),
                             m.group(4).split("|"))

    def repl(mm):
        # packer asli: if (k[c]) replace — tabel kosong = KATA ASLI dipertahankan
        w = mm.group(0)
        try:
            k = _unbase(w, radix)
            if k < len(words) and words[k]:
                return words[k]
            return w
        except ValueError:
            return w

    out = re.sub(r"\b[0-9a-zA-Z]+\b", repl, payload)
    m3u8 = re.search(r'(https?://[^"\'\s\\]+\.m3u8[^"\'\s\\]*)', out)
    vtt = re.search(r'(https?://[^"\'\s\\]+\.vtt[^"\'\s\\]*)', out)
    if not m3u8:
        return None
    return {"m3u8": m3u8.group(1), "vtt": vtt.group(1) if vtt else None}


def stream(eps_url):
    """Halaman EP → {m3u8, vtt}."""
    c = _c()
    t = c.get(eps_url).text
    m = re.search(r'muvipro_player_content_id[^>]*data-id="(\d+)"', t)
    if not m:
        raise RuntimeError("player id gak ketemu")
    pl = c.post(AJAX, data={"action": "muvipro_player_content", "tab": "p1",
                            "post_id": m.group(1)},
                headers={"X-Requested-With": "XMLHttpRequest",
                         "Referer": eps_url}).text
    emb = re.search(r'SRC="(https://minochinos\.com/embed/[A-Za-z0-9]+)"',
                    pl, re.I)
    if not emb:
        raise RuntimeError("embed minochinos gak ketemu")
    # payload packed bervariasi per request; master m3u8 kadang 403
    # (token format aneh) → coba sampai master valid (#EXTM3U)
    s = cr.Session(impersonate="chrome")
    hc = _c()
    d = None
    for _ in range(5):
        t2 = s.get(emb.group(1), timeout=30).text
        cand = _unpack_minochinos(t2)
        if not cand:
            time.sleep(1.2)
            continue
        try:
            r = s.get(cand["m3u8"], timeout=30)
            if r.status_code == 200 and "#EXTM3U" in r.text[:64]:
                d = cand
                break
        except Exception:
            pass
            time.sleep(1.2)
    if not d:
        raise RuntimeError("unpack player gagal (5x)")
    return d


def _seg_list(m3u8, max_usia=600):
    """Master → media playlist → segmen (token segar)."""
    s = cr.Session(impersonate="chrome")
    rr = s.get(m3u8, timeout=30)
    if rr.status_code != 200:
        raise RuntimeError(f"master m3u8 HTTP {rr.status_code}")
    plst = rr.text
    if "#EXT-X-STREAM-INF" in plst:          # master → media
        media = re.findall(r"(\S+\.m3u8\S*)", plst)
        if not media:
            raise RuntimeError("media playlist gak ketemu")
        u2 = urljoin(m3u8, media[0])
        rr2 = s.get(u2, timeout=30)
        if rr2.status_code != 200 or "#EXTM3U" not in rr2.text[:64]:
            raise RuntimeError("media playlist bukan m3u8 valid")
        return u2, [urljoin(u2, l) for l in rr2.text.splitlines()
                    if l.strip() and not l.startswith("#")]
    if "#EXTM3U" not in plst[:64]:
        raise RuntimeError("playlist bukan m3u8 valid")
    return m3u8, [urljoin(m3u8, l) for l in plst.splitlines()
                  if l.strip() and not l.startswith("#")]


def download(eps_url, out_path=None, with_sub=True, progress=None,
             max_segs=None):
    """Download 1 episode: segmen → remux → burn sub vtt → mp4.
    → (path, dur_detik, sub_burn)"""
    d = stream(eps_url)
    media_url, segs = _seg_list(d["m3u8"])
    if not segs:
        raise RuntimeError("segmen kosong")
    if max_segs:
        segs = segs[:max_segs]
    n = len(segs)
    jud = re.search(r"/eps/([^/]+)/", eps_url).group(1)[:60]
    if not out_path:
        safe = re.sub(r"[^a-z0-9]+", "-", jud.lower()).strip("-")
        out_path = f"series-{safe}.ts"
    raw = out_path + ".raw.ts"
    s = _c()          # httpx (curl_cffi kena 403 di CDN acek/dramiyos)
    s.headers.update({"Referer": "https://minochinos.com/"})
    t0 = time.time()
    state = {"last": 0.0}
    with open(raw, "wb") as f:
        for i, u in enumerate(segs, 1):
            for att in (1, 2, 3, 4):
                try:
                    r = s.get(u, timeout=60)
                    if r.status_code != 200 or len(r.content) < 200:
                        # 403 → token/CDN: retry + segmen URL segar utuh
                        raise RuntimeError(f"segmen {r.status_code}")
                    f.write(r.content)
                    break
                except Exception:
                    if att == 4:
                        raise
                    time.sleep(2 + att * 2)
            if progress and time.time() - state["last"] > 4:
                state["last"] = time.time()
                try:
                    progress(i, n)
                except Exception:
                    pass
    # remux
    remuxed = out_path + ".remux.mp4"
    rc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
         "-c", "copy", "-bsf:a", "aac_adtstoasc", remuxed],
        capture_output=True, timeout=900)
    if rc.returncode != 0 or not os.path.isfile(remuxed):
        raise RuntimeError("remux gagal: " + rc.stderr.decode()[:160])
    out = remuxed
    burned = False
    if with_sub and d.get("vtt"):
        try:
            vr = cr.Session(impersonate="chrome").get(d["vtt"], timeout=30)
            if vr.status_code == 200 and b"WEBVTT" in vr.content[:64]:
                subp = out_path + ".sub.vtt"
                open(subp, "wb").write(vr.content)
                sub_esc = subp.replace("\\", "\\\\").replace(":", "\\:")
                burned_file = out_path + ".sub.mp4"
                rc = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", remuxed,
                     "-vf", f"subtitles='{sub_esc}':"
                            "force_style='FontSize=16,Outline=2'",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
                     "-c:a", "copy", "-movflags", "+faststart", burned_file],
                    capture_output=True, timeout=7200)
                if rc.returncode == 0 and os.path.isfile(burned_file) \
                        and os.path.getsize(burned_file) > 0:
                    out = burned_file
                    burned = True
                os.remove(subp)
        except Exception:
            pass
    # durasi
    fp = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", out], capture_output=True, text=True, timeout=60)
    dur = 0.0
    try:
        dur = float(fp.stdout.strip())
    except ValueError:
        pass
    # bersihin sisa
    for p in (raw, remuxed):
        if p != out and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
    if not out_path.endswith(".mp4"):
        final = out_path + ".mp4"
        os.replace(out, final)
        out = final
    return out, dur, burned


if __name__ == "__main__":
    items, tot = search("", 1)
    print(f"{len(items)} series | total {tot}")
    for it in items[:5]:
        print(" •", it["title"][:60])
    d = detail(items[0]["url"])
    print("\n", d["title"][:60], "|", len(d["eps"]), "episode")
    for lbl, u in d["eps"][:4]:
        print("   ", lbl, u[-40:])
