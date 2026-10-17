"""Scraper Chaturbate Live Cams — via official affiliate API.
Public JSON: https://chaturbate.com/api/public/affiliates/onlinerooms/
Mendapatkan snapshot gambar live (360x270/HD), info model, tags, dan chat_url.
"""
from __future__ import annotations

import logging
import random
from curl_cffi import requests as cr

log = logging.getLogger("cam")

API_URL = "https://chaturbate.com/api/public/affiliates/onlinerooms/"
CAMPAIGN_WM = "0OQAo"


def get_online_rooms(tag: str = "", limit: int = 50, gender: str = "f") -> list[dict]:
    """Ambil daftar room live cewek yang lagi online.
    tag: optional filter tag (misal 'asian', 'teen', 'milf', 'latina', dll)
    gender: 'f' (female), 'c' (couple), 't' (trans)
    """
    params = {
        "wm": CAMPAIGN_WM,
        "client_ip": "request_ip",
        "gender": gender,
        "limit": limit,
    }
    t = (tag or "").strip().lower()
    if t and t not in ("all", "semua", "acak", "random"):
        params["tag"] = t

    try:
        r = cr.get(API_URL, params=params, timeout=12, impersonate="chrome124")
        if r.status_code != 200:
            log.warning("chaturbate API status %s: %s", r.status_code, r.text[:100])
            return []
        data = r.json()
        raw_rooms = data.get("results") or []
        rooms = []
        for rm in raw_rooms:
            # Ambil image thumbnail terbaik
            img = rm.get("image_url_360x270") or rm.get("image_url")
            if not img or not img.startswith("http"):
                continue
            rooms.append({
                "username": rm.get("username", "Anon"),
                "subject": (rm.get("room_subject") or "").strip(),
                "age": rm.get("age"),
                "viewers": rm.get("num_users", 0),
                "tags": rm.get("tags") or [],
                "image": img,
                "url": rm.get("chat_room_url") or f"https://chaturbate.com/{rm.get('username')}/",
                "location": rm.get("location") or "",
            })
        return rooms
    except Exception as e:
        log.exception("chaturbate error: %s", e)
        return []


def random_cam(tag: str = "") -> dict | None:
    """Comot 1 room acak."""
    rooms = get_online_rooms(tag=tag, limit=60)
    return random.choice(rooms) if rooms else None
