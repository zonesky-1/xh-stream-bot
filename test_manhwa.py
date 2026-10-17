import asyncio, sys, os, json, time
sys.path.insert(0, ".")
import scraper_hentai as sh

async def main():
    t0 = time.time()
    gp = await sh.search("manhwa", 1)
    print(f"search: {len(gp.items)} items, max_pages={gp.max_pages}, {round(time.time()-t0,1)}s")
    for it in gp.items[:3]:
        print(f"  {it.idx}. [{it.cat}] {it.title[:55]} | thumb={bool(it.thumb)}")

    target = gp.items[0]
    t1 = time.time()
    d = await sh.gallery(target.url)
    print(f"gallery: '{d.title[:50]}' pages={d.pages} cover={bool(d.cover)} {round(time.time()-t1,1)}s")
    print("  page1:", d.page_urls[0] if d.page_urls else None)
    print("  tags:", d.tags[:6])

    t2 = time.time()
    files, trunc = await sh.download_pages(d, "dl_test", start=0, limit=3)
    size = sum(os.path.getsize(f) for f in files)
    print(f"download 3 pages: {len(files)} files, {size/1024:.0f}KB, trunc={trunc}, {round(time.time()-t2,1)}s")
    zp = sh.zip_files(files, "dl_test/test.zip")
    print("zip:", os.path.getsize(zp), "bytes")
    print("PASS")

try:
    asyncio.run(main())
except Exception:
    import traceback
    traceback.print_exc()
