# language: Python 3.11, file: index_candy.py
# Index katalog Candy AI Shorts (candyshorts.com) → SQLite FTS5 candy_index.db
# Fakta lapangan: sitemap 810 URL (multi-lokasi) → filter hanya /series/<slug>
# EN. Halaman series TANPA blokir (200 direct); yang diblokir geo cuma
# private-cdn (video/poster) → download nanti lewat farm proxy.
# Jalan: .venv/bin/python index_candy.py (UPSERT, aman diulang)
from __future__ import annotations

import re
import sqlite3
import time

import httpx

DB = "/home/agentuser/xh-bot/candy_index.db"
SITEMAP = "https://candyshorts.com/sitemap.xml"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

RE_SERIES = re.compile(r"^https://candyshorts\.com/series/([a-z0-9][a-z0-9-]{2,80})$")

UPSERT = """INSERT INTO movies(url, title, slug) VALUES(?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title,
              slug=excluded.slug"""


def slug_to_title(slug: str) -> str:
    s = slug.replace("-", " ").strip()
    return s.title() if s.islower() else s


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
    r = httpx.get(SITEMAP, headers={"User-Agent": UA}, timeout=30,
                  follow_redirects=True, verify=False)
    r.raise_for_status()
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    con = ensure_db()
    n = 0
    for u in locs:
        m = RE_SERIES.match(u)
        if not m:
            continue
        slug = m.group(1)
        con.execute(UPSERT, (u, slug_to_title(slug), slug))
        n += 1
    con.commit()
    cnt = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"SELESAI: {n} series diproses, total unik = {cnt} "
          f"({time.time() - t0:.1f}s)", flush=True)
    con.close()


if __name__ == "__main__":
    main()
