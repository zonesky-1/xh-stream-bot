"""scraper_kemono.py — Kemono.cr API scraper (Patreon, Fanbox, Fantia, Candfans)."""
from __future__ import annotations

import json
import logging
import os
import random
import re

from curl_cffi import requests as cr

log = logging.getLogger("kemono")

API = "https://kemono.cr/api/v1"
SITE = "https://kemono.cr"
SERVICES = ("patreon", "fanbox", "fantia", "candfans", "subscribestar", "boosty")
H = {"Accept": "text/css"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CREATORS_FILE = "/home/agentuser/xh-bot/kemono_creators.json"
_CREATORS: list[dict] = []


def get_creators() -> list[dict]:
    """Cache top 1.500 kreator dari kemono_creators.json."""
    global _CREATORS
    if not _CREATORS and os.path.exists(CREATORS_FILE):
        try:
            _CREATORS = json.load(open(CREATORS_FILE))
        except Exception:
            _CREATORS = []
    return _CREATORS


def top_creators(page: int = 1, limit: int = 8) -> tuple[list[dict], int]:
    """Kembalikan slice top kreator dan total halaman."""
    c_list = get_creators()
    total = len(c_list)
    total_pages = max(1, (total + limit - 1) // limit)
    page = max(1, min(page, total_pages))
    start = (page - 1) * limit
    return c_list[start:start + limit], total_pages


def media_url(path: str) -> str:
    """Konversi path media Kemono ke thumbnail edge CDN atau data host."""
    p = path if path.startswith("/") else f"/{path}"
    if not p.lower().endswith(".mp4"):
        return f"https://img.kemono.cr/thumbnail/data{p}"
    return f"{SITE}/data{p}"


def _clean_post(p: dict) -> dict:
    svc = p.get("service") or ""
    uid = str(p.get("user") or "")
    pid = str(p.get("id") or "")
    title = (p.get("title") or "").strip() or f"Post #{pid}"
    content = (p.get("content") or "").strip()

    photos: list[str] = []
    videos: list[str] = []

    f = p.get("file") or {}
    fp = f.get("path")
    if fp:
        name = (f.get("name") or fp).lower()
        u = media_url(fp)
        if name.endswith((".mp4", ".mov", ".webm", ".m4v")):
            videos.append(u)
        elif name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            photos.append(u)

    for a in p.get("attachments") or []:
        ap = a.get("path")
        if not ap:
            continue
        name = (a.get("name") or ap).lower()
        u = media_url(ap)
        if name.endswith((".mp4", ".mov", ".webm", ".m4v")):
            if u not in videos:
                videos.append(u)
        elif name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            if u not in photos:
                photos.append(u)

    return {
        "id": pid,
        "service": svc,
        "creator": uid,
        "title": title,
        "content": content[:300],
        "date": (p.get("published") or p.get("added") or "")[:10],
        "url": f"{SITE}/{svc}/user/{uid}/post/{pid}" if svc and uid and pid else SITE,
        "photos": photos,
        "videos": videos,
    }


def creator_profile(creator_id: str, service: str = "patreon") -> dict | None:
    url = f"{API}/{service}/user/{creator_id}/profile"
    try:
        r = cr.get(url, headers=H, timeout=10, impersonate="chrome124")
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def creator_posts(creator_id: str, service: str = "patreon",
                  offset: int = 0, limit: int = 50) -> list[dict]:
    url = f"{API}/{service}/user/{creator_id}/posts"
    r = cr.get(url, params={"o": offset}, headers=H, timeout=12, impersonate="chrome124")
    if r.status_code != 200:
        log.warning("creator posts status %s: %s", r.status_code, r.text[:100])
        return []
    raw = r.json()
    posts = raw if isinstance(raw, list) else (raw.get("posts") or [])
    out: list[dict] = []
    for p in posts:
        c = _clean_post(p)
        if c["photos"] or c["videos"]:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def popular() -> list[dict]:
    r = cr.get(f"{API}/posts/popular", headers=H, timeout=12, impersonate="chrome124")
    if r.status_code != 200:
        return []
    posts = r.json().get("posts") or []
    out = []
    for p in posts:
        c = _clean_post(p)
        if c["photos"] or c["videos"]:
            out.append(c)
    return out


def search_posts(q: str, limit: int = 50) -> list[dict]:
    r = cr.get(f"{API}/posts", params={"q": q}, headers=H, timeout=12, impersonate="chrome124")
    if r.status_code != 200:
        return []
    raw = r.json()
    posts = raw if isinstance(raw, list) else (raw.get("posts") or [])
    out = []
    for p in posts:
        c = _clean_post(p)
        if c["photos"] or c["videos"]:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def random_creator_posts() -> tuple[list[dict], str]:
    c_list = get_creators()
    if not c_list:
        return popular(), "🔥 populer hari ini (offline list)"
    pool = c_list[:400]
    random.shuffle(pool)
    for c in pool[:6]:
        try:
            items = creator_posts(c["id"], c.get("svc", "patreon"), limit=30)
            if items:
                label = f"🎲 {c['name']} · {c.get('svc', 'patreon')} ({c.get('fav', 0):,} favs)"
                return items, label
        except Exception:
            continue
    return popular(), "🔥 populer hari ini"


def random_post() -> tuple[list[dict], str]:
    items = popular()
    if items:
        p = random.choice(items)
        return [p], f"🎲 post acak: {p.get('creator')}"
    return random_creator_posts()


def resolve(q: str) -> tuple[list[dict], str]:
    q = (q or "").strip()
    if not q:
        return popular(), "🔥 populer hari ini"
    if q.lower() in ("acak", "random", "rand", "kocok"):
        return random_creator_posts()
    if q.lower() in ("acakpost", "randompost", "postacak"):
        return random_post()

    # Coba nama kreator exact di daftar lokal
    c_list = get_creators()
    q_low = q.lower()
    matched = [c for c in c_list if c["name"].lower() == q_low or c["id"].lower() == q_low]
    if matched:
        c = matched[0]
        items = creator_posts(c["id"], c.get("svc", "patreon"))
        if items:
            return items, f"👑 {c['name']} · {c.get('svc', 'patreon')}"

    # Coba exact creator di tiap service
    for svc in SERVICES:
        prof = creator_profile(q, svc)
        if prof:
            items = creator_posts(q, svc)
            if items:
                name = prof.get("name") or q
                return items, f"👑 {name} · {svc}"

    # Fallback search posts
    items = search_posts(q)
    if items:
        return items, f"🔍 cari: {q}"

    raise RuntimeError(f"gak ketemu bocoran '{q}' di Kemono — coba /km acak atau /km top")
