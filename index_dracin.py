# language: Python 3.11, file: index_dracin.py
# Bangun index katalog dracinema dari sitemap video mereka:
#   /sitemap.xml → sitemaps/movies-N.xml (10k judul/file, ada <video:title>)
# Simpan ke SQLite FTS5 → search instan di bot tanpa query situs tiap kali.
# Jalan: python3 index_dracin.py  (bisa diulang — UPSERT; progress ke stdout)
from __future__ import annotations

import asyncio
import httpx
import logging
import random
import re
import sqlite3
import sys
import time

logging.disable(logging.INFO)
BASE = "https://www.dracinema.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
DB = "/home/agentuser/xh-bot/dracin_index.db"
PROXY_FILE = "/home/agentuser/xh-bot/.ws_farm_proxies.txt"
FALLBACK_FILE = "/home/agentuser/xh-bot/.dr_good_proxies"

RE_SITEMAP = re.compile(r"<loc>([^<]+movies-\d+\.xml)</loc>")
RE_ENTRY = re.compile(
    r"<url><loc>(?P<url>[^<]+)</loc>"
    r"(?:<lastmod>(?P<lastmod>[^<]*)</lastmod>)?"
    r".*?<video:title>(?P<title>[^<]*)</video:title>"
    r"(?:<video:description>(?P<desc>[^<]*)</video:description>)?"
    r"(?:<video:thumbnail_loc>(?P<thumb>[^<]*)</video:thumbnail_loc>)?",
    re.S)


def proxies_all() -> list[str]:
    out: list[str] = []
    for f in (PROXY_FILE, FALLBACK_FILE):
        try:
            with open(f) as fh:
                out += [l.strip() for l in fh if l.strip()]
        except OSError:
            pass
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


async def fetch(cands: list[str], url: str, tries: int = 24,
                timeout: float = 60) -> str | None:
    """GET lewat scraper_dracin._rotate (pool farm + batch kecil + marker).
    Kenapa delegasi: versi lokal punya kegagalan diam-diam yang nggak
    reproduksi di probe luar — jalur _rotate terbukti (playback smoke test)."""
    import scraper_dracin as D
    try:
        st, t = await D._rotate(url, tries=max(tries, 20),
                                timeout=min(timeout, 30), min_len=200,
                                want=lambda st, t: st == 200)
        return t if st == 200 else None
    except Exception as e:
        print(f"    fetch err {type(e).__name__}: {str(e)[:80]}", flush=True)
        return None


def ensure_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS movies(
        url TEXT PRIMARY KEY, title TEXT NOT NULL, desc TEXT,
        thumb TEXT, lastmod TEXT)""")
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS movies_fts
        USING fts5(title, desc, content='movies', content_rowid='rowid')""")
    # sinkron FTS via trigger — jangan REBUILD per file (120 file = 120x full scan)
    con.executescript("""
    CREATE TRIGGER IF NOT EXISTS movies_ai AFTER INSERT ON movies BEGIN
      INSERT INTO movies_fts(rowid, title, desc)
      VALUES (new.rowid, new.title, new.desc);
    END;
    CREATE TRIGGER IF NOT EXISTS movies_ad AFTER DELETE ON movies BEGIN
      INSERT INTO movies_fts(movies_fts, rowid, title, desc)
      VALUES ('delete', old.rowid, old.title, old.desc);
    END;
    CREATE TRIGGER IF NOT EXISTS movies_au AFTER UPDATE ON movies BEGIN
      INSERT INTO movies_fts(movies_fts, rowid, title, desc)
      VALUES ('delete', old.rowid, old.title, old.desc);
      INSERT INTO movies_fts(rowid, title, desc)
      VALUES (new.rowid, new.title, new.desc);
    END;
    """)
    return con


UPSERT = """INSERT INTO movies(url, title, desc, thumb, lastmod)
            VALUES(?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title,
              desc=excluded.desc, thumb=excluded.thumb, lastmod=excluded.lastmod"""


def ingest(con: sqlite3.Connection, xml: str) -> int:
    n = 0
    for m in RE_ENTRY.finditer(xml):
        g = m.groupdict()
        if not g["title"]:
            continue
        con.execute(UPSERT, (g["url"], g["title"], g["desc"] or "",
                             g["thumb"] or "", g["lastmod"] or ""))
        n += 1
    con.commit()
    return n


async def main() -> None:
    t0 = time.time()
    cands = proxies_all()
    if not cands:
        print("TIDAK ADA PROXY"); sys.exit(1)
    print(f"proxy kandidat: {len(cands)}", flush=True)

    idx = await fetch(cands, BASE + "/sitemap.xml", tries=20, timeout=18)
    if not idx:
        print("sitemap index GAGAL"); sys.exit(1)
    files = RE_SITEMAP.findall(idx)
    print(f"sitemap movies: {len(files)} file", flush=True)

    con = ensure_db()
    total = 0
    done_ok: set[str] = set()
    sem = asyncio.Semaphore(2)  # 2 file paralel — farm rate-limit kalau kebanyakan

    async def one(path: str, i: int):
        nonlocal total
        async with sem:
            # NB: <loc> di sitemap index = URL LENGKAP — jangan di-prepend BASE lagi
            # (bug dobel https://www.dracinema.comhttps://… = penyebab GAGAL total
            #  yang menyamar jadi "proxy mati")
            full = path if path.startswith("http") else BASE + path
            xml = await fetch(cands, full, tries=30, timeout=70)
            if not xml:
                print(f"  [{i}] GAGAL {path}", flush=True)
                return
            done_ok.add(path)
            n = ingest(con, xml)
            total += n
            print(f"  [{i}] {path}: {n} judul (total {total}) "
                  f"{time.time()-t0:.0f}s", flush=True)

    await asyncio.gather(*(one(p, i + 1) for i, p in enumerate(files)))

    # retry: file yang gagal dicoba ulang 3 ronde (proxy sekarat terus)
    fails = [p for p in files if p not in done_ok]
    for rnd in range(1, 4):
        if not fails:
            break
        print(f"--- ronde retry {rnd}: {len(fails)} file", flush=True)
        still = []
        for i, p in enumerate(fails):
            async with sem:
                full = p if p.startswith("http") else BASE + p
                xml = await fetch(cands, full, tries=40, timeout=75)
                if not xml:
                    still.append(p)
                    print(f"  gagal lagi {p}", flush=True)
                    continue
                n = ingest(con, xml)
                done_ok.add(p)
                total += n
                print(f"  OK {p}: {n} judul (total {total}) "
                      f"{time.time()-t0:.0f}s", flush=True)
                await asyncio.sleep(1.0)
        fails = still
        await asyncio.sleep(3)

    cnt = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"SELESAI: {total} baris dimasukkan, total unik di DB = {cnt} "
          f"({time.time()-t0:.0f}s) sisa_gagal={len(fails)}", flush=True)
    con.close()


if __name__ == "__main__":
    asyncio.run(main())
