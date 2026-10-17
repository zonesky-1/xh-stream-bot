# language: Python 3.11, file: scraper_hentai.py, target: HentaiFox (manhwa/manga/doujin) + helper hentai xHamster
from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

log = logging.getLogger("scraper_hentai")

BASE = "https://hentaifox.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
RESULTS_PER_PAGE = 20  # 8 thumb/kelihatan per page di HTML server-side; dipakai buat estimasi nav


@dataclass
class Gallery:
    idx: int
    title: str
    url: str
    cat: str = ""
    thumb: str = ""


@dataclass
class GalleryPage:
    query: str
    page: int
    max_pages: int
    items: list = field(default_factory=list)


@dataclass
class GalleryDetail:
    title: str
    url: str
    cover: str
    pages: int
    page_urls: list = field(default_factory=list)
    tags: list = field(default_factory=list)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                 "Referer": BASE + "/"},
        follow_redirects=True, timeout=30,
    )


def _search_url(q: str, page: int) -> str:
    slug = re.sub(r"\s+", "+", q.strip()).lower()
    url = f"{BASE}/search/?q={slug}"
    if page > 1:
        url += f"&page={page}"
    return url


async def search(q: str, page: int = 1) -> GalleryPage:
    """Cari gallery di HentaiFox. Default q='manhwa' kalau kosong (dipanggil bot)."""
    from bs4 import BeautifulSoup
    q = q or "manhwa"
    url = _search_url(q, page)
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        html = r.text
    soup = BeautifulSoup(html, "lxml")
    items: list[Gallery] = []
    seen: set[str] = set()
    for div in soup.select("div.lc_galleries div.thumb"):
        a = div.select_one("div.inner_thumb a[href*='/gallery/']")
        if not a:
            continue
        href = (a.get("href") or "").split("?")[0]
        if not href or href in seen:
            continue
        seen.add(href)
        title_el = div.select_one("div.caption h2 a")
        title = (title_el.get_text(strip=True) if title_el else "") or href
        cat_el = div.select_one("div.g_type a")
        cat = cat_el.get_text(strip=True) if cat_el else ""
        img = div.select_one("div.inner_thumb img")
        thumb = (img.get("data-src") or img.get("src") or "") if img else ""
        if thumb.startswith("data:"):
            thumb = ""
        items.append(Gallery(idx=len(items) + 1, title=title, url=BASE + href,
                             cat=cat, thumb=thumb))
    # pagination: link /page/N/ atau /pag/N/ di halaman
    pages = [int(n) for n in re.findall(r"(?:page|pag)/(\d+)/", html)]
    max_pages = max(pages) if pages else 1
    if page > max_pages:
        page = max_pages
    return GalleryPage(query=q, page=page, max_pages=max_pages, items=items)


def _full_from_thumb(thumb_url: str) -> str:
    """Nt.jpg -> N (base tanpa ekstensi — ekstensi full-res campur jpg/png/webp,
    jadi dipilih pas download dengan coba satu-satu)."""
    return re.sub(r"(\d+)t\.\w+$", r"\1", thumb_url)


async def gallery(url: str) -> GalleryDetail:
    """Detail gallery: cover, jumlah halaman, URL halaman full-res."""
    from bs4 import BeautifulSoup
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        html = r.text
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else url
    title = re.sub(r"\s*-\s*(HentaiFox|manhwa|manga).*$", "", title, flags=re.I).strip() or url
    cover = ""
    page_urls: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if "hentaifox.com" not in src or src.startswith("data:"):
            continue
        if src.startswith("//"):
            src = "https:" + src
        if src.endswith("/cover.jpg"):
            cover = src
        elif re.search(r"/\d+t\.\w+$", src):
            page_urls.append(_full_from_thumb(src))
    # urutkan numerik (subdomain bisa beda-beda per page, sort by nomor halaman)
    def pnum(u: str) -> int:
        m = re.search(r"/(\d+)$", u)
        return int(m.group(1)) if m else 0
    page_urls = sorted(set(page_urls), key=pnum)
    if not cover and page_urls:
        base = re.sub(r"/\d+$", "", page_urls[0])
        cover = base + "/cover.jpg"
    tags = []
    for m in re.finditer(r'href="/(?:tags|parodies|artists|characters|groups)/[^"]+"[^>]*>([^<]+)<', html):
        t = m.group(1).strip()
        if t and len(t) < 40:
            tags.append(t)
    return GalleryDetail(title=title, url=url, cover=cover, pages=len(page_urls),
                         page_urls=page_urls, tags=list(dict.fromkeys(tags))[:15])


async def download_pages(detail: GalleryDetail, out_dir: str,
                         start: int = 0, limit: Optional[int] = None,
                         progress: Optional[Callable[[int, int], None]] = None,
                         max_bytes: Optional[int] = None) -> tuple[list[str], bool]:
    """Unduh halaman (0-index). Balik (list file, truncated?) — berhenti kalau max_bytes kelewatan."""
    os.makedirs(out_dir, exist_ok=True)
    urls = detail.page_urls[start:]
    if limit:
        urls = urls[:limit]
    if not urls:
        raise RuntimeError("gallery nggak punya halaman yang bisa diunduh")
    gid = re.sub(r"[^\w-]", "_", detail.url.rsplit("/", 2)[-2])
    files: list[str] = []
    truncated = False
    total = 0
    sem = asyncio.Semaphore(6)

    async with _client() as c:
        async def one(i: int, u: str):
            nonlocal truncated, total
            async with sem:
                if truncated:
                    return
                # ekstensi full-res campur (jpg/png/webp) — coba sampai ketemu
                rr = None
                ext = ".jpg"
                for e in (".jpg", ".png", ".webp"):
                    try:
                        r2 = await c.get(u + e)
                    except httpx.HTTPError:
                        continue
                    if r2.status_code == 200 and (r2.headers.get("content-type") or "").startswith("image"):
                        rr, ext = r2, e
                        break
                if rr is None:
                    log.warning("halaman %d nggak bisa diunduh: %s", i + 1, u)
                    return
                path = os.path.join(out_dir, f"{gid}_{i + 1:03d}{ext}")
                data = rr.content
                if max_bytes is not None and total + len(data) > max_bytes:
                    truncated = True
                    return
                with open(path, "wb") as f:
                    f.write(data)
                files.append(path)
                total += len(data)
                if progress:
                    try:
                        progress(len(files), len(urls))
                    except Exception:
                        log.exception("progress error")

        await asyncio.gather(*(one(i, u) for i, u in enumerate(urls)))

    return sorted(files), truncated


def zip_files(paths: list[str], zip_path: str) -> str:
    os.makedirs(os.path.dirname(zip_path) or ".", exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, os.path.basename(p))
    return zip_path


def cleanup(paths: list[str]):
    for p in paths + (glob.glob(os.path.dirname(paths[0]) + "/*") if paths else []):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
