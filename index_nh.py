# language: Python 3.11, file: index_nh.py
# Index katalog NontonHentai (nontonhentai.org) → SQLite FTS5 nh_index.db
# Fakta lapangan: WP search mati (0 hasil bahkan judul pasti) → WAJIB index lokal.
# Sitemap: anime-sitemap.xml + anime-sitemap2.xml = 1044 series /series/<slug>/.
# Series page SSR (episode link pattern: /<slug>-episode-N-subtitle-indonesia/).
# Jalan: .venv/bin/python index_nh.py (UPSERT, aman diulang)
from __future__ import annotations

import re
import sqlite3
import time

import httpx

DB = "/home/agentuser/xh-bot/nh_index.db"
SITEMAPS = ["https://nontonhentai.org/anime-sitemap.xml",
            "https://nontonhentai.org/anime-sitemap2.xml"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

RE_SERIES = re.compile(
    r"^https://nontonhentai\.org/series/([a-z0-9][a-z0-9-]{2,120})/$")

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
    con = ensure_db()
    n = 0
    for sm in SITEMAPS:
        r = httpx.get(sm, headers={"User-Agent": UA}, timeout=30,
                      follow_redirects=True, verify=False)
        r.raise_for_status()
        for u in re.findall(r"<loc>([^<]+)</loc>", r.text):
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
