# language: Python 3.11, file: scraper_nh.py — NontonHentai (hentai sub Indo)
#
# Fakta lapangan (hasil bedah 2026-10-09, jangan diubah sembarangan):
# 1. nontonhentai.org direct 200; WP search MATI (0 hasil) → search pakai index
#    lokal nh_index.db (index_nh.py dari sitemap, 1044 series).
# 2. Series page SSR → link episode:
#      https://nontonhentai.org/<slug>-episode-<N>-subtitle-indonesia/
# 3. Episode page → 1 iframe: https://nh.abhihi.xyz/embed/<uuid>
#    → config JWPlayer JSON (plain, ada di <script>): sources[0].file = m3u8
#      https://jv.abplay.store/nh/hls/<slug>/...m3u8  (200, direct)
# 4. Segment m3u8 bernama .html tapi ISI-nya MPEG-TS asli (0x47) + content-type
#    dispoof text/html → ffmpeg bodo amat. Download: ffmpeg -c copy
#    (Referer: embed) — pola sama persis scraper_drbest.
# 5. TANPA login, TANPA proxy.
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
from typing import Callable, Optional

import httpx

log = logging.getLogger("nh")

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "nh_index.db")
BASE = "https://nontonhentai.org"
EMBED_HOST = "nh.abhihi.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _get(url: str, timeout: float = 40, referer: str | None = None) -> httpx.Response:
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    last: Exception | None = None
    for i in range(3):
        try:
            return httpx.get(url, headers=h, timeout=timeout,
                             follow_redirects=True, verify=False)
        except Exception as e:
            last = e
            import time as _t
            _t.sleep(1.0 * (i + 1))
    raise last  # type: ignore[misc]


# ── search lokal (FTS5) — shape SERAGAM scraper_dracin.search ─────────────
def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    if not os.path.exists(DB):
        raise RuntimeError("index NontonHentai belum jalan (index_nh.py)")
    con = sqlite3.connect(DB, timeout=10)
    try:
        n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        if n == 0:
            raise RuntimeError("index NontonHentai kosong")
        offset = (page - 1) * per
        if not q.strip():
            rows = con.execute(
                "SELECT title, url FROM movies ORDER BY rowid "
                "LIMIT ? OFFSET ?", (per, offset)).fetchall()
            return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                      "provider": "NontonHentai"} for r in rows], n)
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
                  "provider": "NontonHentai"} for r in rows], total)
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


# ── detail: series → daftar episode ───────────────────────────────────────
RE_EP = re.compile(
    r'href="(https://nontonhentai\.org/([a-z0-9-]+)-episode-(\d+)'
    r'-subtitle-indonesia/)"')


def parse_detail(url: str, page: str) -> dict:
    ti = re.search(r"<title>([^<]{3,160})</title>", page)
    title = ti.group(1).strip() if ti else ""
    title = re.sub(r"\s*[|\-]\s*NontonHentai.*$", "", title, flags=re.I).strip() \
        or title
    eps: dict[int, str] = {}
    for full, slug, num in RE_EP.findall(page):
        eps[int(num)] = full
    # cover (og:image) — boleh kosong
    cov = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page) \
        or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', page)
    return {"title": title, "url": url, "eps": eps,
            "total": max(eps, default=0),
            "thumb": cov.group(1) if cov else ""}


async def detail(url: str) -> dict:
    def _run() -> dict:
        r = _get(url)
        r.raise_for_status()
        d = parse_detail(url, r.text)
        if not d["eps"]:
            raise RuntimeError("halaman series nggak punya daftar episode")
        return d
    return await asyncio.to_thread(_run)


# ── stream: ep page → iframe embed → JWPlayer config → m3u8 ───────────────
RE_IFRAME = re.compile(r'<iframe[^>]+src="(https?://[^"]+)"')
RE_CONFIG = re.compile(r"var config = (\{.*?\});", re.S)


def parse_stream(ep_page: str) -> str:
    m = RE_IFRAME.search(ep_page)
    if not m:
        raise RuntimeError("episode nggak punya player embed")
    return m.group(1)


async def stream_url(ep_url: str) -> str:
    """Episode page → embed → m3u8 master. Tanpa login, tanpa proxy."""
    def _run() -> str:
        r = _get(ep_url)
        r.raise_for_status()
        embed = parse_stream(r.text)
        # JWPlayer config di embed = JSON plain (bukan XOR)
        e = _get(embed, referer=BASE)
        e.raise_for_status()
        cm = RE_CONFIG.search(e.text)
        if not cm:
            raise RuntimeError("config player nggak ketemu")
        try:
            cfg = json.loads(cm.group(1))
        except json.JSONDecodeError as ex:
            raise RuntimeError(f"config player bukan JSON: {ex}")
        srcs = cfg.get("sources") or []
        if not srcs or not srcs[0].get("file"):
            raise RuntimeError("sumber video kosong di config")
        return srcs[0]["file"]
    return await asyncio.to_thread(_run)


# ── download: ffmpeg -c copy dari m3u8 (segment TS dispoof content-type) ──
async def download(master_m3u8: str, out_path: str,
                   progress: Optional[Callable[[int, Optional[int]], None]] = None
                   ) -> tuple[str, bool]:
    def _run() -> tuple[str, bool]:
        # Referer = host embed → jv.abplay ngecek; segment .html = TS asli
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-headers", f"User-Agent: {UA}\r\nReferer: https://{EMBED_HOST}/\r\n",
               "-i", master_m3u8, "-c", "copy", "-bsf:a", "aac_adtstoasc",
               out_path]
        if progress:
            progress(0, None)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if p.returncode != 0 or not os.path.isfile(out_path) \
                or os.path.getsize(out_path) == 0:
            raise RuntimeError("ffmpeg gagal: " + (p.stderr or "")[:240])
        if progress:
            progress(os.path.getsize(out_path), os.path.getsize(out_path))
        log.info("nh unduh: %s %.1f MB", os.path.basename(out_path),
                 os.path.getsize(out_path) / 1048576)
        return out_path, False
    return await asyncio.to_thread(_run)


# ── CLI ───────────────────────────────────────────────────────────────────
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
                print(" ", it["title"], "|", it["url"])
        elif cmd == "index":
            print(index_info())
        elif cmd == "detail":
            d = await detail(_s.argv[2])
            print(f"title={d['title']}\ntotal={d['total']} eps={d['eps']}")
        elif cmd == "stream":
            print(await stream_url(_s.argv[2]))
        elif cmd == "download":
            m = await stream_url(_s.argv[2])
            p, _ = await download(m, _s.argv[3])
            print("ok", p, os.path.getsize(p))
        else:
            print("usage: search|index|detail|stream|download")

    _a.run(_main())
