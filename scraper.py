# language: Python 3.11, file: scraper.py, target: xHamster (search + yt-dlp HLS download)
from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Optional

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("scraper")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://xhamster.com"
RESULTS_PER_PAGE = 46


@dataclass
class Result:
    idx: int
    title: str
    url: str
    duration: str = ""
    views: str = ""
    thumb: str = ""


@dataclass
class SearchPage:
    query: str
    page: int
    max_pages: int
    items: list


def _slug(q: str) -> str:
    # canonical site format: /search/hot+mom (301 dari /search/hot-mom nelen query param)
    return re.sub(r"[^a-z0-9]+", "+", q.lower()).strip("+")


def _parse_initials(page_html: str) -> list[Result]:
    """Jalur UTAMA: window.initials (SSR JSON) → searchResult.videoThumbProps.
    SEMUA item (46/46) bawa thumbURL+title+duration+views — DOM xH kini lazy-load
    (cuma 7/46 kejaring, dan IP datacenter kena 'xh-thumb-disabled').
    JSON ini selalu ikut di HTML, gak peduli IP."""
    import json
    m = re.search(r"window\.initials=(\{.*?});</script>", page_html, re.S)
    if not m:
        return []
    try:
        vt = (json.loads(m.group(1)).get("searchResult")
              or {}).get("videoThumbProps") or []
    except Exception as e:
        log.debug("initials parse gagal: %s", e)
        return []
    items: list[Result] = []
    for v in vt:
        if not isinstance(v, dict):
            continue
        url = (v.get("pageURL") or "").split("?")[0]
        if not url:
            continue
        dur = v.get("duration") or 0
        views = v.get("views")
        if isinstance(views, (int, float)):
            if views >= 1_000_000:
                vs = f"{views / 1_000_000:.1f}M views"
            elif views >= 1_000:
                vs = f"{views / 1_000:.1f}K views"
            else:
                vs = f"{int(views)} views"
        else:
            vs = str(views or "")
        items.append(Result(
            idx=len(items) + 1, title=(v.get("title") or "").strip(),
            url=url, duration=f"{dur // 60}:{dur % 60:02d}" if dur else "",
            views=vs, thumb=v.get("thumbURL") or ""))
    return items


async def search(q: str, page: int = 1) -> SearchPage:
    slug = _slug(q)
    if slug:
        url = f"{BASE}/search/{slug}"
        if page > 1:
            url += f"?page={page}"
    else:
        url = f"{BASE}/search?q={urllib.parse.quote(q)}"
        if page > 1:
            url += f"&page={page}"
    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        follow_redirects=True,
        timeout=30,
    ) as c:
        page_html = None
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = await c.get(url)
                r.raise_for_status()
                page_html = r.text
                break
            except httpx.HTTPError as e:
                last_err = e
                log.warning("search attempt %d gagal: %s", attempt + 1, e)
                await asyncio.sleep(1.5 * (attempt + 1))
        if page_html is None:
            raise last_err if last_err else RuntimeError("search gagal")
    return _parse(page_html, q, page)


def _parse(page_html: str, q: str, page: int) -> SearchPage:
    soup = BeautifulSoup(page_html, "lxml")
    items: list[Result] = _parse_initials(page_html)
    if not (items and sum(1 for i in items if i.thumb) >= max(1, len(items) // 2)):
        items = _parse_dom(soup)
    seen_urls: set[str] = set()
    uniq: list[Result] = []
    for it in items:
        if it.url in seen_urls:
            continue
        seen_urls.add(it.url)
        it.idx = len(uniq) + 1
        uniq.append(it)
    items = uniq
    pages = [int(n) for n in re.findall(r'data-page="(\d+)"', page_html)]
    max_pages = max(pages) if pages else 1
    if page > max_pages:
        page = max_pages
    return SearchPage(query=q, page=page, max_pages=max_pages, items=items)


def _parse_dom(soup: BeautifulSoup) -> list[Result]:
    items: list[Result] = []
    seen_urls: set[str] = set()
    for div in soup.select("div.video-thumb"):
        a = div.select_one('a[href*="/videos/"]')
        if not a:
            continue
        url = (a.get("href") or "").split("?")[0]
        if not url or url in seen_urls:
            continue
        if div.get("data-video-type") not in (None, "video", ""):
            continue
        seen_urls.add(url)
        title = a.get("aria-label") or ""
        if not title:
            img0 = div.select_one("img")
            title = (img0.get("alt") if img0 else "") or ""
        dur_el = div.select_one('[data-role="video-duration"]')
        duration = dur_el.get_text(strip=True) if dur_el else ""
        txt = div.get_text(" ", strip=True)
        m = re.search(r"([\d.,]+\s*[KMB]?\s*views)", txt)
        views = m.group(1) if m else ""
        img = div.select_one("img")
        thumb = ""
        if img:
            thumb = img.get("src") or img.get("data-src") or ""
        items.append(Result(idx=len(items) + 1, title=title.strip(), url=url,
                            duration=duration, views=views, thumb=thumb))
    return items


async def resolve(url: str) -> dict:
    return await asyncio.to_thread(_extract, url)


def _extract(url: str) -> dict:
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 25,
        "retries": 2,
        "http_headers": {"User-Agent": UA, "Referer": f"{BASE}/"},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def pick_format(info: dict, want: str) -> str:
    """want: 'stream' (<=480p, <=45MB ideal), 'best' (maksimal, <=600MB),
    atau 'hNNN' mis. 'h720' → maksimal <=720p (fallback: terendah di atasnya)."""
    seen: set = set()
    ok: list = []
    for f in info.get("formats") or []:
        if "m3u8" not in (f.get("protocol") or ""):
            continue
        if f.get("vcodec") in (None, "none") or f.get("acodec") in (None, "none"):
            continue
        h = f.get("height") or 0
        size = f.get("filesize") or f.get("filesize_approx") or 0
        fid = f.get("format_id")
        if not fid:
            continue
        key = (h, f.get("acodec"), round(f.get("tbr") or 0))
        if key in seen:
            continue
        seen.add(key)
        ok.append((h, size, fid))
    if not ok:
        raise RuntimeError("video ini nggak punya stream yang bisa diputar")
    if want.startswith("h") and want[1:].isdigit():
        target = int(want[1:])
        # tinggi yang tersedia unik, urut
        heights = sorted({x[0] for x in ok if x[0] > 0})
        pool_h = max((h for h in heights if h <= target), default=min(heights))
        pool = [x for x in ok if x[0] == pool_h] or ok
        pool.sort(key=lambda x: x[1] or 0)
        return pool[0][2]
    if want == "stream":
        pool = [x for x in ok if 0 < x[0] <= 480] or ok
        pool.sort(key=lambda x: x[0], reverse=True)
        small = [x for x in pool if not x[1] or x[1] <= 45 * 1024 * 1024]
        return (small or pool)[0][2]
    pool = sorted(ok, key=lambda x: (x[0], x[1]), reverse=True)
    under = [x for x in pool if not x[1] or x[1] <= 600 * 1024 * 1024]
    return (under or pool)[0][2]


def download_sync(url: str, format_id: str, out_dir: str,
                  progress: Optional[Callable[[int, int], None]] = None) -> str:
    import yt_dlp

    os.makedirs(out_dir, exist_ok=True)

    def hook(d):
        if not progress or d.get("status") != "downloading":
            return
        done = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        try:
            progress(done, total)
        except Exception:
            log.exception("progress callback error")

    opts = {
        "format": format_id,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "concurrent_fragment_downloads": 4,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 6,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": UA, "Referer": f"{BASE}/"},
        "progress_hooks": [hook],
    }
    def _extract(o):
        with yt_dlp.YoutubeDL(o) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        info = _extract(opts)
    except Exception as e:
        # format_id dari hasil resolve bisa kadaluarsa pas unduh beneran
        # (url HLS berubah / daftar format berbeda) → tangga fallback
        if "not available" not in str(e).lower():
            raise
        ladder = [
            ("hls-merge", "bv*[protocol*=m3u8]+ba[protocol*=m3u8]"
                          "/bv*[protocol*=m3u8]+ba/b[protocol*=m3u8]"),
            ("best", "bv*+ba/b"),
        ]
        info = None
        for tag, sel in ladder:
            log.warning("format %s gagal (%s) — coba fallback %s",
                        format_id, str(e)[:90], tag)
            try:
                info = _extract(dict(opts, format=sel))
                break
            except Exception as e2:
                log.warning("fallback %s juga gagal: %s", tag, str(e2)[:90])
                e = e2
        if info is None:
            raise e
    vid = info.get("id", "vid")
    cands = [p for p in glob.glob(os.path.join(out_dir, vid + ".*"))
             if not p.endswith((".part", ".frag", ".ytdl")) and os.path.isfile(p)]
    if not cands:
        raise RuntimeError("download selesai tapi file nggak ketemu")
    return max(cands, key=os.path.getsize)
