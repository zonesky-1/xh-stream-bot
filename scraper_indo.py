# language: Python 3.11, file: scraper_indo.py, target: dojing.net (doujin/manhwa bahasa Indonesia)
from __future__ import annotations

import asyncio
import html as _html
import logging
import os
import re
from urllib.parse import quote_plus

import httpx

from scraper_hentai import Gallery, GalleryDetail, GalleryPage, zip_files  # reuse bentuk data + zip

log = logging.getLogger("scraper_indo")
BASE = "https://dojing.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# chapter dalam 1 series dibatasi biar waktu detail ga meledak
MAX_CHAPTERS = 15


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
                 "Referer": BASE + "/"},
        follow_redirects=True, timeout=30,
    )


def _series_from_html(html: str) -> list[Gallery]:
    """Kumpulkan link /manga/<slug>/ unik dari satu halaman, lengkap dgn thumb+judul."""
    items: list[Gallery] = []
    seen: set[str] = set()
    for m in re.finditer(
            r'<a[^>]+href="(https://dojing\.net/manga/[^"?#]+/)"[^>]*>(.*?)</a>',
            html, re.S):
        href = m.group(1)
        if href in seen:
            continue
        seen.add(href)
        inner = m.group(2)
        # judul: teks anchor, atau <h2>/<h3> di dalamnya
        tm = re.search(r"<h[23][^>]*>(.*?)</h[23]>", inner, re.S)
        txt = tm.group(1) if tm else inner
        title = _html.unescape(
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)).strip())
        # thumb: img pertama di blok kartu
        im = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', inner)
        thumb = im.group(1) if im else ""
        if thumb.startswith("//"):
            thumb = "https:" + thumb
        if not title:
            title = href.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        items.append(Gallery(idx=len(items) + 1, title=title, url=href,
                             cat="Doujinshi", thumb=thumb))
    return items


def _max_pages(html: str) -> int:
    nums = [int(n) for n in re.findall(r"[?&]paged=(\d+)", html)]
    nums += [int(n) for n in re.findall(r"/page/(\d+)", html)]
    return max(nums) if nums else 1


async def search(q: str = "", page: int = 1) -> GalleryPage:
    """Cari series doujin berbahasa Indonesia di dojing.net.
    q kosong → browse homepage (update terbaru)."""
    q = (q or "").strip()
    url = f"{BASE}/?s={quote_plus(q)}" if q else f"{BASE}/"
    if page > 1:
        url += ("&" if "?" in url else "?") + f"paged={page}"
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        html = r.text
    items = _series_from_html(html)
    if page > max(page, _max_pages(html)):
        page = _max_pages(html)
    return GalleryPage(query=q, page=page, max_pages=max(_max_pages(html), page),
                       items=items)


def _chapters_from_series(html: str, slug: str) -> list[str]:
    """Url chapter post (level root) dari halaman series, terurut nomor chapter."""
    links = set(re.findall(rf'href="(https://dojing\.net/[^"?#]+/)"', html))
    numbered: dict[float, str] = {}
    latest = ""
    pat = re.compile(rf"{re.escape(slug)}-chapter-([\d.]+)/$")
    for u in links:
        base = u.rstrip("/") + "/"
        m = pat.search(base)
        if m:
            try:
                numbered[float(m.group(1))] = base
            except ValueError:
                pass
        elif base.rstrip("/") == f"{BASE}/{slug}":
            latest = base  # link "New Chapter" utk series all-chapter
    urls = [numbered[k] for k in sorted(numbered)]
    if latest and latest.rstrip("/") not in {u.rstrip("/") for u in urls}:
        urls.append(latest)
    return urls


def _reader_imgs(html: str) -> list[str]:
    """Gambar halaman manga (manga.komik.me/File*/…) urut DOM, tanpa duplikat.
    Sumber direader bervariasi: div#readerarea (lama) atau area #content s/d
    #footer (baru, host path File4/…) — keduanya dicoba, utuh atau gabungan."""
    def urls_in(seg: str) -> list[str]:
        return re.findall(
            r'https://manga\.komik\.me/File\d*/[^"\'\s<]+\.(?:jpg|jpeg|png|webp)',
            seg, re.I)

    # 1) area konten utama (paling stabil), batasi s/d footer biar Related ga kebawa
    m = re.search(r'<div[^>]+id="content"(.*?)<div[^>]+id="footer"', html, re.S)
    urls = urls_in(m.group(1)) if m else []
    # 2) fallback: div#readerarea
    if not urls:
        mr = re.search(r'<div[^>]+id="readerarea"(.*?)</div>', html, re.S)
        if mr:
            urls = urls_in(mr.group(1))
    # 3) fallback terakhir: seluruh halaman
    if not urls:
        urls = urls_in(html)
    out: list[str] = []
    for u in urls:
        if u not in out:
            out.append(u)
    return out


async def gallery(url: str) -> GalleryDetail:
    """Detail series: judul, cover, semua halaman dari semua chapter (terurut)."""
    async with _client() as c:
        r = await c.get(url)
        r.raise_for_status()
        html = r.text
        og_t = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        og_i = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        title = og_t.group(1) if og_t else url.rstrip("/").rsplit("/", 1)[-1]
        title = re.sub(r"\s*-\s*(Dojing\.net|All Chapter)\s*$", "", title).strip()
        cover = og_i.group(1) if og_i else ""
        slug = url.rstrip("/").rsplit("/manga/", 1)[-1]

        chapters = _chapters_from_series(html, slug)

        async def fetch(u: str) -> list[str]:
            try:
                rr = await c.get(u)
                return _reader_imgs(rr.text)
            except httpx.HTTPError as e:
                log.warning("chapter %s gagal: %s", u, e)
                return []

        async def probe_constructed() -> list[str]:
            """Coba /<slug>-chapter-N/ buat N=1..15, ambil yang reader-nya ada."""
            async def one(n: int) -> str | None:
                u = f"{BASE}/{slug}-chapter-{n}/"
                try:
                    rr = await c.get(u)
                    if rr.status_code == 200 and _reader_imgs(rr.text):
                        return u
                except httpx.HTTPError:
                    pass
                return None
            got = await asyncio.gather(*(one(n) for n in range(1, 16)))
            return [g for g in got if g]

        if not chapters:
            chapters = await probe_constructed()

        chapters = chapters[:MAX_CHAPTERS]
        if chapters:
            batches = await asyncio.gather(*(fetch(u) for u in chapters))
        else:
            batches = [_reader_imgs(html)]
        # link chapter ada tapi isinya 0 → coba chapter konstruksi
        if not any(batches):
            constructed = await probe_constructed()
            if constructed:
                chapters = constructed[:MAX_CHAPTERS]
                batches = await asyncio.gather(*(fetch(u) for u in chapters))

        page_urls: list[str] = []
        for b in batches:
            for p in b:
                if p not in page_urls:
                    page_urls.append(p)
        if not page_urls:
            log.warning("gallery %s: 0 halaman kebaca", url)
        return GalleryDetail(title=title, url=url, cover=cover,
                             pages=len(page_urls), page_urls=page_urls,
                             tags=chapters)


async def download_pages(detail: GalleryDetail, out_dir: str, start: int = 0,
                         limit: int | None = None, progress: Callable | None = None,
                         max_bytes: int | None = None):
    """Unduh halaman [start:start+limit] (atau semua sampai max_bytes).
    Balik (paths, truncated) — urutan persis urutan baca."""
    os.makedirs(out_dir, exist_ok=True)
    urls = detail.page_urls[start:]
    if limit is not None:
        urls = urls[:limit]
    files: list[str] = []
    total = 0
    truncated = False
    async with _client() as c:
        for i, u in enumerate(urls):
            if max_bytes is not None and total >= max_bytes:
                truncated = True
                break
            ext = os.path.splitext(u.split("?")[0])[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            path = os.path.join(out_dir, f"indo_{start + i:04d}{ext}")
            try:
                r = await c.get(u, headers={"Referer": url_of(detail)})
                if r.status_code != 200 or not r.headers.get(
                        "content-type", "").startswith("image"):
                    log.warning("halaman %s bukan image (%s)", u, r.status_code)
                    continue
                data = r.content
                if max_bytes is not None and total + len(data) > max_bytes:
                    truncated = True
                    break
                with open(path, "wb") as f:
                    f.write(data)
                files.append(path)
                total += len(data)
                if progress:
                    try:
                        progress(len(files), len(urls))
                    except Exception:
                        log.exception("progress error")
            except httpx.HTTPError as e:
                log.warning("unduh %s gagal: %s", u, e)
    return files, truncated


def url_of(detail: GalleryDetail) -> str:
    """Referer buat hotlink protection: halaman series asli."""
    return detail.url
