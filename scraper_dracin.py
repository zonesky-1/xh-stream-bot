# language: Python 3.11, file: scraper_dracin.py — dracinema (dracin / drama China sub Indo)
#
# Fakta lapangan (jangan diubah sembarangan — ini hasil bedah, bukan tebakan):
# 1. www.dracinema.com ngeblok IP server: Cloudflare 1020 (WAF) — SEMUA path
#    (HTML, robots, /api/*) dibales "Sorry, you have been blocked". BUKAN
#    challenge → nggak bisa diselesaiin client-side → HARUS lewat proxy.
# 2. Proxy utama = .ws_farm_proxies.txt (milik user, user:pass@host:port),
#    cadangan = .dr_good_proxies (pernah terbukti) + GitHub proxy-lists.
#    Farm user RATE-LIMIT kalau diborosin → batch kecil (4) + jeda.
# 3. Video: POST /api/playback {movieKey, episode} + header X-API-Key
#    (secret hardcode di chunk JS 9437 — axios interceptor mereka). Tanpa header
#    ini origin Caddy balas 403 {"success":false,"error":"Access denied"}.
#    Respons: {token: JWT} → payload base64 = {kind, data:{meta, detail:{videoUrls}},
#    subtitle: WEBVTT}. Ep 1-5 kind="ok" (gratis); ep 6+ kind="login_required".
# 4. MP4 di cdn.playsverse.com TIDAK diblok → download DIRECT tanpa proxy
#    (500KB/0.78s). auth_key di URL singkat → SELALU playback() dulu, jangan cache.
# 5. Search: index lokal FTS5 (index_dracin.py, dari sitemap video mereka ±190rb
#    judul). Search server-side situsnya MATI — semua query balikin grid default.
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import re
import sqlite3
import time
import warnings
from typing import Callable, Optional

import httpx

warnings.filterwarnings("ignore")
log = logging.getLogger("dracin")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://www.dracinema.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
API_KEY = "xb3MdwdLrZrpaDXvrLLwfP=="        # rahasia dari interceptor axios mereka
DB = os.path.join(HERE, "dracin_index.db")
FARM_FILE = os.path.join(HERE, ".ws_farm_proxies.txt")
GOOD_FILE = os.path.join(HERE, ".dr_good_proxies")

_PROXY_LISTS = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/Clarketm/proxy-list/master/proxy-list-raw.txt",
]

_pool: list[str] = []
_pool_at = 0.0
_good: list[str] = []
_TTL_POOL = 1800.0


def _good_load() -> None:
    global _good
    if _good:
        return
    _good = []
    for f in (GOOD_FILE, FARM_FILE):
        try:
            with open(f) as fh:
                _good += [l.strip() for l in fh if l.strip()]
        except OSError:
            pass


def _good_save(p: str) -> None:
    if p in _good:
        return
    _good.append(p)
    try:
        with open(GOOD_FILE, "w") as fh:
            fh.write("\n".join(_good[-40:]))
    except OSError:
        pass


async def _load_pool() -> None:
    global _pool, _pool_at
    _good_load()
    if _pool and (time.time() - _pool_at) < _TTL_POOL:
        return
    pool: list[str] = []
    # 1) farm user — sumber utama
    try:
        with open(FARM_FILE) as fh:
            pool += [l.strip() for l in fh if l.strip()]
    except OSError:
        pass
    # 2) github lists — cadangan
    if len(pool) < 20:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                     headers={"User-Agent": UA}) as c:
            for u in _PROXY_LISTS:
                try:
                    r = await c.get(u)
                    if r.status_code == 200:
                        pool += [p.strip() for p in r.text.split() if p.strip()]
                except Exception:
                    continue
    seen: list[str] = []
    for p in pool:
        p = p if "://" in p else "http://" + p
        if p not in seen:
            seen.append(p)
    random.shuffle(seen)
    _pool = seen[:240]
    _pool_at = time.time()
    log.info("pool proxy: %d kandidat", len(_pool))


async def _try_one(proxy: str, url: str, timeout: float = 15,
                   min_len: int = 300, method: str = "GET",
                   json_body: dict | None = None) -> tuple[int, str] | None:
    try:
        async with httpx.AsyncClient(proxy=proxy, headers={"User-Agent": UA},
                                     timeout=timeout, follow_redirects=True,
                                     verify=False) as c:
            if method == "GET":
                r = await c.get(url)
            else:
                r = await c.post(url, json=json_body,
                                 headers={"Content-Type": "application/json",
                                          "Origin": BASE, "Referer": BASE + "/",
                                          "X-API-Key": API_KEY})
            t = r.text
            if "been blocked" in t or "Just a moment" in t:
                return None           # CF block / challenge → proxy ini lolos WAF
            if len(t) >= min_len:
                return (r.status_code, t)
    except Exception:
        pass
    return None


async def _rotate(url: str, tries: int = 30, timeout: float = 15,
                  min_len: int = 300, method: str = "GET",
                  json_body: dict | None = None,
                  want: Callable[[int, str], bool] | None = None
                  ) -> tuple[int, str]:
    """Coba proxy (batch 4 paralel) sampai respons memenuhi predikat want()."""
    await _load_pool()
    if not _pool:
        raise RuntimeError("proxy pool kosong")
    ordered: list[str] = []
    if _good:
        ordered += random.sample(_good, k=min(len(_good), 8))
    ordered += [p for p in random.sample(_pool, k=min(len(_pool), max(tries, 20)))
                if p not in ordered]
    sem = asyncio.Semaphore(4)

    async def one(p: str):
        async with sem:
            return p, await _try_one(p, url, timeout, min_len, method, json_body)

    for start in range(0, len(ordered), 4):
        res = await asyncio.gather(*(one(p) for p in ordered[start:start + 4]))
        for p, out in res:
            if out is None:
                continue
            st, t = out
            if want is None or want(st, t):
                _good_save(p)
                return st, t
        await asyncio.sleep(0.3)
    raise RuntimeError("proxy mati semua untuk " + url)


async def fetch(url: str, tries: int = 30, timeout: float = 16,
                min_len: int = 500) -> str:
    """Ambil HTML halaman dracinema lewat proxy pool."""
    _, t = await _rotate(url, tries=tries, timeout=timeout, min_len=min_len,
                         want=lambda st, t: st == 200)
    return t


# ── search lokal (FTS5) — instan, tanpa jaringan ───────────────────────────
def search(q: str, page: int = 1, per: int = 10) -> tuple[list[dict], int]:
    if not os.path.exists(DB):
        raise RuntimeError("index dracinema belum jadi")
    con = sqlite3.connect(DB, timeout=10)
    try:
        n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        if n == 0:
            raise RuntimeError("index masih kosong — tunggu build selesai")
        offset = (page - 1) * per
        if not q.strip():
            rows = con.execute(
                "SELECT title, url, thumb, desc FROM movies "
                "ORDER BY lastmod DESC LIMIT ? OFFSET ?",
                (per, offset)).fetchall()
            return ([{"title": r[0], "url": r[1], "thumb": r[2], "desc": r[3] or ""}
                     for r in rows], n)
        tokens = re.findall(r"[a-zA-Z0-9]+", q.lower())
        if not tokens:
            return [], 0
        match = " ".join(t + "*" for t in tokens)
        try:
            total = con.execute(
                "SELECT COUNT(*) FROM movies_fts WHERE movies_fts MATCH ?",
                (match,)).fetchone()[0]
            rows = con.execute(
                "SELECT m.title, m.url, m.thumb, m.desc FROM movies_fts f "
                "JOIN movies m ON m.rowid = f.rowid "
                "WHERE movies_fts MATCH ? "
                "ORDER BY bm25(movies_fts) LIMIT ? OFFSET ?",
                (match, per, offset)).fetchall()
        except sqlite3.OperationalError:
            like = "%" + q.strip().lower() + "%"
            total = con.execute(
                "SELECT COUNT(*) FROM movies WHERE LOWER(title) LIKE ?",
                (like,)).fetchone()[0]
            rows = con.execute(
                "SELECT title, url, thumb, desc FROM movies "
                "WHERE LOWER(title) LIKE ? LIMIT ? OFFSET ?",
                (like, per, offset)).fetchall()
        return ([{"title": r[0], "url": r[1], "thumb": r[2], "desc": r[3] or ""}
                 for r in rows], total)
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


def movie_key(url: str) -> str:
    """/movie/<slug> → <slug> (jadi movieKey utk playback)."""
    m = re.search(r"/movie/([^/?#]+)", url)
    if not m:
        raise ValueError("bukan url movie: " + url)
    return m.group(1)


def eps_range(desc: str) -> tuple[int, int]:
    """'…episode 1-60 gratis…' → (1, 60). Gagal → (1, 1)."""
    m = re.search(r"episode\s+(\d+)\s*-\s*(\d+)", desc or "", re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1, 1


# ── playback: URL video + subtitle ─────────────────────────────────────────
def _b64_json(segment: str) -> dict:
    segment += "=" * (4 * (-len(segment) % 4))
    return json.loads(base64.urlsafe_b64decode(segment))


async def playback(key: str, episode: int) -> dict:
    """POST /api/playback → token ter-decode.

    {kind: 'ok'|'login_required'|…, data:{meta, detail:{videoUrls}},
     subtitle: WEBVTT|None, providerCode}
    """
    body = {"movieKey": key, "episode": episode}
    st, t = await _rotate(
        BASE + "/api/playback", tries=34, timeout=14, min_len=40,
        method="POST", json_body=body,
        want=lambda st, t: st == 200 and "token" in t)
    if st != 200:
        raise RuntimeError(f"playback HTTP {st}: {t[:120]}")
    return _b64_json(json.loads(t)["token"].split(".")[1])


def pick_video(d: dict) -> Optional[dict]:
    """videoUrl terbaik dari playback; kind != ok → None."""
    if d.get("kind") != "ok":
        return None
    vurls = ((d.get("data") or {}).get("detail") or {}).get("videoUrls") or []
    if not vurls:
        return None
    return max(vurls, key=lambda v: (v.get("quality") or 0))


# ── download MP4: DIRECT tanpa proxy ───────────────────────────────────────
async def download_mp4(url: str, out_path: str,
                       progress: Optional[Callable[[int, Optional[int]], None]] = None,
                       max_bytes: Optional[int] = None) -> tuple[str, bool]:
    """Stream MP4 dari cdn.playsverse. Balikin (path, truncated)."""
    headers = {"User-Agent": UA, "Referer": BASE + "/"}
    got = 0
    truncated = False
    async with httpx.AsyncClient(headers=headers, timeout=90,
                                 follow_redirects=True, verify=False) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            cl = r.headers.get("content-length")
            total = int(cl) if cl and cl.isdigit() else None
            with open(out_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    if max_bytes is not None and got + len(chunk) > max_bytes:
                        chunk = chunk[: max(0, max_bytes - got)]
                        truncated = True
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, total)
                    if truncated:
                        break
    if got == 0:
        raise RuntimeError("download kosong (0 byte)")
    log.info("dracin unduh: %s %.1f MB%s", os.path.basename(out_path),
             got / 1048576, " (dipotong)" if truncated else "")
    return out_path, truncated


# ── CLI analisis ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async def _main():
        cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
        if cmd == "search":
            items, total = search(" ".join(sys.argv[2:]), 1)
            print(f"total={total}")
            for it in items:
                print(" ", it["title"], "|", it["url"])
        elif cmd == "index":
            print(index_info())
        elif cmd == "playback":
            d = await playback(sys.argv[2], int(sys.argv[3]))
            v = pick_video(d)
            print("kind:", d.get("kind"))
            print("quality:", (v or {}).get("quality"))
            print("url:", (v or {}).get("url", "")[:140])
            print("subtitle:", bool(d.get("subtitle")))
        elif cmd == "download":
            p, tr = await download_mp4(sys.argv[2], sys.argv[3])
            print("ok", p, os.path.getsize(p), "truncated:", tr)
        elif cmd == "fetch":
            t = await fetch(sys.argv[2])
            print(len(t), "bytes\n", t[:800])
        else:
            print("usage: search|index|playback|download|fetch")

    asyncio.run(_main())
