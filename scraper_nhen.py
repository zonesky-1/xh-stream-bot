# language: Python 3.11, file: scraper_nhen.py — NHENTAI (6-digit doujin API v2)
#
# Fakta lapangan (bedah 2026-10-17, jangan diubah sembarangan):
# 1. API v1 MATI (403 "Use new API") → v2: https://nhentai.net/api/v2/...
#    openapi: /api/v2/search (query,sort,page), /api/v2/galleries/{id},
#    /galleries/popular, /galleries/random, /cdn. Wajib header Accept: text/css
#    (anti-DDG mirror coomer — sama polanya; tanpa itu kena 403 octet-stream).
# 2. search → {result:[{id,media_id,english_title,thumbnail,num_pages,...}],
#    num_pages, per_page, total}. per_page=25.
# 3. galleries/{id} → {id, media_id, title:{english,japanese,pretty},
#    cover:{path: galleries/X/cover.jpg.webp}, pages:[{path,width,height}],
#    tags:[{type,name,slug}]}.
# 4. CDN (tanpa auth, tanpa CF): thumb/cover t.nhentai.net (cover.jpg 200
#    image/jpeg — buang suffix .webp), halaman i.nhentai.net/<path> (200 jpg).
#    i.nhentai.net pernah HTTP/2 reset sesekali → retry wajib.
# 5. Interface = clone scraper_hentai (Gallery/GalleryPage/GalleryDetail/
#    search/gallery/download_pages/zip_files/cleanup) supaya reader manhwa
#    (slide/10 hal/ZIP/strip) di bot.py dipakai ulang tanpa ubah apa pun —
#    cukup STATES_M[qid]["mod"] = scraper_nhen.
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

log = logging.getLogger("nhen")

API = "https://nhentai.net/api/v2"
SITE = "https://nhentai.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


# ── tipe data IDENTIK scraper_hentai (drop-in reader) ─────────────────────
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
        headers={"User-Agent": UA, "Accept": "text/css"},
        timeout=30, follow_redirects=True, http2=False)


async def _get_retry(c: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    """GET + retry utk 5xx/429 — CF origin nhentai suka 522 sesaat (terverifikasi
    live 2026-10-17: /galleries/popular balik 522 lalu OK). Max 3 percobaan."""
    last = None
    for attempt in range(3):
        try:
            r = await c.get(url, **kw)
        except httpx.HTTPError as e:
            last = e
        else:
            if r.status_code in (429, 500, 502, 503, 504, 520, 521, 522, 524):
                last = RuntimeError(f"HTTP {r.status_code}")
            else:
                return r
        await asyncio.sleep(1.5 * (attempt + 1))
    if last:
        raise last
    raise RuntimeError("gagal GET")


def _thumb_url(path: str) -> str:
    """galleries/X/thumb.jpg.webp → https://t.nhentai.net/galleries/X/thumb.jpg
    (.jpg 200 image/jpeg; .webp juga ada tapi jpg lebih aman utk kartu TG)."""
    p = re.sub(r"\.webp$", "", path or "")
    return f"https://t.nhentai.net/{p}" if p else ""


def _item(r: dict, idx: int) -> Gallery:
    gid = r.get("id")
    title = (r.get("english_title") or r.get("japanese_title")
             or r.get("title") or f"galeri {gid}").strip()
    n = r.get("num_pages") or 0
    return Gallery(idx=idx, title=title, url=f"{SITE}/g/{gid}/",
                   cat=f"{n} hal" if n else "",
                   thumb=_thumb_url(r.get("thumbnail") or ""))


def _to_page(payload: dict, query: str, page: int) -> GalleryPage:
    rows = payload.get("result") or payload or []
    maxp = int(payload.get("num_pages") or 1) if isinstance(payload, dict) else 1
    items = [_item(r, i + 1) for i, r in enumerate(rows)]
    return GalleryPage(query=query, page=page, max_pages=max(1, maxp), items=items)


async def search(q: str = "", page: int = 1) -> GalleryPage:
    """Cari doujin. q kosong → popular (browse tanpa judul)."""
    q = (q or "").strip()
    async with _client() as c:
        if q:
            r = await _get_retry(c, f"{API}/search",
                                params={"query": q, "page": page, "limit": 25})
        else:
            r = await _get_retry(c, f"{API}/galleries/popular")
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        data = {"result": data, "num_pages": 1}
    label = q or "🔥 populer hari ini"
    gp = _to_page(data, label, page)
    if not q:  # popular = list datar tanpa paginasi resmi → batasi 25
        gp.items = gp.items[:25]
        gp.max_pages = 1
    return gp


async def random_id() -> int:
    async with _client() as c:
        r = await _get_retry(c, f"{API}/galleries/random")
        r.raise_for_status()
        return int(r.json()["id"])


def _page_url(path: str) -> str:
    return f"https://i.nhentai.net/{path}"


async def gallery(url: str) -> GalleryDetail:
    """Detail galeri dari URL https://nhentai.net/g/<id>/."""
    m = re.search(r"/g/(\d+)", url)
    if not m:
        raise RuntimeError(f"bukan URL gallery nhentai: {url}")
    gid = m.group(1)
    async with _client() as c:
        r = await _get_retry(c, f"{API}/galleries/{gid}")
        if r.status_code == 404:
            raise RuntimeError(f"gallery {gid} nggak ada (dihapus/dibanned)")
        r.raise_for_status()
        d = r.json()
    title = ((d.get("title") or {}).get("english")
             or (d.get("title") or {}).get("pretty") or f"nhentai {gid}")
    cover = _thumb_url((d.get("cover") or {}).get("path") or "")
    pages = d.get("pages") or []
    page_urls = [_page_url(p["path"]) for p in pages if p.get("path")]
    tags = [t.get("name", "") for t in (d.get("tags") or [])
            if t.get("type") in ("tag", "artist", "parody") and t.get("name")]
    return GalleryDetail(title=title, url=f"{SITE}/g/{gid}/", cover=cover,
                         pages=len(page_urls), page_urls=page_urls,
                         tags=list(dict.fromkeys(tags))[:15])


async def download_pages(detail: GalleryDetail, out_dir: str,
                         start: int = 0, limit: Optional[int] = None,
                         progress: Optional[Callable[[int, int], None]] = None,
                         max_bytes: Optional[int] = None) -> tuple[list[str], bool]:
    """Unduh halaman (0-index). Balik (list file, truncated?)."""
    os.makedirs(out_dir, exist_ok=True)
    urls = detail.page_urls[start:]
    if limit:
        urls = urls[:limit]
    if not urls:
        raise RuntimeError("gallery nggak punya halaman yang bisa diunduh")
    m = re.search(r"/g/(\d+)", detail.url)
    gid = m.group(1) if m else "nh"
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
                rr = None
                for _attempt in range(3):
                    try:
                        r2 = await _get_retry(c, u)
                    except httpx.HTTPError as e:
                        log.warning("halaman %d err %s (retry)", i + 1, e)
                        await asyncio.sleep(0.6)
                        continue
                    if r2.status_code == 200 and (r2.headers.get("content-type")
                                                  or "").startswith("image"):
                        rr = r2
                        break
                    await asyncio.sleep(0.5)
                if rr is None:
                    log.warning("halaman %d nggak bisa diunduh: %s", i + 1, u)
                    return
                ext = ".png" if "png" in (rr.headers.get("content-type") or "") else ".jpg"
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
