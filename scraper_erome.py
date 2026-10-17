"""Client scraping Erome (erome.com) — sarang cewek amatir self-upload, leak hp, dan foto/video pribadi.
Mendukung explore terbaru/populer, pencarian album (/erome <keyword>), dan ekstraksi album media (foto & video).
"""
from __future__ import annotations

import logging
import random
import re
from bs4 import BeautifulSoup
from curl_cffi import requests as cr

log = logging.getLogger("erome")

SITE = "https://www.erome.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _headers() -> dict:
    return {"User-Agent": UA, "Referer": SITE}


def parse_album_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    albums = []
    for el in soup.find_all("div", class_="album"):
        a = el.find("a", class_="album-title") or el.find("a", href=lambda h: h and "/a/" in h)
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = f"{SITE}{href}"
        aid = href.split("/a/")[-1].split("?")[0]
        title = a.text.strip() or f"Album {aid}"
        img = el.find("img")
        thumb = (img.get("data-src") or img.get("src") or "") if img else ""
        user_el = el.find("a", class_="album-user")
        user = user_el.text.strip() if user_el else "Anon"
        albums.append({
            "id": aid,
            "title": title,
            "url": href,
            "thumb": thumb,
            "user": user,
        })
    return albums


def explore(page: int = 1) -> list[dict]:
    """Album explore terbaru/populer."""
    url = f"{SITE}/explore" if page <= 1 else f"{SITE}/explore?page={page}"
    try:
        r = cr.get(url, headers=_headers(), timeout=12, impersonate="chrome124")
        if r.status_code == 200:
            return parse_album_list(r.text)
    except Exception as e:
        log.exception("erome explore error: %s", e)
    return []


def search(q: str, page: int = 1) -> list[dict]:
    """Cari album amatir berdasarkan kata kunci (misal: 'indo', 'hijab', 'college', 'amateur')."""
    url = f"{SITE}/search?q={q}" if page <= 1 else f"{SITE}/search?q={q}&page={page}"
    try:
        r = cr.get(url, headers=_headers(), timeout=12, impersonate="chrome124")
        if r.status_code == 200:
            return parse_album_list(r.text)
    except Exception as e:
        log.exception("erome search error: %s", e)
    return []


def get_album_detail(aid: str) -> dict | None:
    """Ambil detail album: foto full resolution & direct mp4 video."""
    url = f"{SITE}/a/{aid}" if not aid.startswith("http") else aid
    try:
        r = cr.get(url, headers=_headers(), timeout=12, impersonate="chrome124")
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else f"Album {aid}"
        user_el = soup.find("a", class_="username")
        user = user_el.text.strip() if user_el else "Anon"

        photos: list[str] = []
        videos: list[str] = []

        # Cari foto full-res
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if src and "erome.com" in src and "avatar" not in src and "thumbs" not in src:
                if src not in photos:
                    photos.append(src)

        # Cari video mp4
        for vid in soup.find_all("video"):
            src = vid.find("source")
            v_url = (src.get("src") if src else "") or vid.get("src")
            if v_url and v_url.startswith("http"):
                if v_url not in videos:
                    videos.append(v_url)

        # Fallback regex jika DOM berubah
        if not photos:
            photos = list(dict.fromkeys(re.findall(r"(https://s\d+\.erome\.com/[^\s\"'<>]+\.(?:jpg|jpeg|png))", r.text)))
            # exclude thumbs
            photos = [p for p in photos if "thumbs" not in p]

        if not videos:
            videos = list(dict.fromkeys(re.findall(r"(https://v\d+\.erome\.com/[^\s\"'<>]+\.mp4)", r.text)))

        return {
            "id": aid,
            "title": title,
            "user": user,
            "url": url,
            "photos": photos,
            "videos": videos,
        }
    except Exception as e:
        log.exception("erome get_album_detail error: %s", e)
        return None


def resolve(q: str) -> tuple[list[dict], str]:
    """Routing query /erome <query>."""
    q = (q or "").strip()
    if not q or q.lower() in ("acak", "random", "explore", "hot"):
        items = explore()
        if items:
            if q.lower() in ("acak", "random"):
                random.shuffle(items)
                return items, "🎲 album amatir acak"
            return items, "🔥 explore album amatir terbaru"
        raise RuntimeError("gagal mengambil explore Erome")

    items = search(q)
    if items:
        return items, f"🔍 cari album '{q}'"
    raise RuntimeError(f"gak ketemu album Erome untuk '{q}' — coba kata kunci lain (mis. /erome indo atau /erome hijab)")
