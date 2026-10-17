"""Scraper video amatir China (91porny — 国产自拍/自拍/探花).

Sumber: 91porny.com — HTML tembus via curl_cffi Chrome, video HLS (m3u8)
di CDN cdn2.jiuse3.cloud (akses langsung OK, wajib header Referer site).
Detail: title, durasi (视频时长), poster (og:image), m3u8.
Download: ffmpeg -c copy concat HLS → mp4 faststart.
"""
import json
import re
import urllib.parse
import urllib.request
import warnings
from urllib.parse import quote
from curl_cffi import requests as cr

warnings.filterwarnings("ignore")

SITE = "https://91porny.com"

# Kamus slang Indo -> istilah pencarian tube China
SLANG_MAP = {
    "selingkuh": "偷情",
    "hotel": "酒店",
    "pijat": "按摩",
    "mahasiswi": "女大",
    "kuliah": "女大",
    "kampus": "女大",
    "tante": "熟女",
    "janda": "少妇",
    "istri orang": "人妻",
    "istri": "人妻",
    "amatir": "自拍",
    "bocoran": "流出",
    "gadis": "少女",
    "mandi": "洗澡",
    "cantik": "高颜值",
    "mobil": "车震",
    "outdoor": "户外",
    "toilet": "厕所",
    "kantor": "办公室",
    "guru": "老师",
    "seragam": "制服",
    "model": "模特",
    "intip": "偷拍",
    "kamar": "酒店",
}


def to_chinese_keyword(text: str) -> str:
    """Otomatis terjemahkan kata kunci Indo/Inggris ke istilah Mandarin."""
    if not text or not text.strip():
        return ""
    q = text.strip()
    # Jika sudah huruf Mandarin, pakai langsung
    if re.search(r"[\u4e00-\u9fff]", q):
        return q
    ql = q.lower()
    if ql in SLANG_MAP:
        return SLANG_MAP[ql]
    # Fallback auto translate Google
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=id&tl=zh-CN&dt=t&q="
               + urllib.parse.quote(q))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = "".join([part[0] for part in data[0] if part[0]]).strip()
            if res:
                return res
    except Exception:
        pass
    return q


def _s():
    return cr.Session(impersonate="chrome", timeout=20)


def _abs(u):
    return u if u.startswith("http") else SITE + u


def search(q="", limit=12):
    """Search video amatir China (bisa Indo/Mandarin). kosong = terbaru."""
    s = _s()
    zh_q = to_chinese_keyword(q) if q else ""
    u = f"{SITE}/search?keywords={quote(zh_q)}" if zh_q else f"{SITE}/"
    t = s.get(u).text
    seen, ids = set(), []
    for m in re.finditer(r'href="(/video/view/([0-9a-f]+))"', t):
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        ids.append(_abs(m.group(1)))
        if len(ids) >= limit:
            break
    items = []
    for url in ids:
        try:
            it = {"url": url}
            it.update(detail(url))
            items.append(it)
        except Exception:
            continue
    return items


def detail(url):
    """→ {title, dur, poster, m3u8}"""
    s = _s()
    t = s.get(url).text
    ti = re.search(r'<title>([^<]+)</title>', t)
    title = (ti.group(1) if ti else "?").strip()
    title = re.sub(r"\s*-\s*91视频.*$", "", title)
    dur = ""
    dm = re.search(r"视频时长[:：]\s*([\d:]+)", t)
    if dm:
        dur = dm.group(1)
    m3u8 = ""
    mm = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', t)
    if mm:
        m3u8 = mm.group(0).replace("&amp;", "&")
    poster = ""
    po = re.search(r'property="og:image" content="([^"]+)"', t)
    if po:
        poster = po.group(1)
    return {"title": title[:80], "dur": dur, "poster": poster, "m3u8": m3u8}


def download(m3u8_url, out_path, referer=SITE):
    """HLS → mp4. CDN lambat dari luar → download segmen paralel via curl_cffi,
    lalu concat via ffmpeg file-based (lebih andal daripada ffmpeg langsung ke URL)."""
    import os, time, subprocess
    import concurrent.futures as cf

    s = _s()
    HDRS = {"Referer": referer}
    try:
        pl = s.get(m3u8_url, headers=HDRS, timeout=60).text
    except Exception:
        return False
    segs = re.findall(r'[^\s"\']+\.ts', pl)
    if not segs:
        return False
    base = m3u8_url.rsplit("/", 1)[0]
    workdir = out_path + "_parts"
    os.makedirs(workdir, exist_ok=True)

    def dl(i_seg):
        i, seg = i_seg
        url = seg if seg.startswith("http") else f"{base}/{seg}"
        path = f"{workdir}/seg{i:04d}.ts"
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            return True
        for _ in range(3):
            try:
                rr = s.get(url, headers=HDRS, timeout=90)
                if rr.status_code == 200 and len(rr.content) > 1000:
                    open(path, "wb").write(rr.content)
                    return True
            except Exception:
                time.sleep(1.5)
        return False

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        ok = list(ex.map(dl, enumerate(segs)))
    if sum(ok) != len(segs):
        return False

    lst = f"{workdir}/list.txt"
    with open(lst, "w") as f:
        for i in range(len(segs)):
            f.write(f"file '{workdir}/seg{i:04d}.ts'\n")
    p = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", "-movflags", "+faststart", out_path],
                       capture_output=True, text=True, timeout=300)
    return p.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


if __name__ == "__main__":
    print("== search 自拍 ==")
    for r in search("自拍", 3):
        print(" •", r["title"][:50], "|", r["dur"], "|", r["m3u8"][:60])
