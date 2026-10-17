# language: Python 3.11, file: scraper_coomer.py — COOMER (bocoran OnlyFans/Fansly API)
#
# Fakta lapangan (bedah 2026-10-17, jangan diubah sembarangan):
# 1. API: https://coomer.st/api/v1/... — SEMUA request wajib header
#    "Accept: text/css" (anti-DDG mirror; tanpa itu 403 octet-stream aneh).
# 2. Endpoint penting (dari swagger embedded /assets/api-DB-01rif.js):
#      GET /v1/posts/popular?service=onlyfans     → {info, props, posts:[50]}
#      GET /v1/posts?q=<kata>&service=onlyfans    → {count, posts:[50]}  ← q= FILTER KONTEN
#      GET /v1/{service}/user/{id}/profile        → {post_count, …} (404 = bukan dia)
#      GET /v1/{service}/user/{id}/posts?o=0      → [50 post] (o=50 halaman 2, unik)
#      GET /v1/{service}/user/{id}/post/{post_id} → {post:{…, content, file, attachments}}
#    Param query=/search=/creator= DIABAIKAN server (full list 220rb) — jangan dipakai
#    utk search; /v1/creators.txt 404. Search kreator = coba profile exact dulu, baru q=.
# 3. Media: post.file.path + post.attachments[].path (absolut diawali "/").
#    URL = https://coomer.st/data<path> → 302 ke n[1-4].cooomer.st → file asli.
#    Box VPS TIDAK bisa akses n*.cooomer.st (timeout, semua node) — TAPI server
#    Telegram BISA (terverifikasi: sendPhoto/sendVideo by URL sukses, redirect diikut).
#    JADI: jangan pernah download sendiri — LEMPAR URL ke Bot API.
# 4. Service: onlyfans, fansly, candfans (dari SPA WN=['onlyfans','fansly','candfans']).
# 5. substring/title mengandung HTML (<p>, <a>) → strip tag sebelum tampil.
from __future__ import annotations

import json
import logging
import os
import random
import re

from curl_cffi import requests as cr

log = logging.getLogger("coomer")

API = "https://coomer.st/api/v1"
SITE = "https://coomer.st"
SERVICES = ("onlyfans", "fansly", "candfans")
H = {"Accept": "text/css"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CREATORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coomer_creators.json")
_CREATORS: list[dict] = []


def get_creators() -> list[dict]:
    global _CREATORS
    if not _CREATORS and os.path.exists(CREATORS_FILE):
        try:
            with open(CREATORS_FILE) as f:
                _CREATORS = json.load(f)
        except Exception:
            _CREATORS = []
    return _CREATORS


def top_creators(page: int = 1, limit: int = 8) -> tuple[list[dict], int]:
    """List kreator teratas berdasarkan favorit, dipaginasi."""
    clist = get_creators()
    total_pages = max(1, (len(clist) + limit - 1) // limit)
    p = max(1, min(page, total_pages))
    start = (p - 1) * limit
    return clist[start:start + limit], total_pages


def random_creator_posts() -> tuple[list[dict], str]:
    """Pilih 1 kreator top secara acak dan ambil postingan terbarunya."""
    clist = get_creators()
    if clist:
        pool = list(clist[:500])
        random.shuffle(pool)
        for c in pool[:8]:
            try:
                items = creator_posts(c["id"], c.get("svc", "onlyfans"), limit=30)
                if items:
                    name = c["name"]
                    svc = c.get("svc", "onlyfans")
                    fav = c.get("fav", 0)
                    label = f"🎲 {name} · {svc} ({fav:,} favs)"
                    return items, label
            except Exception:
                continue
    return popular(), "🔥 populer hari ini (fallback)"


def random_post() -> tuple[list[dict], str]:
    """Comot 1 post acak dari feed populer hari ini."""
    pop = popular()
    if pop:
        p = random.choice(pop)
        return [p], f"🎲 acak post: {p.get('creator', 'kreator')}"
    return popular(), "🔥 populer hari ini"

_SESS = None


def _session() -> cr.Session:
    global _SESS
    if _SESS is None:
        _SESS = cr.Session(impersonate="chrome124")
    return _SESS


def _get(path: str, params: dict | None = None, timeout: int = 30) -> cr.Response:
    last: Exception | None = None
    for _ in range(3):
        try:
            return _session().get(API + path, params=params or {},
                                  headers=H, timeout=timeout)
        except Exception as e:
            last = e
    raise RuntimeError(f"coomer {path} gagal: {last}")


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _media_paths(post: dict) -> list[str]:
    """Gabung file utama + attachments → [path] yang ber-media saja."""
    out = []
    f = post.get("file") or {}
    if f.get("path"):
        out.append(f["path"])
    for a in post.get("attachments") or []:
        p = a.get("path")
        if p:
            out.append(p)
    return [p for p in out if p.lower().endswith((".jpg", ".jpeg", ".png",
                                                   ".webp", ".gif", ".mp4"))]


def media_url(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    if not p.lower().endswith(".mp4"):
        return f"https://img.coomer.st/thumbnail/data{p}"
    return f"{SITE}/data{p}"


def _norm(post: dict, fallback_creator: str = "") -> dict:
    paths = _media_paths(post)
    videos = [p for p in paths if p.lower().endswith(".mp4")]
    photos = [p for p in paths if not p.lower().endswith(".mp4")]
    title = _strip(post.get("title") or "") or _strip(post.get("substring") or "")
    if not title:
        title = "(tanpa judul)"
    return {
        "id": post.get("id") or "",
        "creator": post.get("user") or fallback_creator,
        "service": post.get("service") or "onlyfans",
        "title": title[:140],
        "date": (post.get("published") or "")[:10],
        "photos": [media_url(p) for p in photos],
        "videos": [media_url(p) for p in videos],
        "url": f"{SITE}/{post.get('service') or 'onlyfans'}/user/"
               f"{post.get('user') or fallback_creator}",
    }


def popular(service: str = "onlyfans") -> list[dict]:
    """/of tanpa argumen — 50 post populer hari ini (campur kreator)."""
    r = _get("/posts/popular", {"service": service})
    r.raise_for_status()
    posts = (r.json() or {}).get("posts") or []
    return [_norm(p) for p in posts if _media_paths(p)]


def search_posts(q: str, service: str = "onlyfans") -> list[dict]:
    """Search konten lewat q= (filter substring/title server-side)."""
    r = _get("/posts", {"q": q[:60], "service": service})
    r.raise_for_status()
    posts = (r.json() or {}).get("posts") or []
    return [_norm(p) for p in posts if _media_paths(p)]


def profile(creator: str, service: str) -> dict | None:
    """Exact creator? → profile dict, kalau 404 → None."""
    r = _get(f"/{service}/user/{creator}/profile")
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def creator_posts(creator: str, service: str = "onlyfans",
                  offset: int = 0, limit: int = 50) -> list[dict]:
    r = _get(f"/{service}/user/{creator}/posts", {"o": offset})
    r.raise_for_status()
    posts = r.json() or []
    return [_norm(p, creator) for p in posts[:limit] if _media_paths(p)]


def resolve(q: str) -> tuple[list[dict], str]:
    """/of <kreator|kata>:
    1) keyword acak/random -> comot kreator random
    2) coba exact creator di tiap service (profile 200) → posts per kreator
    3) fallback: search posts q=
    Balik (items, label)."""
    q = (q or "").strip()
    if not q:
        return popular(), "🔥 populer hari ini"
    ql = q.lower()
    if ql in ("acak", "random", "rand", "kocok"):
        return random_creator_posts()
    if ql in ("acakpost", "randompost", "postacak"):
        return random_post()
    if re.fullmatch(r"[\w.\-]+", q):
        for svc in SERVICES:
            try:
                prof = profile(q, svc)
            except Exception:
                continue
            if prof:
                try:
                    items = creator_posts(q, svc)
                except Exception:
                    items = []
                if items:
                    n = prof.get("post_count")
                    label = f"{q} · {svc}" + (f" · {n} post" if n else "")
                    return items, label
    try:
        items = search_posts(q)
    except Exception:
        items = []
    if items:
        return items, f"cari: {q}"
    # coba service lain utk search
    for svc in SERVICES[1:]:
        try:
            items = search_posts(q, svc)
        except Exception:
            items = []
        if items:
            return items, f"cari: {q} ({svc})"
    raise RuntimeError(f"gak ketemu bocoran '{q}' — coba nama kreator persis "
                       f"(mis. /of emma_more) atau kata kunci lain")
