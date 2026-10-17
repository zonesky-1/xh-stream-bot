# language: Python 3.11, file: index_ai2.py
# Index katalog Swaplse (swaplse.com) → SQLite FTS5 ai2_index.db
# API resmi (dinyatakan di robots.txt: Allow /api/vitrina/works):
#   GET /api/vitrina/works?offset=N  → {"works":[…40], "total":4806}
# Simpan kind=video saja; url = id kerja (mp4 = cdn.swaplse.com/vitrina/w<id>.mp4)
# Jalan: .venv/bin/python index_ai2.py (UPSERT, aman diulang)
from __future__ import annotations

import sqlite3
import time

import httpx

DB = "/home/agentuser/xh-bot/ai2_index.db"
API = "https://swaplse.com/api/vitrina/works"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PER = 40
DELAY = 0.25        # sopan — API publik, jangan digeber

UPSERT = """INSERT INTO movies(url, title, slug) VALUES(?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title,
              slug=excluded.slug"""


def ensure_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS movies(
        url TEXT PRIMARY KEY, title TEXT NOT NULL, slug TEXT)""")
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS movies_fts
        USING fts5(title, content='movies', content_rowid='rowid')""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS movies_ai AFTER INSERT ON movies
        BEGIN INSERT INTO movies_fts(rowid, title)
        VALUES(new.rowid, new.title); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS movies_ad AFTER DELETE ON movies
        BEGIN INSERT INTO movies_fts(movies_fts, rowid, title)
        VALUES('delete', old.rowid, old.title); END""")
    return con


def main() -> None:
    t0 = time.time()
    con = ensure_db()
    n = vid = 0
    offset = 0
    total = None
    with httpx.Client(headers={"User-Agent": UA}, timeout=30,
                      follow_redirects=True, verify=False) as c:
        while True:
            r = c.get(API, params={"offset": offset})
            r.raise_for_status()
            d = r.json()
            works = d.get("works", [])
            if total is None:
                total = int(d.get("total") or 0)
                print(f"total karya di API: {total}", flush=True)
            if not works:
                break
            for w in works:
                n += 1
                if w.get("kind") != "video":
                    continue
                title = (w.get("title_en") or w.get("title") or "").strip()
                if not title:
                    title = f"swaplse {w.get('id')}"
                con.execute(UPSERT, (str(w["id"]), title, ""))
                vid += 1
            offset += PER
            if offset >= total:
                break
            time.sleep(DELAY)
    con.commit()
    cnt = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"SELESAI: {n} karya dibaca, {vid} video diindex, "
          f"total unik = {cnt} ({time.time() - t0:.1f}s)", flush=True)
    con.close()


if __name__ == "__main__":
    main()
