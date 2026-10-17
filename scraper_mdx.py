"""Scraper MangaDex (komik doujin hentai — contentRating pornographic).

API resmi, tanpa key:
- search: /manga?title=Q&contentRating[]=pornographic
- feed:   /manga/{id}/feed?order[chapter]=asc&translatedLanguage[]=id
- pages:  /at-home/server/{chapterId} → baseUrl/data/hash/halaman.jpg

Jebakan: contentRating[] HARUS diset (default cuma safe);
feed butuh pagination limit=50 (chapter banyak);
halaman = uploads.mangadex.org (kadang lambat, perlu retry).
"""
import warnings
from urllib.parse import urljoin

import httpx

warnings.filterwarnings("ignore")

API = "https://api.mangadex.org"
UA = "xh-bot/1.0 (telegram media bot)"


def _c():
    return httpx.Client(headers={"User-Agent": UA}, timeout=30,
                        follow_redirects=True)


def search(q="", limit=20):
    """→ list {id, title, rating} — doujin hentai didahulukan."""
    params = {"title": q, "limit": limit,
              "contentRating[]": ["pornographic", "safe", "suggestive"],
              "includes[]": ["cover_art"]}
    if not q:
        params["order[]"] = ["followedCount"]      # relevansi = default search
    r = _c().get(f"{API}/manga", params=params)
    r.raise_for_status()
    items = []
    for m in r.json().get("data", []):
        at = m.get("attributes", {})
        title = (at.get("title") or {}).get("en") or \
                next(iter((at.get("title") or {}).values()), "?")
        cov = next((rel["attributes"]["fileName"]
                    for rel in m.get("relationships", [])
                    if rel["type"] == "coverArt"), None)
        cover = (f"https://uploads.mangadex.org/covers/{m['id']}/{cov}"
                 if cov else None)
        items.append({"id": m["id"], "title": title[:70], "cover": cover,
                      "rating": ",".join(at.get("contentRating", []))})
    # doujin/18+ duluan
    items.sort(key=lambda x: "pornographic" not in x["rating"])
    return items


def chapters(manga_id, lang="id"):
    """→ list {id, chapter, title} (urut naik). Fallback bahasa Inggris."""
    out, offset = [], 0
    while offset < 500:                  # batas 500 chapter (cukup buat doujin)
        r = _c().get(f"{API}/manga/{manga_id}/feed", params={
            "limit": 50, "offset": offset,
            "translatedLanguage[]": [lang, "en"],
            "order[chapter]": "asc",
            "contentRating[]": ["pornographic", "safe", "suggestive"]})
        r.raise_for_status()
        d = r.json()
        data = d.get("data", [])
        if not data:
            break
        for ch in data:
            at = ch.get("attributes", {})
            out.append({"id": ch["id"],
                        "chapter": at.get("chapter") or "?",
                        "title": (at.get("title") or "")[:60],
                        "lang": at.get("translatedLanguage", "?")})
        offset += 50
        if offset >= d.get("total", 0):
            break
    return out


def pages(chapter_id):
    """→ list URL halaman (uploads.mangadex.org)."""
    r = _c().get(f"{API}/at-home/server/{chapter_id}")
    r.raise_for_status()
    d = r.json()
    base = d["baseUrl"]
    ch = d["chapter"]
    return [urljoin(base + "/data/" + ch["hash"] + "/", p)
            for p in ch.get("data", [])]


if __name__ == "__main__":
    it = search("hentai")[0]
    print("cari:", it["title"], "|", it["rating"])
    chs = chapters(it["id"])
    print("chapter:", len(chs), "| pertama:", chs[0]["chapter"] if chs else "-")
    pgs = pages(chs[0]["id"])
    print("halaman:", len(pgs), "|", pgs[0][:80] if pgs else "-")


def browse_latest(limit=15):
    """Doujin terbaru yang lagi di-upload."""
    r = _c().get(f"{API}/manga", params={
        "limit": limit,
        "order[latestUploadedChapter]": "desc",
        "contentRating[]": ["pornographic", "safe", "suggestive"]})
    r.raise_for_status()
    out = []
    for a in r.json().get("data", []):
        at = a.get("attributes", {})
        title = at.get("title")
        if isinstance(title, dict):
            title = title.get("en") or next(iter(title.values()), "?")
        title = title or at.get("canonicalTitle") or "?"
        out.append({
            "id": a["id"], "title": title[:70],
            "rating": "pornographic" if "pornographic" in
                      (at.get("contentRating") or "") else "safe"})
    return out
