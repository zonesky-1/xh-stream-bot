# language: Python 3.11, file: index_drbest.py
# Index katalog dracin.best — TANPA PROXY (langsung dari server, dibuktiin probe):
#   /sitemap.xml (204KB, ~988 URL drama) → judul dari slug (/provider/judul-12digit)
# Simpan ke SQLite FTS5 drbest_index.db. Jalan: .venv/bin/python index_drbest.py
# (aman diulang — UPSERT; jalankan periodik buat refresh katalog)
from __future__ import annotations

import re
import sqlite3
import time

import httpx

DB = "/home/agentuser/xh-bot/drbest_index.db"
SITEMAP = "https://dracin.best/sitemap.xml"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# URL drama: /<provider>/<slug atau id> — id bisa campur besar/kecil (freereels
# pake code kayak gQGLPtHjNY) dan nggak selalu ada suffix numerik
RE_DRAMA = re.compile(
    r"https://dracin\.best/([a-z0-9-]{3,25})/([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)/?$")

UPSERT = """INSERT INTO movies(url, title, provider, desc) VALUES(?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title,
              provider=excluded.provider, desc=excluded.desc"""
EXCLUDE_PATHS = ("genre", "genres", "platform", "platforms", "popular",
                 "cari", "search", "api", "about")


def slug_to_title(slug: str) -> str:
    # buang suffix id numerik: "…-42000012744", "…-2952" (bukan tahun 19xx/20xx)
    s = re.sub(r"-(?!(?:19|20)\d{2}$)\d{3,}$", "", slug)
    s = s.replace("-", " ").strip()
    return s.title() if s.islower() else s


def ensure_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS movies(
        url TEXT PRIMARY KEY, title TEXT NOT NULL, provider TEXT, desc TEXT)""")
    con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS movies_fts
        USING fts5(title, provider, content='movies', content_rowid='rowid')""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS movies_ai AFTER INSERT ON movies
        BEGIN INSERT INTO movies_fts(rowid, title, provider)
        VALUES(new.rowid, new.title, new.provider); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS movies_ad AFTER DELETE ON movies
        BEGIN INSERT INTO movies_fts(movies_fts, rowid, title, provider)
        VALUES('delete', old.rowid, old.title, old.provider); END""")
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
        m = RE_DRAMA.match(u.rstrip("/"))
        if not m:
            continue
        provider, slug = m.group(1), m.group(2)
        if provider in EXCLUDE_PATHS:
            continue
        con.execute(UPSERT, (u, slug_to_title(slug), provider, slug))
        n += 1
    con.commit()
    cnt = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"SELESAI: {n} url diproses, total unik di DB = {cnt} "
          f"({time.time() - t0:.1f}s)", flush=True)
    con.close()


if __name__ == "__main__":
    main()
