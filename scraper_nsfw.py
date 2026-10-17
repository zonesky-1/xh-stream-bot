"""Scraper NSFW images — konten dewasa 18+ (post publik, tag bebas).

Sumber utama: rule34.xxx (JSON API publik, tanpa akun)
Fallback: e621.net (JSON API publik, butuh User-Agent deskriptif)

Kedua situs: konten buatan/post dewasa antar orang dewasa — bukan CSAM
(gak ada endpoint anak di sini; filter rating & tag jahat di-skip).
"""
import random
import warnings

import httpx

warnings.filterwarnings("ignore")

UA_R34 = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124.0 Safari/537.36"
UA_E621 = "xh-bot/1.0 (telegram media bot; contact @Updatebotsiitu_bot)"

# tag yang di-skip kalau user ketik sendiri (biar gak nyasar ke zona gelap)
BAD_TAGS = {"shota", "child", "loli", "lolicon", "shotacock", "young",
            "teen", "underage", "ambiguous_age", "small_breast",
            "little_girl", "little_boy", "cub", "guro", "scat",
            "vore", "animal_genitalia", "animal"}

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def _sanitize(q: str) -> str:
    tags = [t for t in q.lower().split() if t and t not in BAD_TAGS]
    if any(t in BAD_TAGS for t in q.lower().split()):
        raise ValueError("tag itu gak gua izinin")
    return " ".join(tags[:6])            # batasi 6 tag


def _http():
    return httpx.Client(timeout=30, verify=False, follow_redirects=True)


def r34_search(q="", limit=25, page=None):
    """→ list {url, tags, id, score} (rule34)."""
    tags = _sanitize(q) if q else "score:>500"
    if page is None:
        page = random.randint(0, 30)
    r = _http().get("https://rule34.xxx/index.php", params={
        "page": "dapi", "s": "post", "q": "index", "json": "1",
        "tags": tags, "limit": limit, "pid": page})
    r.raise_for_status()
    data = r.json()
    out = []
    for p in data if isinstance(data, list) else []:
        u = (p.get("file_url") or "").replace("http://", "https://")
        if u.lower().endswith(IMG_EXT):
            out.append({"url": u, "tags": (p.get("tags") or "")[:90],
                        "id": p.get("id"), "score": p.get("score", 0)})
    return out


def e621_search(q="", limit=25, page=None):
    """→ list {url, tags, id, score} (e621, fallback)."""
    tags = _sanitize(q) if q else "score:>500 solo female"
    if page is None:
        page = random.randint(0, 20)
    r = _http().get("https://e621.net/posts.json", params={
        "tags": tags, "limit": limit, "page": page},
        headers={"User-Agent": UA_E621})
    r.raise_for_status()
    posts = (r.json() or {}).get("posts", [])
    out = []
    for p in posts:
        f = p.get("file") or {}
        u = f.get("url") or ""
        if u.lower().endswith(IMG_EXT):
            out.append({"url": u,
                        "tags": " ".join((p.get("tags") or {}).get("general", []))[:90],
                        "id": p.get("id"), "score": p.get("score", {}).get("total", 0)})
    return out


def xbooru_search(q="", limit=25, page=None):
    """→ list {url, tags, id, score} (xbooru, dapi JSON)."""
    tags = _sanitize(q) if q else "score:>200"
    if page is None:
        page = random.randint(0, 40)
    r = _http().get("https://xbooru.com/index.php", params={
        "page": "dapi", "s": "post", "q": "index", "json": "1",
        "tags": tags, "limit": limit, "pid": page})
    r.raise_for_status()
    out = []
    for p in r.json() if isinstance(r.json(), list) else []:
        u = (p.get("file_url") or "").replace("http://", "https://")
        if u.lower().endswith(IMG_EXT):
            out.append({"url": u, "tags": (p.get("tags") or "")[:90],
                        "id": p.get("id"), "score": p.get("score", 0)})
    return out


def e926_search(q="", limit=25, page=None):
    """→ list {url, tags, id, score} (e926, furry/anthro)."""
    tags = _sanitize(q) if q else "score:>500"
    if page is None:
        page = random.randint(0, 20)
    r = _http().get("https://e926.net/posts.json", params={
        "tags": tags, "limit": limit, "page": page},
        headers={"User-Agent": UA_E621})
    r.raise_for_status()
    out = []
    for p in (r.json() or {}).get("posts", []):
        u = (p.get("file") or {}).get("url") or ""
        if u.lower().endswith(IMG_EXT):
            out.append({"url": u,
                        "tags": " ".join((p.get("tags") or {}).get("general", []))[:90],
                        "id": p.get("id"), "score": (p.get("score") or {}).get("total", 0)})
    return out


def random_post(q=""):
    """4 sumber: rule34 → e621 → xbooru → e926 → 1 post acak."""
    errors = []
    for fn in (r34_search, e621_search, xbooru_search, e926_search):
        try:
            items = fn(q)
            if items:
                return random.choice(items)
            errors.append(f"{fn.__name__}: kosong")
        except Exception as e:
            errors.append(f"{fn.__name__}: {str(e)[:60]}")
    raise RuntimeError(" ; ".join(errors) or "gak ada hasil")


if __name__ == "__main__":
    it = random_post()
    print("random:", it["url"][:90])
    print("tags:", it["tags"][:80])
    it2 = random_post("catgirl solo")
    print("catgirl:", it2["url"][:90])
