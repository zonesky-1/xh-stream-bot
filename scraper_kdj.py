# language: Python 3.11, file: scraper_kdj.py
# KomikDoujin (komikdoujin.com) — komik doujin berbahasa Indonesia.
# Kontrak modul manhwa (sama dgn scraper_hentai/scraper_indo):
#   search(q, page) → GalleryPage ; gallery(url) → GalleryDetail
# Sumber data:
#   • search/daftar: REST  /wp-json/wp/v2/komik_series?search=…&_embed=1
#   • daftar chapter : link RELATIF /chapter/… di HTML halaman series
#   • isi chapter    : REST  /wp-json/wp/v2/komik_chapter?slug=… (content)
#     gambar = webp di pic.gudangkomik.top — buang watermark wm-*.jpg
from __future__ import annotations

import asyncio
import logging
import math
import re

import httpx

from scraper_hentai import (Gallery, GalleryDetail, GalleryPage,  # noqa: F401
                            zip_files)
# mesin unduh halaman sudah generik (jalan dari detail.page_urls) — pakai
# punya scraper_indo apa adanya (Referer = url detail, cocok utk kdj juga)
from scraper_indo import download_pages  # noqa: F401

log = logging.getLogger("scraper_kdj")
BASE = "https://komikdoujin.com"
API = BASE + "/wp-json/wp/v2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
PER_PAGE = 20
MAX_CHAPTERS = 30        # batas chapter digabung (waktu + ukuran zip)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "id-ID,id;q=0.9"},
        follow_redirects=True, timeout=30)


async def search(q: str = "", page: int = 1) -> GalleryPage:
    q = (q or "").strip()
    # NB: jangan pakai _fields bareng _embed — featuredmedia ikut kepotong
    params: dict = {"per_page": PER_PAGE, "page": page, "_embed": "1"}
    if q:
        params["search"] = q
    async with _client() as c:
        r = await c.get(f"{API}/komik_series", params=params)
        r.raise_for_status()
        total = int(r.headers.get("X-WP-Total") or 0)
        data = r.json()
    items = []
    for i, d in enumerate(data):
        thumb = ""
        emb = d.get("_embedded", {}).get("wp:featuredmedia") or []
        if emb:
            thumb = emb[0].get("source_url", "") or ""
        items.append(Gallery(
            idx=(page - 1) * PER_PAGE + i + 1,
            title=re.sub(r"<[^>]+>", "", d.get("title", {}).get("rendered", "")),
            url=d.get("link", ""), cat="komik Indonesia", thumb=thumb))
    max_pages = max(1, math.ceil(total / PER_PAGE)) if total else 1
    return GalleryPage(query=q, page=page, max_pages=min(max_pages, 200),
                       items=items)


_RE_CH = re.compile(r'href="(?:https://komikdoujin\.com)?(/chapter/[^"]+)"')


async def _chapter_images(c: httpx.AsyncClient, ch_url: str) -> list[str]:
    """Gambar webp satu chapter via REST (slug dari URL). Lewati watermark."""
    slug = ch_url.rstrip("/").rsplit("/", 1)[-1]
    r = await c.get(f"{API}/komik_chapter",
                    params={"slug": slug, "_fields": "content"})
    r.raise_for_status()
    data = r.json()
    if not data:
        return []
    html = data[0].get("content", {}).get("rendered", "")
    urls: list[str] = []
    for u in re.findall(r'<img[^>]+src="([^"]+)"', html):
        name = u.rsplit("/", 1)[-1].lower()
        if name.startswith("wm-"):      # watermark promo — buang
            continue
        if "wp-content/uploads" in u and not u.startswith("http"):
            u = BASE + u
        urls.append(u)
    return urls


async def gallery(url: str) -> GalleryDetail:
    """Detail series: semua chapter (terurut) digabung jadi satu bacaan
    maraton — persis pola scraper_indo."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        html = r.text
        mt = re.search(r"<title>([^<]+)</title>", html)
        title = mt.group(1).split("–")[0].split("|")[0].strip() if mt else slug
        mcover = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        cover = mcover.group(1) if mcover else ""
        chapters = list(dict.fromkeys(_RE_CH.findall(html)))
        # HTML = terbaru dulu → balik buat urutan baca
        chapters = [BASE + u for u in reversed(chapters)][:MAX_CHAPTERS]
        if not chapters:
            raise RuntimeError("daftar chapter nggak ketemu di halaman series")
        batches = await asyncio.gather(
            *(_chapter_images(c, u) for u in chapters),
            return_exceptions=True)
        page_urls: list[str] = []
        n_ch_ok = 0
        for ch, b in zip(chapters, batches):
            if isinstance(b, Exception):
                log.warning("chapter %s gagal: %s", ch, str(b)[:80])
                continue
            n_ch_ok += 1
            page_urls.extend(b)
        if not page_urls:
            raise RuntimeError("semua chapter gagal / kosong")
        log.info("kdj %s: %d chapter → %d gambar", slug, n_ch_ok, len(page_urls))
    return GalleryDetail(title=title, url=url, cover=cover,
                         pages=len(page_urls), page_urls=page_urls,
                         tags=[f"{n_ch_ok} chapter", "doujin Indonesia"])
