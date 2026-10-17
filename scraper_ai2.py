# language: Python 3.11, file: scraper_ai2.py
# Swaplse AI (swaplse.com) — video hentai AI, GRATIS semua, tanpa login.
# Fakta lapangan:
#   • API resmi /api/vitrina/works (Allow di robots.txt) → id, title, kind, src
#   • mp4 direct: https://cdn.swaplse.com/vitrina/w<id>.mp4 (tanpa token/expire)
#   • total ~4.806 karya (video + gambar); index lokal FTS5 utk search
# Kontrak mesin dracin: search(q,page)→(items,total) sync; detail/async,
# stream_url(async), download(async).
from __future__ import annotations

import logging
import os
import re
import sqlite3

import httpx

log = logging.getLogger("scraper_ai2")
DB = "/home/agentuser/xh-bot/ai2_index.db"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    if not os.path.exists(DB):
        raise RuntimeError("index Swaplse belum jalan (index_ai2.py)")
    con = sqlite3.connect(DB, timeout=10)
    try:
        n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        if n == 0:
            raise RuntimeError("index Swaplse kosong")
        offset = (page - 1) * per
        if not q.strip():
            rows = con.execute(
                "SELECT title, url FROM movies ORDER BY rowid "
                "LIMIT ? OFFSET ?", (per, offset)).fetchall()
            return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                      "provider": "Swaplse AI"} for r in rows], n)
        tokens = re.findall(r"[a-zA-Z0-9]+", q.lower())
        if not tokens:
            return [], 0
        match = " ".join(t + "*" for t in tokens)
        try:
            total = con.execute(
                "SELECT COUNT(*) FROM movies_fts WHERE movies_fts MATCH ?",
                (match,)).fetchone()[0]
            rows = con.execute(
                "SELECT m.title, m.url FROM movies_fts f "
                "JOIN movies m ON m.rowid = f.rowid WHERE movies_fts MATCH ? "
                "ORDER BY bm25(movies_fts) LIMIT ? OFFSET ?",
                (match, per, offset)).fetchall()
        except sqlite3.OperationalError:
            like = "%" + q.strip().lower() + "%"
            total = con.execute(
                "SELECT COUNT(*) FROM movies WHERE LOWER(title) LIKE ?",
                (like,)).fetchone()[0]
            rows = con.execute(
                "SELECT title, url FROM movies WHERE LOWER(title) LIKE ? "
                "LIMIT ? OFFSET ?", (like, per, offset)).fetchall()
        return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                  "provider": "Swaplse AI"} for r in rows], total)
    finally:
        con.close()


def _title_of(wid: str) -> str:
    con = sqlite3.connect(DB, timeout=10)
    try:
        row = con.execute("SELECT title FROM movies WHERE url=?",
                          (str(wid),)).fetchone()
        return row[0] if row else f"Swaplse {wid}"
    finally:
        con.close()


async def detail(url: str) -> dict:
    """1 karya = 1 video pendek (3-30 detik) — total episode selalu 1."""
    title = _title_of(url)
    return {"title": title, "url": url, "eps": {1: url}, "total": 1,
            "thumb": ""}


async def stream_url(ep_url: str) -> str:
    """MP4 direct di CDN — tanpa resolve, tanpa expire."""
    return f"https://cdn.swaplse.com/vitrina/w{ep_url}.mp4"


async def download(url: str, out: str) -> None:
    """Unduh MP4 direct (httpx stream)."""
    tmp = out + ".part"
    with httpx.Client(headers={"User-Agent": UA}, timeout=90,
                      follow_redirects=True, verify=False) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    os.replace(tmp, out)
