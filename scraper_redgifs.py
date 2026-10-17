# language: Python 3.11, file: scraper_redgifs.py — REDGIFS (video/gif pendek, API v2)
#
# Fakta lapangan (bedah 2026-10-17, jangan diubah sembarangan):
# 1. Auth: GET https://api.redgifs.com/v2/auth/temporary → {token} (JWT ±950 char).
#    Pakai Bearer token + impersonate chrome124 (curl_cffi) — httpx polos kena
#    401 WrongSender di sebagian endpoint.
# 2. ENDPOINT PUBLIK (tanpa login user):
#      /v2/tags/feed/<tag>?limit=10  → {bestGifs:[…], bestImages:[…], relatedTags}
#      /v2/recommend/gifs/<id>/quick → {gifs:[…]}  (rantai "lainnya")
#      /v1/tags/suggest?query=q      → [{type:tag,text}|{type:creator,text:@user}]
#      /v2/niches?page=N             → {niches:[{id,name,gifs}], pages, total}
#      /v2/creators/search?query=q   → {items:[{name,gifs,…}]}
#    Endpoint /v2/search, /v2/feeds/for-you, /v2/feeds/trending/* = 401/400
#    (butuh akun / var tak valid) → JANGAN dipakai.
# 3. Item gif: {id, description, duration, width, height, type(1=video,2=image),
#    tags, userName, urls:{sd:…-mobile.mp4, hd:….mp4, poster:…-poster.jpg,
#    thumbnail:…-mobile.jpg, html:…/ifr/<id>}}.
#    media.redgifs.com LANGSUNG bisa di-download dari httpx biasa (206).
#    sd ±0.4MB / hd ±2MB — jauh di bawah limit 50MB Telegram.
# 4. tags/feed selalu balikin 10 "best" yang SAMA (offset diabaikan) → variasi
#    datang dari: ganti tag / rantai recommend / random niche.
from __future__ import annotations

import logging
import random
import time

from curl_cffi import requests as cr

log = logging.getLogger("redgifs")

API = "https://api.redgifs.com"
SITE = "https://www.redgifs.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# pool tag default utk /rg tanpa argumen (populer + aman)
DEFAULT_TAGS = ["petite", "amateur", "milf", "blonde", "latina", "asian",
                "brunette", "cosplay", "pov", "compilation", "teen", "babes",
                "handjob", "creampie", "casting", "office", "lingerie"]

_tok: dict = {"token": "", "ts": 0.0}
_SESS = None


def _session() -> cr.Session:
    global _SESS
    if _SESS is None:
        _SESS = cr.Session(impersonate="chrome124")
    return _SESS


def _token(force: bool = False) -> str:
    if not force and _tok["token"] and time.time() - _tok["ts"] < 30 * 60:
        return _tok["token"]
    r = _session().get(f"{API}/v2/auth/temporary", timeout=25)
    r.raise_for_status()
    _tok["token"] = r.json().get("token") or ""
    _tok["ts"] = time.time()
    return _tok["token"]


def _get(path: str, params: dict | None = None, retry: int = 2) -> cr.Response:
    """GET API dengan auto-refresh token saat 401."""
    last: Exception | None = None
    for i in range(retry + 1):
        try:
            r = _session().get(API + path, params=params or {},
                               headers={"Authorization": f"Bearer {_token(i > 0)}",
                                        "Accept": "application/json"},
                               timeout=25)
            if r.status_code == 401 and i < retry:
                _token(force=True)
                continue
            return r
        except Exception as e:  # jaringan flaky → retry singkat
            last = e
            time.sleep(0.8)
    raise RuntimeError(f"redgifs {path} gagal: {last}")


def _norm(g: dict) -> dict:
    """Seragamkan item gif → {id,title,dur,video,poster,thumb,user,url,tags}."""
    urls = g.get("urls") or {}
    vid = urls.get("hd") or urls.get("sd") or ""
    title = (g.get("description") or "").strip()
    if not title:
        tg = g.get("tags") or []
        title = " · ".join(tg[:4]) if tg else (g.get("id") or "gif")
    return {
        "id": g.get("id") or "",
        "title": title[:120],
        "dur": g.get("duration") or 0,
        "w": g.get("width") or 0,
        "h": g.get("height") or 0,
        "video": vid,
        "poster": urls.get("poster") or urls.get("thumbnail") or "",
        "thumb": urls.get("thumbnail") or urls.get("poster") or "",
        "user": g.get("userName") or "",
        "url": urls.get("html") or f"{SITE}/watch/{g.get('id')}",
        "tags": [t for t in (g.get("tags") or []) if isinstance(t, str)][:8],
        "type": g.get("type") or 1,
    }


def suggest(q: str) -> list[dict]:
    """Autocomplete tag/creator → [{kind:'tag'|'creator', text}]"""
    r = _get("/v1/tags/suggest", {"query": q[:40]})
    if r.status_code != 200:
        return []
    out = []
    for x in r.json()[:8]:
        out.append({"kind": x.get("type") or "tag", "text": x.get("text") or ""})
    return out


def tag_feed(tag: str, limit: int = 10) -> list[dict]:
    """Feed tag → list item ternormalisasi (max `limit`)."""
    tag = (tag or "").strip().lower().replace(" ", "-")
    if not tag:
        return []
    r = _get(f"/v2/tags/feed/{tag}", {"limit": max(1, min(limit, 10))})
    if r.status_code != 200:
        log.info("tag feed %s → %s", tag, r.status_code)
        return []
    d = r.json()
    items = [_norm(g) for g in (d.get("bestGifs") or [])]
    items += [_norm(g) for g in (d.get("bestImages") or []) if g.get("type") == 2]
    random.shuffle(items)
    return items[:limit]


def niches(page: int = 1) -> list[dict]:
    """Daftar niche (rekomendasi random tag). → [{id, name, count}]"""
    r = _get("/v2/niches", {"page": page})
    if r.status_code != 200:
        return []
    return [{"id": n.get("id") or "", "name": n.get("name") or "",
             "count": n.get("gifs") or 0}
            for n in (r.json().get("niches") or [])]


def recommend(gif_id: str) -> list[dict]:
    """Rantai '🎲 lainnya' — rekomendasi sejenis dari 1 gif."""
    r = _get(f"/v2/recommend/gifs/{gif_id}/quick")
    if r.status_code != 200:
        return []
    return [_norm(g) for g in (r.json().get("gifs") or [])]


def random_gif(tag: str = "") -> dict:
    """1 gif acak. tag kosong → campur pool tag + niche random."""
    if tag:
        items = tag_feed(tag)
        if items:
            return random.choice(items)
        # tag gak dikenal → coba suggest dulu
        sug = suggest(tag)
        for s in sug:
            if s["kind"] == "tag":
                items = tag_feed(s["text"])
                if items:
                    return items[0]
        raise RuntimeError(f"tag '{tag}' nggak ketemu — coba /rgtag utk lihat saran")
    # tanpa tag: pilih niche/popular tag acak
    pool = list(DEFAULT_TAGS)
    ns = niches(random.randint(1, 30))
    pool += [n["id"] for n in ns if n["id"]][:20]
    random.shuffle(pool)
    for t in pool[:6]:
        items = tag_feed(t, limit=6)
        if items:
            g = random.choice(items)
            g["seed_tag"] = t
            return g
    raise RuntimeError("feed redgifs kosong — coba lagi")


def next_gif(prev_id: str, tag: str = "") -> dict:
    """🎲 lainnya: rekomendasi dulu, habis itu tag lain / feed lagi."""
    if prev_id:
        rec = recommend(prev_id)
        rec = [g for g in rec if g.get("video")]
        if rec:
            return random.choice(rec)
    if tag:
        items = tag_feed(tag, limit=10)
        items = [g for g in items if g.get("video") and g.get("id") != prev_id]
        if items:
            return random.choice(items)
    return random_gif(tag)


def download(video_url: str, out_path: str, referer: str = SITE + "/") -> str:
    """Download mp4 (±0.4–3MB) → out_path. Balik path."""
    r = _session().get(video_url, headers={"Referer": referer, "User-Agent": UA},
                       timeout=90)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path
