# language: Python 3.11, file: juicy_resolve.py
# Resolver embed "juicycodes" (barplay/bezplay — 85% film LK21).
#
# MENGAPA PAKAI CHROME (hasil bedah 2026-10-09, jangan disederhanakan):
# 1. Payload embed YANG DIFETCH PYTHON = signature INVALID (server terbitkan
#    payload terikat konteks klien — divalidasi waktu stream). TERBUKTI:
#    payload python → decode di mana pun → 403; payload chrome → 200 utk python.
# 2. Decode node (vm shim) = output BEDA dari page (env-dependent, atob/stub).
#    Decode di page (shadow window.eval) = satu-satunya yang valid.
# 3. Setelah URL dari page: playlist + segmen diambil PYTHON bebas
#    (200/206) — cuma langkah embed+decode yang butuh Chrome.
#
# Alur: launch chrome headless (port tetap) → buka embed → ambil payload dari
# script inline → shadow-eval _juicycodes → tangkap config → URL playlist →
# tutup tab. Playlist/segmen = urusan scraper_film.
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import subprocess
import time
import urllib.request

CHROME = ("/home/agentuser/.agent-browser/browsers/"
          "chrome-155.0.8059.39/chrome")
UDIR = "/home/agentuser/.hermes/cache/scratch/juicy-chrome"
PORT = 37911
TOKO = "/home/agentuser/.hermes/cache/scratch"  # temp workspace


def _chrome_running() -> bool:
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/json/version", timeout=3) as r:
            return "Browser" in r.read().decode()
    except Exception:
        return False


def ensure_chrome() -> None:
    if _chrome_running():
        return
    os.makedirs(UDIR, exist_ok=True)
    subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PORT}", "--headless=new",
         "--no-sandbox", "--disable-dev-shm-usage", "--no-first-run",
         "--no-default-browser-check", "--disable-gpu",
         "--user-data-dir=" + UDIR, "--window-size=1280,720",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if _chrome_running():
            return
        time.sleep(0.2)
    raise RuntimeError("chrome gagal nyala")


def kill_chrome() -> None:
    subprocess.run(["pkill", "-f", f"user-data-dir={UDIR}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _targets() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json",
                                timeout=5) as r:
        return json.load(r)


async def _resolve(embed_url: str, timeout: float = 45) -> str:
    import websockets
    ensure_chrome()
    # buka tab baru ke embed
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/json/new?{embed_url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        tgt = json.load(r)
    ws_url = tgt["webSocketDebuggerUrl"]
    try:
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            await ws.send(json.dumps({"id": 99, "method": "Page.enable"}))
            await asyncio.sleep(4)   # tunggu load + inline script jalan
            # tunggu load + payload siap
            expr = """(async () => {
              const sleep = ms => new Promise(r => setTimeout(r, ms));
              for (let i = 0; i < 60; i++) {
                const s = [...document.querySelectorAll('script')].find(x =>
                    !x.src && (x.textContent||'').includes('_juicycodes'));
                if (s) {
                  const m = s.textContent.match(/_juicycodes\\(([\\s\\S]*?)\\);/);
                  if (m) {
                    const orig = window.eval; let cap = null;
                    window.eval = (code) => { cap = String(code); return undefined; };
                    try { window._juicycodes((new Function('return (' + m[1] + ')'))()); }
                    catch(e) { window.eval = orig; return JSON.stringify({err: String(e)}); }
                    window.eval = orig;
                    const src = cap && cap.match(/"src":"(https:[^"]+)"/);
                    if (src) return JSON.stringify({url: src[1].replaceAll('\\\\/', '/')});
                    return JSON.stringify({err: 'no src', cap: cap && cap.slice(0, 140)});
                  }
                }
                await sleep(500);
              }
              return JSON.stringify({err: 'timeout: payload nggak ketemu'});
            })()"""
            await ws.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": expr, "awaitPromise": True,
                           "returnByValue": True}}))
            t0 = time.time()
            while time.time() - t0 < timeout:
                raw = await asyncio.wait_for(ws.recv(),
                                             timeout=timeout + 5)
                ev = json.loads(raw)
                if ev.get("id") == 1:
                    if ev.get("exceptionDetails"):
                        raise RuntimeError(
                            "eval exception: " + str(ev["exceptionDetails"]
                                                     )[:300])
                    val = (ev.get("result", {}).get("result", {})
                           .get("value", ""))
                    if val in ("", None):
                        raise RuntimeError(
                            "eval value kosong: " + str(ev)[:300])
                    try:
                        d = json.loads(val)
                    except Exception:
                        d = {"err": f"bad value {val[:120]}"}
                    if "url" in d:
                        return d["url"]
                    raise RuntimeError("juicy resolve gagal: "
                                       + str(d)[:220])
            raise RuntimeError("juicy resolve timeout")
    finally:
        # tutup tab biar nggak numpuk
        try:
            tid = tgt.get("id")
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json/close/{tid}",
                    timeout=5) as r:
                r.read()
        except Exception:
            pass


def resolve(embed_url: str) -> str:
    """Embed barplay/bezplay → URL playlist m3u8 (siap di-GET python)."""
    return asyncio.run(_resolve(embed_url))


# ── uji CLI: node/juicy_resolve.py <embed_url> ─────────────────────────────
if __name__ == "__main__":
    import sys
    logging_msg = None
    if len(sys.argv) < 2:
        print("usage: juicy_resolve.py <embed_url>")
        raise SystemExit(2)
    print(resolve(sys.argv[1]))
