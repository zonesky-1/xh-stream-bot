"""E2E penuh: 1 episode series utuh → mp4 playable + sub burn."""
import sys, os, time
sys.path.insert(0, "/home/agentuser/xh-bot")
import scraper_series as ss

items, _ = ss.search("euphoria", 1)
d = ss.detail(items[0]["url"], items[0]["id"])
ep = next(u for lbl, u in d["eps"] if lbl == "S1E2")
print("EP:", d["title"][:40], "S1E2", flush=True)
t0 = time.time()

def prog(i, n):
    if i % 20 == 0 or i == n:
        print(f"  segmen {i}/{n} ({time.time() - t0:.0f}s)", flush=True)

out, dur, burned = ss.download(ep, "/tmp/series_full.mp4", True, prog)
sz = os.path.getsize(out)
print(f"SELESAI: {out} {sz / 1048576:.1f} MB | durasi {dur / 60:.1f} menit | "
      f"sub burn {burned} | total {time.time() - t0:.0f}s", flush=True)
