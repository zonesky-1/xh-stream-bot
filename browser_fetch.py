# language: Python 3.11, file: browser_fetch.py
# Pengunduh segmen lewat CHROME — untuk host yang menolak non-Chrome
# (ambar.bezplay.xyz: "Unauthorized: invalid" dari httpx/curl_cffi — bedah
# 2026-10-09: header identik dgn Chrome, yang dicek = fingerprint transport
# TLS/H2. jadi biar Chrome sendiri yang nembak).
#
# Trik: page fetch (jaringan Chrome ✓) → blob → <a download>.click() →
# Chrome nulis file ke disk NATIF (tanpa lewat CDP base64 — cepat).
# Python tinggal nunggu file muncul di downloadPath.
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request

import websockets

PORT = 37911
CHROME = ("/home/agentuser/.agent-browser/browsers/"
          "chrome-155.0.8059.39/chrome")
UDIR = "/home/agentuser/.hermes/cache/scratch/juicy-chrome"


def _alive() -> bool:
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/json/version", timeout=3) as r:
            return "Browser" in r.read().decode()
    except Exception:
        return False


def ensure_chrome() -> None:
    if _alive():
        return
    os.makedirs(UDIR, exist_ok=True)
    subprocess = __import__("subprocess")
    subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PORT}", "--headless=new",
         "--no-sandbox", "--disable-dev-shm-usage", "--no-first-run",
         "--disable-gpu", "--user-data-dir=" + UDIR,
         "--window-size=1280,720", "about:blank"],
        stdout=__import__("subprocess").DEVNULL,
        stderr=__import__("subprocess").DEVNULL)
    for _ in range(50):
        if _alive():
            return
        time.sleep(0.2)
    raise RuntimeError("chrome gagal nyala utk browser_fetch")


def _new_tab(url: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _close_tab(tid: str) -> None:
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/close/{tid}", timeout=5).read()
    except Exception:
        pass


def _set_download(ws_url: str, path: str) -> None:
    """Set download behavior — sekali per sesi (via tab ws sync kecil)."""
    async def _go():
        async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
            await ws.send(json.dumps({
                "id": 1, "method": "Browser.setDownloadBehavior",
                "params": {"behavior": "allow", "downloadPath": path,
                           "eventsEnabled": True}}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                if json.loads(raw).get("id") == 1:
                    return
    asyncio.run(_go())


async def _download_all(embed_url: str, files: dict[str, str],
                        dest_dir: str, timeout: float = 600) -> list[str]:
    """files: {nama_file_di_disk: url} — fetch+download dari dalam page
    yang dibuka di embed_url (Referer/Origin/cookies page itu)."""
    ensure_chrome()
    os.makedirs(dest_dir, exist_ok=True)
    tgt = _new_tab(embed_url)
    try:
        async with websockets.connect(tgt["webSocketDebuggerUrl"],
                                      max_size=64 * 1024 * 1024) as ws:
            await ws.send(json.dumps({
                "id": 1, "method": "Page.setDownloadBehavior",
                "params": {"behavior": "allow", "downloadPath": dest_dir}}))
            await asyncio.sleep(4)  # tunggu page load + cookies embed

            payload = json.dumps([[name, url] for name, url in files.items()])
            expr = f"""(async () => {{
              const jobs = {payload};
              window.__errs = [];
              for (const [name, url] of jobs) {{
                try {{
                  const r = await fetch(url, {{credentials: 'omit'}});
                  if (!r.ok) {{ window.__errs.push(name + ':' + r.status); continue; }}
                  const blob = await r.blob();
                  const a = document.createElement('a');
                  a.href = URL.createObjectURL(blob);
                  a.download = name;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                }} catch (e) {{ window.__errs.push(name + ':' + e); }}
              }}
              return JSON.stringify({{done: jobs.length, errs: window.__errs}});
            }})()"""
            await ws.send(json.dumps({
                "id": 2, "method": "Runtime.evaluate",
                "params": {"expression": expr, "awaitPromise": True,
                           "returnByValue": True,
                           "timeout": timeout * 1000}}))
            result = None
            t0 = time.time()
            while time.time() - t0 < timeout:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout + 10)
                ev = json.loads(raw)
                if ev.get("id") == 2:
                    if ev.get("exceptionDetails"):
                        raise RuntimeError(
                            "browser fetch exception: "
                            + str(ev["exceptionDetails"])[:300])
                    result = (ev.get("result", {}).get("result", {})
                              .get("value", ""))
                    break
            if not result:
                raise RuntimeError("browser fetch nggak balik hasil")
            d = json.loads(result)
            errs = d.get("errs") or []
            if errs:
                # CDN flaky — biar pemanggil yang putuskan ambang toleransi
                import sys as _sys
                print("browser_fetch errs:", len(errs), str(errs)[:200],
                      file=_sys.stderr)
            # tunggu file stabil di disk (download async)
            pending = set(files)
            last_sz: dict[str, int] = {}
            t0 = time.time()
            while pending and time.time() - t0 < timeout:
                for n in list(pending):
                    p = os.path.join(dest_dir, n)
                    cr = os.path.join(dest_dir, n + ".crdownload")
                    if os.path.exists(cr):
                        continue
                    if os.path.exists(p):
                        sz = os.path.getsize(p)
                        if last_sz.get(n) == sz and sz > 0:
                            pending.discard(n)
                        else:
                            last_sz[n] = sz
                if pending:
                    await asyncio.sleep(0.4)
            if pending:
                errs += ["file nggak selesai: " + n for n in sorted(pending)]
            return errs
    finally:
        _close_tab(tgt["id"])


def download_files(embed_url: str, files: dict[str, str],
                   dest_dir: str) -> list[str]:
    """Blocking wrapper. files = {nama_file: url} → daftar error (boleh
    kosong; CDN flaky — toleransi ditentukan pemanggil)."""
    return asyncio.run(_download_all(embed_url, files, dest_dir))


async def _fetch_text(embed_url: str, url: str, timeout: float = 60) -> str:
    """Ambil teks (playlist) lewat Chrome — utk host yg nolak non-Chrome."""
    ensure_chrome()
    tgt = _new_tab(embed_url)
    try:
        async with websockets.connect(tgt["webSocketDebuggerUrl"],
                                      max_size=64 * 1024 * 1024) as ws:
            await asyncio.sleep(4)
            expr = f"""(async () => {{
              const r = await fetch({json.dumps(url)},
                                    {{credentials: 'omit'}});
              if (!r.ok) return 'ERR' + r.status;
              return await r.text();
            }})()"""
            await ws.send(json.dumps({
                "id": 2, "method": "Runtime.evaluate",
                "params": {"expression": expr, "awaitPromise": True,
                           "returnByValue": True,
                           "timeout": timeout * 1000}}))
            t0 = time.time()
            while time.time() - t0 < timeout:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout + 10)
                ev = json.loads(raw)
                if ev.get("id") == 2:
                    if ev.get("exceptionDetails"):
                        raise RuntimeError(
                            "browser fetch exception: "
                            + str(ev["exceptionDetails"])[:300])
                    val = (ev.get("result", {}).get("result", {})
                           .get("value", ""))
                    if isinstance(val, str) and val.startswith("ERR"):
                        raise RuntimeError("browser fetch " + val[:40])
                    return str(val)
            raise RuntimeError("browser fetch_text timeout")
    finally:
        _close_tab(tgt["id"])


def fetch_text(embed_url: str, url: str) -> str:
    return asyncio.run(_fetch_text(embed_url, url))


# ── CLI: browser_fetch.py <embed_url> <dest_dir> <url> [namafile url ...] ─
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("usage: browser_fetch.py <embed_url> <dest_dir> <url> "
              "[name url ...]")
        raise SystemExit(2)
    emb, dest = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]
    pairs: dict[str, str] = {}
    if len(rest) == 1:
        pairs["seg00000.bin"] = rest[0]
    else:
        for i in range(0, len(rest), 2):
            pairs[rest[i]] = rest[i + 1]
    download_files(emb, pairs, dest)
    for n in pairs:
        p = os.path.join(dest, n)
        print(n, os.path.getsize(p), "OK")
