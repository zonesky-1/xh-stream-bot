"""Scraper Kitsu (info anime: score, episode, sinopsis, poster).

API publik, tanpa key. GraphQL-ish REST v1.
"""
import re
import warnings

import httpx

warnings.filterwarnings("ignore")

API = "https://kitsu.io/api/edge"


def _c():
    return httpx.Client(
        headers={"Accept": "application/vnd.api+json",
                 "User-Agent": "xh-bot/1.0"},
        timeout=25, follow_redirects=True)


def search(q="", limit=5):
    """→ list {id, title, score, eps, status, poster, synopsis}"""
    r = _c().get(f"{API}/anime", params={
        "filter[text]": q, "page[limit]": limit})
    r.raise_for_status()
    out = []
    for a in r.json().get("data", []):
        at = a.get("attributes", {})
        out.append({
            "id": a["id"],
            "title": (at.get("canonicalTitle") or at.get("titles", {}).get("en_jp") or "?")[:70],
            "score": (at.get("averageRating") or "-")[:5],
            "eps": at.get("episodeCount") or "?",
            "status": at.get("status", "?"),
            "poster": ((at.get("posterImage") or {}).get("large")
                       or (at.get("posterImage") or {}).get("medium") or ""),
            "synopsis": re.sub(r"\s+", " ", at.get("synopsis") or "")[:300],
            "year": (at.get("startDate") or "")[:4],
        })
    return out


if __name__ == "__main__":
    for it in search("one piece", 3):
        print(f"• {it['title']} | score {it['score']} | {it['eps']} eps | {it['year']}")
        print("  ", it["synopsis"][:80])


def top_anime(limit=10):
    """Anime terpopuler (by rating, ongoing)."""
    r = _c().get(f"{API}/anime", params={
        "sort": "-averageRating", "page[limit]": limit,
        "filter[status]": "current",
        "filter[averageRating]": "75.."})
    r.raise_for_status()
    out = []
    for a in r.json().get("data", []):
        at = a.get("attributes", {})
        out.append({
            "id": a["id"],
            "title": (at.get("canonicalTitle") or "?")[:70],
            "score": (at.get("averageRating") or "-")[:5],
            "eps": at.get("episodeCount") or "?",
            "status": at.get("status", "?"),
            "poster": ((at.get("posterImage") or {}).get("large")
                       or (at.get("posterImage") or {}).get("medium") or ""),
            "synopsis": re.sub(r"\s+", " ", at.get("synopsis") or "")[:300],
            "year": (at.get("startDate") or "")[:4]})
    return out
