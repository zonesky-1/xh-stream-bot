"""Scraper JavDB (database JAV: search + magnet + cover).

Tembok umur JavBus gak ada di sini — JavDB cuma butuh impersonate Chrome.
Cover pattern: c0.jdbstatic.com/covers/<2char>/<code>.jpg
Magnet: di halaman detail, size di baris sebelahnya.
"""
import re
import warnings

from curl_cffi import requests as cr

warnings.filterwarnings("ignore")

SITE = "https://javdb.com"


def _s():
    return cr.Session(impersonate="chrome")


def search(q="", limit=10):
    """→ list {code, title, url}"""
    s = _s()
    for att in range(3):
        try:
            t = s.get(f"{SITE}/search", params={"q": q}, timeout=25).text
            break
        except Exception:
            if att == 2:
                raise
    items, seen = [], set()
    for m in re.finditer(
            r'<div class=.item.>\s*<a href=.(/v/[a-zA-Z0-9]+).[^>]*>(.*?)</a>',
            t, re.S):
        url, body = m.group(1), m.group(2)
        if url in seen:
            continue
        seen.add(url)
        code = re.search(r'<strong>([^<]+)</strong>', body)
        title = re.search(r'</strong>\s*([^<]+)</div>', body)
        url_id = url.rsplit("/", 1)[-1]
        img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', body)
        cover_url = img.group(1) if img else f"https://c0.jdbstatic.com/covers/{url_id[:2].lower()}/{url_id}.jpg"
        items.append({"url": SITE + url,
                      "code": (code.group(1) if code else url_id).strip(),
                      "title": (title.group(1) if title else "").strip()[:70],
                      "cover": cover_url})
        if len(items) >= limit:
            break
    return items


def detail(url):
    """→ {title, cover, magnets: [(hash, size)], date, genres}"""
    s = _s()
    for att in range(3):
        try:
            t = s.get(url, timeout=25).text
            break
        except Exception:
            if att == 2:
                raise
    ti = re.search(r"<title>([^<]+)</title>", t)
    title = re.sub(r"\s+", " ", ti.group(1) if ti else "?").strip()[:100]
    code = url.rsplit("/", 1)[-1]
    cover = f"https://c0.jdbstatic.com/covers/{code[:2]}/{code}.jpg"
    # semua magnet + size terdekat (lookahead 300 char)
    magnets, seen = [], set()
    for m in re.finditer(r"magnet:\?xt=urn:btih:([0-9a-fA-F]{40})", t):
        h = m.group(1).lower()
        if h in seen:
            continue
        seen.add(h)
        tail = t[m.end():m.end() + 300]
        sm = re.search(r"\d+(?:\.\d+)?\s*(?:GB|MB)", tail)
        magnets.append((h, sm.group(0) if sm else "?"))
        if len(magnets) >= 10:
            break
    date = re.search(r'<div class="date">([\d-]+)</div>', t)
    genres = re.findall(r'<a[^>]+href="/tags[^"]*"[^>]*>([^<]+)</a>', t)
    return {"title": title, "cover": cover, "magnets": magnets[:10],
            "date": date.group(1) if date else "?",
            "genres": genres[:6]}


def magnet_link(btih, size=""):
    return f"magnet:?xt=urn:btih:{btih}&dn=javdb"


if __name__ == "__main__":
    its = search("SSIS")
    print(f"{len(its)} hasil")
    for it in its[:3]:
        print(" •", it["code"], it["title"][:50])
    d = detail(its[0]["url"])
    print("detail:", d["title"][:60])
    print("cover:", d["cover"][:70])
    print("magnet:", len(d["magnets"]), "| pertama:", d["magnets"][0] if d["magnets"] else "-")
    print("date:", d["date"], "| genres:", d["genres"][:3])


def browse_latest(limit=15):
    """Rilis terbaru di homepage JavDB."""
    s = _s()
    for att in range(3):
        try:
            t = s.get(SITE + "/", timeout=25).text
            break
        except Exception:
            if att == 2:
                raise
    items, seen = [], set()
    for m in re.finditer(
                        r'<div class=.item.>\s*<a href=.(/v/[a-zA-Z0-9]+).[^>]*>(.*?)</a>',
            t, re.S):
        url, body = m.group(1), m.group(2)
        if url in seen:
            continue
        seen.add(url)
        code = re.search(r'<strong>([^<]+)</strong>', body)
        title = re.search(r'</strong>\s*([^<]+)</div>', body)
        url_id = url.rsplit("/", 1)[-1]
        img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', body)
        cover_url = img.group(1) if img else f"https://c0.jdbstatic.com/covers/{url_id[:2].lower()}/{url_id}.jpg"
        items.append({"url": SITE + url,
                      "code": (code.group(1) if code else url_id).strip(),
                      "title": (title.group(1) if title else "").strip()[:70],
                      "cover": cover_url})
        if len(items) >= limit:
            break
    return items
