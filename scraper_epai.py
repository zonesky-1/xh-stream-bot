"""Scraper EPORNER — kategori AI (video AI-generated).

Sumber: https://www.eporner.com/cat/ai/ (~6.600+ video "AI Generated").
- search kosong = kategori AI terbaru; search teks = eporner relevance search.
- download via /dload/<ID>/<res>/<nama>.mp4 → wajib Referer halaman video.
- gvideo.eporner.com 403 → JANGAN dipakai; /dload/ yang jalan (206/200).
- pagination /cat/ai/<N>/ dan /<N>/sort/relevance/<q>/.
"""
import re
import time
import warnings
from urllib.parse import quote
from curl_cffi import requests as cr

warnings.filterwarnings("ignore")

SITE = "https://www.eporner.com"
PER = 40                          # perkiraan video/halaman utama
MAX_BYTES = 45 * 1024 * 1024      # batas aman Telegram (limit 49MB)


def _s():
    return cr.Session(impersonate="chrome")


def _cards(html):
    """Parse kartu video (area #vidresults)."""
    seg = html.split('id="vidresults"', 1)
    seg = seg[1] if len(seg) > 1 else html
    items = []
    seen = set()
    for m in re.finditer(
            r'<a href="(/video-([A-Za-z0-9]+)/[^"]+)"[^>]*>\s*<img[^>]+'
            r'(?:data-src|src)="([^"]+)"[^>]*alt="([^"]*)"', seg):
        url, vid, thumb, title = m.groups()
        if vid in seen:
            continue
        seen.add(vid)
        items.append({
            "title": (title.replace("&#39;", "'").replace("&amp;", "&")
                      .replace("&quot;", '"').strip() or "tanpa judul"),
            "url": SITE + url,
            "id": vid,
            "thumb": thumb,
        })
    return items


def search(q="", page=1):
    """→ (items, total). items: {title, url, id, thumb}"""
    s = _s()
    q = (q or "").strip()
    if q:
        url = f"{SITE}/{page}/sort/relevance/{quote(q.lower())}/"
    else:
        url = f"{SITE}/cat/ai/" + (f"{page}/" if page > 1 else "")
    r = s.get(url, timeout=25)
    r.raise_for_status()
    items = _cards(r.text)
    # total perkiraan (self-scaling) biar ➡️ selalu ada selama ada isi
    total = page * max(len(items), 40) + 1 if items else (page - 1) * 40
    return items, total


def detail(url):
    """→ {title, duration, thumb, qualities:[{res,size,bytes,url}]}"""
    s = _s()
    r = s.get(url, timeout=25)
    r.raise_for_status()
    t = r.text
    og = re.search(r'<meta property="og:title" content="([^"]+)"', t)
    title = (og.group(1) if og else "tanpa judul")
    title = re.sub(r"\s*-\s*EPORNER\s*$", "", title)
    og2 = re.search(r'<meta property="og:image" content="([^"]+)"', t)
    thumb = og2.group(1) if og2 else ""
    dur = ""
    m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*</(?:span|div)", t)
    if m:
        dur = m.group(1)
    qualities = []
    for m in re.finditer(
            r'href="(/dload/[^"]+/(\d+)/[^"]+)"([^>]*)>\s*(?:Download\s+)?'
            r"MP4 \((\d+p), ([a-z0-9]+), ([\d.]+) ([KMG]B)\)", t):
        path, _res, attrs, res, codec, size, unit = m.groups()
        if "account.login" in attrs:      # kualitas premium (wajib login)
            continue
        mb = float(size) * {"KB": 1e-3, "MB": 1.0, "GB": 1e3}[unit]
        qualities.append({"res": res, "codec": codec, "size": f"{size} {unit}",
                          "bytes": int(mb * 1e6), "url": SITE + path})
    qualities.sort(key=lambda x: int(x["res"].rstrip("p")))
    return {"title": title, "duration": dur, "thumb": thumb,
            "qualities": qualities}


def pilih_kualitas(qualities, target=720):
    """Kualitas tertinggi ≤ target yang size-nya < MAX_BYTES."""
    ok = [q for q in qualities if q["bytes"] < MAX_BYTES
          and int(q["res"].rstrip("p")) <= target]
    if ok:
        return ok[-1]
    if qualities:                    # semua > MAX_BYTES → yang paling kecil
        return min(qualities, key=lambda x: x["bytes"])
    return None


def download(url, out_path=None, res="720", progress=None):
    """Download video (mp4 h264) via /dload/. → (path, size_bytes)."""
    import os
    d = detail(url)
    q = pilih_kualitas(d["qualities"], int(str(res).rstrip("p")) if res else 720)
    if not q:
        raise RuntimeError("tidak ada link download")
    if not out_path:
        safe = re.sub(r"[^a-z0-9]+", "-", d["title"].lower())[:48].strip("-")
        out_path = f"{safe or 'eporner-ai'}-{q['res']}.mp4"
    s = _s()
    t0 = time.time()
    with s.stream("GET", q["url"], headers={"Referer": url}, timeout=180) as r:
        r.raise_for_status()
        n = 0
        chunks = (r.iter_content(chunk_size=1 << 16)
                  if hasattr(r, "iter_content") else [r.content])
        with open(out_path, "wb") as f:
            for chunk in chunks:
                if not chunk:
                    continue
                f.write(chunk)
                n += len(chunk)
                if progress and int(time.time() - t0) % 4 == 0:
                    try:
                        progress(n, q["bytes"])
                    except Exception:
                        pass
    return out_path, os.path.getsize(out_path)


if __name__ == "__main__":
    items, total = search("", 1)
    print(f"{len(items)} video AI | total perkiraan {total}")
    for it in items[:5]:
        print(" •", it["title"][:64])
    d = detail(items[0]["url"])
    print("\ndetail:", d["title"][:60], "|", d["duration"], "|",
          [(q["res"], q["size"]) for q in d["qualities"]][:5])
