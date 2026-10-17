# language: Python 3.11, file: scraper_drbest.py — dracin.best (sumber dracin KE-2)
#
# Fakta lapangan (hasil bedah E2E, jangan diubah sembarangan):
# 1. dracin.best DAN CDN video-v6.mydramawave.com TERBUKA direct dari server
#    (200) — TIDAK butuh proxy sama sekuali (berbeda dracinema.com/kom).
# 2. Alur: detail /<provider>/<slug> → link play /<provider>/play/<id>/<ep>
#    → <video data-stream-url="/api/proxy?url=<master.m3u8 ter-encode>">
#    → decode → master m3u8 DIRECT → variant → segment .mp4 direct.
# 3. Download: ffmpeg -c copy (master playlist → mux audio+video otomatis).
#    Bukti: EP 20.1MB / 1080x1920 / 18.5 detik / rc=0.
# 4. TANPA gate: EP 36/58 kebuka (dramabox), EP 15/81 (freereels) — nggak ada
#    login_required / vip_required di halaman play.
# 5. Index lokal: index_drbest.py (sitemap, 988 judul, direct) → drbest_index.db
from __future__ import annotations

import asyncio
import html as H
import logging
import os
import re
import sqlite3
import subprocess
from typing import Callable, Optional

import httpx

log = logging.getLogger("drbest")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://dracin.best"
DB = os.path.join(HERE, "drbest_index.db")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HDRS = {"User-Agent": UA, "Referer": BASE + "/"}


def _get(url: str, timeout: float = 60) -> httpx.Response:
    # halaman play suka lambat (server-side fetch stream di belakangnya)
    import time as _t
    last: Exception | None = None
    for i in range(3):
        try:
            return httpx.get(url, headers=_HDRS, timeout=timeout,
                             follow_redirects=True, verify=False)
        except Exception as e:  # ReadTimeout/ConnectError → coba lagi
            last = e
            _t.sleep(1.5 * (i + 1))
    raise last  # type: ignore[misc]


# ── search lokal (FTS5) — shape SERAGAM dg scraper_dracin.search ──────────
def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    if not os.path.exists(DB):
        raise RuntimeError("index dracin.best belum jadi (index_drbest.py)")
    con = sqlite3.connect(DB, timeout=10)
    try:
        n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        if n == 0:
            raise RuntimeError("index dracin.best kosong")
        offset = (page - 1) * per
        if not q.strip():
            rows = con.execute(
                "SELECT title, url, provider FROM movies "
                "ORDER BY rowid LIMIT ? OFFSET ?", (per, offset)).fetchall()
            return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                      "provider": r[2]} for r in rows], n)
        tokens = re.findall(r"[a-zA-Z0-9]+", q.lower())
        if not tokens:
            return [], 0
        match = " ".join(t + "*" for t in tokens)
        try:
            total = con.execute(
                "SELECT COUNT(*) FROM movies_fts WHERE movies_fts MATCH ?",
                (match,)).fetchone()[0]
            rows = con.execute(
                "SELECT m.title, m.url, m.provider FROM movies_fts f "
                "JOIN movies m ON m.rowid = f.rowid WHERE movies_fts MATCH ? "
                "ORDER BY bm25(movies_fts) LIMIT ? OFFSET ?",
                (match, per, offset)).fetchall()
        except sqlite3.OperationalError:
            like = "%" + q.strip().lower() + "%"
            total = con.execute(
                "SELECT COUNT(*) FROM movies WHERE LOWER(title) LIKE ?",
                (like,)).fetchone()[0]
            rows = con.execute(
                "SELECT title, url, provider FROM movies "
                "WHERE LOWER(title) LIKE ? LIMIT ? OFFSET ?",
                (like, per, offset)).fetchall()
        return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                  "provider": r[2]} for r in rows], total)
    finally:
        con.close()


def index_info() -> dict:
    if not os.path.exists(DB):
        return {"count": 0}
    con = sqlite3.connect(DB, timeout=10)
    try:
        return {"count": con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]}
    finally:
        con.close()


# ── detail: cover, jumlah episode, link play ──────────────────────────────
def parse_detail(url: str, page: str) -> dict:
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page)
    if not og:
        og = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', page)
    ti = re.search(r"<h1[^>]*>([^<]{3,140})</h1>", page)
    if not ti:
        ti = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page)
    de = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]{0,300})"', page)
    plays = sorted(set(re.findall(
        r'href=[\'"](/[^\'"]*?/play/[^\'"]*?/(\d+))[\'"]', page)))
    eps = max((int(e) for _, e in plays), default=0)
    ep_map = {int(e): p for p, e in plays}
    return {
        "title": H.unescape(ti.group(1)).strip() if ti else "",
        "thumb": H.unescape(og.group(1)) if og else "",
        "desc": H.unescape(de.group(1)).strip() if de else "",
        "eps": eps,
        "play": ep_map,          # {1: '/dramabox/play/420…/1', …}
    }


async def detail(url: str) -> dict:
    """Fetch halaman detail (direct, cepat) → {title, thumb, desc, eps, play}."""
    def _run() -> dict:
        r = _get(url)
        r.raise_for_status()
        return parse_detail(url, r.text)
    return await asyncio.to_thread(_run)


# ── stream: master m3u8 (decode data-stream-url) ──────────────────────────
def parse_stream(play_page: str) -> Optional[str]:
    """Halaman play → URL master m3u8 CDN asli (tanpa /api/proxy)."""
    m = re.search(r'data-stream-url="([^"]+)"', play_page)
    if not m:
        return None
    su = H.unescape(m.group(1))
    if "url=" in su:
        import urllib.parse as up
        return up.unquote(su.split("url=")[-1])
    return su if su.startswith("http") else BASE + su


async def stream_url(play_url: str) -> str:
    def _run() -> str:
        r = _get(BASE + play_url if play_url.startswith("/") else play_url)
        r.raise_for_status()
        u = parse_stream(r.text)
        if not u:
            raise RuntimeError("stream url nggak ketemu (mungkin halaman play basi)")
        return u
    return await asyncio.to_thread(_run)


async def download(master_m3u8: str, out_path: str,
                   progress: Optional[Callable[[int, Optional[int]], None]] = None
                   ) -> tuple[str, bool]:
    """ffmpeg -c copy master playlist → mp4 utuh (audio+video otomatis di-mux).
    Balikin (path, truncated=False). ~18.5s per EP 20MB (bukti E2E)."""
    def _run() -> tuple[str, bool]:
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-headers", f"User-Agent: {UA}\r\nReferer: {BASE}/\r\n",
               "-i", master_m3u8, "-c", "copy", "-bsf:a", "aac_adtstoasc",
               out_path]
        if progress:
            progress(0, None)  # sinyal mulai
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not os.path.isfile(out_path) \
                or os.path.getsize(out_path) == 0:
            raise RuntimeError("ffmpeg gagal: " + (p.stderr or "")[:240])
        if progress:
            progress(os.path.getsize(out_path), os.path.getsize(out_path))
        log.info("drbest unduh: %s %.1f MB", os.path.basename(out_path),
                 os.path.getsize(out_path) / 1048576)
        return out_path, False
    return await asyncio.to_thread(_run)


# ── CLI analisis ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio as _a
    import sys as _s
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _main():
        cmd = _s.argv[1] if len(_s.argv) > 1 else "help"
        if cmd == "search":
            items, total = search(" ".join(_s.argv[2:]), 1)
            print(f"total={total}")
            for it in items:
                print(" ", it["title"], "|", it["provider"], "|", it["url"])
        elif cmd == "index":
            print(index_info())
        elif cmd == "detail":
            d = await detail(_s.argv[2])
            print(f"title={d['title']}\neps={d['eps']}\nthumb={d['thumb'][:100]}"
                  f"\nplay contoh={list(d['play'].items())[:3]}")
        elif cmd == "ep":
            d = await detail(_s.argv[2])
            ep = int(_s.argv[3])
            u = await stream_url(d["play"][ep])
            print("master:", u[:160])
        elif cmd == "download":
            d = await detail(_s.argv[2])
            ep = int(_s.argv[3])
            u = await stream_url(d["play"][ep])
            p, _ = await download(u, _s.argv[4])
            print("ok", p, os.path.getsize(p))
        else:
            print("usage: search|index|detail|ep|download")

    _a.run(_main())
