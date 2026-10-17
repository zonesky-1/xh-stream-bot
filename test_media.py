# language: Python 3.11, file: test_media.py, target: selftest pipeline xh-bot (run: .venv/bin/python test_media.py)
import asyncio
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scraper

DL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dl")


def dur_sec(d: str) -> int:
    try:
        parts = [int(x) for x in d.split(":")]
    except Exception:
        return 10**9
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


async def main():
    sp = await scraper.search("amateur", 1)
    print(f"search ok: {len(sp.items)} items, max_pages={sp.max_pages}")
    target = min((it for it in sp.items if it.duration), key=lambda it: dur_sec(it.duration))
    print(f"target: {target.title[:50]} | {target.duration} | {target.url}")

    info = await scraper.resolve(target.url)
    fmt_stream = scraper.pick_format(info, "stream")
    fmt_best = scraper.pick_format(info, "best")

    def fdesc(fid):
        for f in info["formats"]:
            if f.get("format_id") == fid:
                size = (f.get("filesize") or f.get("filesize_approx") or 0) / 1048576
                return (f"{fid} h={f.get('height')}p proto={f.get('protocol')} "
                        f"acodec={f.get('acodec')} size~{size:.1f}MB")
        return fid

    print("pick stream:", fdesc(fmt_stream))
    print("pick best  :", fdesc(fmt_best))

    calls = []

    def progress(done, total):
        calls.append((done, total))

    t0 = time.time()
    path = await asyncio.to_thread(scraper.download_sync, target.url, fmt_stream, DL, progress)
    el = time.time() - t0
    size = os.path.getsize(path)
    print(f"downloaded: {os.path.basename(path)} | {size / 1048576:.1f} MB | {el:.1f}s | "
          f"progress calls: {len(calls)}")
    if calls:
        d, tot = calls[-1]
        print(f"last progress: {d / 1048576:.1f}/{tot / 1048576:.1f} MB")

    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height", "-of", "csv=p=0", path],
                         capture_output=True, text=True)
    print("ffprobe:", out.stdout.strip().replace("\n", " | "))
    assert "video" in out.stdout and "audio" in out.stdout, "stream video/audio nggak lengkap"
    os.remove(path)
    print("MEDIA PIPELINE PASS")


if __name__ == "__main__":
    asyncio.run(main())
