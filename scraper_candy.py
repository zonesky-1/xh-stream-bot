# language: Python 3.11, file: scraper_candy.py — Candy AI Shorts (seri porno AI)
#
# Fakta lapangan (hasil bedah, jangan diubah sembarangan):
# 1. candyshorts.com + sitemap = 200 DIRECT dari server (tanpa proxy).
# 2. private-cdn.candy.ai (video & poster) = GEO-BLOCK 403
#    ("not available in your area") → WAJIB lewat farm proxy user
#    (.ws_farm_proxies.txt) — terbukti tembus (200, video/mp4).
# 3. Struktur halaman series: tombol episode:
#      <button data-shorts--player-target="episode" data-number="N"
#        data-lock-state=""|="paywall"  data-video-url="…mp4" (hanya gratis)
#        data-poster-url="…webp">
#    free-episode-limit = 2 → EP 1-2 gratis, sisanya paywall (JANGAN dibypass).
# 4. Index lokal: index_candy.py (sitemap) → candy_index.db
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sqlite3
from typing import Callable, Optional

import httpx

log = logging.getLogger("candy")

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "candy_index.db")
PROXY_FILE = os.path.join(HERE, ".ws_farm_proxies.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HDRS = {"User-Agent": UA, "Referer": "https://candyshorts.com/"}


def _proxies() -> list[str]:
    try:
        with open(PROXY_FILE) as f:
            return [l.strip() for l in f if l.strip().startswith("http")]
    except OSError:
        return []


def _get(url: str, timeout: float = 40, proxy: str | None = None,
         **kw) -> httpx.Response:
    last: Exception | None = None
    for i in range(3):
        try:
            return httpx.get(url, headers=_HDRS, timeout=timeout,
                             follow_redirects=True, verify=False,
                             proxy=proxy, **kw)
        except Exception as e:
            last = e
            import time as _t
            _t.sleep(1.0 * (i + 1))
    raise last  # type: ignore[misc]


# ── search lokal (FTS5) — shape SERAGAM scraper_dracin.search ─────────────
def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    if not os.path.exists(DB):
        raise RuntimeError("index Candy belum jalan (index_candy.py)")
    con = sqlite3.connect(DB, timeout=10)
    try:
        n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        if n == 0:
            raise RuntimeError("index Candy kosong")
        offset = (page - 1) * per
        if not q.strip():
            rows = con.execute(
                "SELECT title, url FROM movies ORDER BY rowid "
                "LIMIT ? OFFSET ?", (per, offset)).fetchall()
            return ([{"title": r[0], "url": r[1], "thumb": "", "desc": "",
                      "provider": "candy"} for r in rows], n)
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
                  "provider": "candy"} for r in rows], total)
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


# ── detail: daftar EP (gratis vs paywall) ─────────────────────────────────
# Tombol episode MEMANJANG (multiline) dan ada '>' di dalam nilai atribut
# (data-action="click->shorts--player#switch") → regex [^>]* biasa motong tag
# sebelum data-number. Scan manual dengan tracking quote biar utuh.
def _ep_tags(page: str) -> list[str]:
    out: list[str] = []
    i = 0
    probe = 'data-shorts--player-target="episode"'
    while True:
        j = page.find(probe, i)
        if j < 0:
            break
        s = page.rfind("<button", 0, j)
        i = j + 1
        if s < 0:
            continue
        q: str | None = None
        end = -1
        k = s
        while k < len(page):
            c = page[k]
            if q:
                if c == q:
                    q = None
            elif c in "\"'":
                q = c
            elif c == ">":
                end = k
                break
            k += 1
        if end > 0:
            out.append(page[s:end + 1])
    return out


def parse_detail(url: str, page: str) -> dict:
    ti = re.search(r"<title>([^<]{3,160})</title>", page)
    title = ti.group(1).strip() if ti else ""
    title = re.sub(r"\s*[|\-]\s*Candy.*$", "", title, flags=re.I).strip() or title
    eps: list[dict] = []
    for tag in _ep_tags(page):
        num = re.search(r'data-number="(\d+)"', tag)
        if not num:
            continue
        lock = re.search(r'data-lock-state="([^"]*)"', tag)
        vid = re.search(r'data-video-url="([^"]+)"', tag)
        poster = re.search(r'data-poster-url="([^"]+)"', tag)
        eps.append({
            "n": int(num.group(1)),
            "free": bool(vid) and (lock is None or lock.group(1) == ""),
            "url": vid.group(1) if vid else "",
            "poster": poster.group(1) if poster else "",
        })
    eps.sort(key=lambda e: e["n"])
    return {"title": title, "url": url, "eps": eps,
            "total": max((e["n"] for e in eps), default=0),
            "free_n": sum(1 for e in eps if e["free"])}


async def detail(url: str) -> dict:
    def _run() -> dict:
        r = _get(url)                    # halaman series = direct, tanpa proxy
        r.raise_for_status()
        d = parse_detail(url, r.text)
        if not d["eps"]:
            raise RuntimeError("halaman series nggak punya daftar episode")
        return d
    return await asyncio.to_thread(_run)


# ── download: private-cdn GEO-BLOCK → putar farm proxy ───────────────────
async def download(mp4_url: str, out_path: str,
                   progress: Optional[Callable[[int, Optional[int]], None]] = None
                   ) -> tuple[str, bool]:
    """Stream MP4 via farm proxy (geo-block 403 → coba proxy sampai tembus).
    Balik (path, truncated=False)."""
    proxies = _proxies()
    if not proxies:
        raise RuntimeError("file proxy farm nggak ada (.ws_farm_proxies.txt)")
    random.shuffle(proxies)

    def _run() -> tuple[str, bool]:
        last_err = "proxy mati semua"
        for p in proxies[:10]:
            try:
                with httpx.Client(headers=_HDRS, timeout=90, verify=False,
                                  follow_redirects=True, proxy=p) as c:
                    with c.stream("GET", mp4_url) as r:
                        if r.status_code not in (200, 206):
                            last_err = f"HTTP {r.status_code} via proxy"
                            continue
                        total = int(r.headers.get("content-length") or 0) or None
                        done = 0
                        with open(out_path, "wb") as f:
                            for chunk in r.iter_bytes(chunk_size=1 << 16):
                                f.write(chunk)
                                done += len(chunk)
                                if progress and total:
                                    progress(done, total)
                if os.path.getsize(out_path) > 0:
                    log.info("candy unduh ok via %s: %.1f MB",
                             p.split("@")[-1], os.path.getsize(out_path) / 1048576)
                    if progress:
                        progress(os.path.getsize(out_path), total)
                    return out_path, False
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                try:
                    os.remove(out_path)
                except OSError:
                    pass
        raise RuntimeError(f"unduh gagal di semua proxy ({last_err[:160]})")

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
            print(f"title={d['title']}\ntotal={d['total']} free={d['free_n']}")
            for e in d["eps"][:6]:
                print(f"  EP {e['n']}: {'FREE' if e['free'] else 'paywall'}"
                      f" {e['url'][:80]}")
        elif cmd == "download":
            d = await detail(_s.argv[2])
            ep = int(_s.argv[3])
            e = next(x for x in d["eps"] if x["n"] == ep)
            if not e["free"]:
                print("EP itu paywall"); return
            p, _ = await download(e["url"], _s.argv[4])
            print("ok", p, os.path.getsize(p))
        else:
            print("usage: search|index|detail|download")

    _a.run(_main())
