"""Scraper PornTrex (video bokep barat, mp4 direct via get_file)."""
import re
import warnings

from curl_cffi import requests as cr

warnings.filterwarnings("ignore")

SITE = "https://www.porntrex.com"


def _s():
    s = cr.Session(impersonate="chrome")
    return s


def search(q="", limit=20):
    """→ list {title, url, dur}"""
    s = _s()
    u = f"{SITE}/search/" + (f"?q={q.replace(' ', '+')}" if q else "?sort_by=relevance")
    t = s.get(u, timeout=25).text
    items, seen = [], set()
    for m in re.finditer(
            r'href="(' + SITE + r'/video/\d+/[^"]+)"[^>]*>.*?</a>',
            t, re.S):
        url = m.group(1)
        if url in seen:
            continue
        seen.add(url)
        title = re.sub(r"[-_]+", " ", url.rsplit("/", 1)[-1])[:70]
        items.append({"title": title, "url": url, "dur": ""})
        if len(items) >= limit:
            break
    return items


def detail(url):
    """→ {title, mp4, poster}"""
    s = _s()
    t = s.get(url, timeout=25).text
    ti = re.search(r"<title>([^<]+)</title>", t)
    title = (ti.group(1) if ti else "video")[:80]
    m = re.search(r'video_url\s*:\s*["\']([^"\']+)', t)
    if not m:
        m2 = re.findall(r'(https?://[^"\'\\ ]+\.mp4[^"\'\\ ]*)', t)
        if not m2:
            raise RuntimeError("mp4 gak ketemu")
        mp4 = m2[0]
    else:
        mp4 = m.group(1)
    po = re.search(r'<meta property="og:image" content="([^"]+)"', t)
    return {"title": title, "mp4": mp4, "poster": po.group(1) if po else ""}


if __name__ == "__main__":
    it = search("teen")[0]
    print("cari:", it["title"][:50])
    d = detail(it["url"])
    print("mp4:", d["mp4"][:90])


def browse_popular(limit=20):
    """Video paling populer PornTrex."""
    s = _s()
    t = s.get(f"{SITE}/?sort_by=most-popular", timeout=25).text
    items, seen = [], set()
    for m in re.finditer(r'href="(https?://[^"]*porntrex\.com/video/\d+/[^"]+)"', t):
        url = m.group(1)
        if url in seen:
            continue
        seen.add(url)
        title = re.sub(r"[-_]+", " ", url.rsplit("/", 1)[-1])[:70]
        items.append({"title": title, "url": url, "dur": ""})
        if len(items) >= limit:
            break
    return items
