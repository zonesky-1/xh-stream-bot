"""Client API Stable Diffusion FastAPI (CPU) — buat di-wire ke /gen bot."""
import base64
import warnings
import httpx

warnings.filterwarnings("ignore")


def generate(prompt, negative="ugly, bad quality, blurry, deformed, lowres",
             steps=15, width=512, height=512, cfg=7.0,
             api_base="http://100.81.10.96:7860", timeout=600):
    """1 gambar → raw bytes PNG. Di CPU 8-core ~30-60 detik."""
    r = httpx.post(f"{api_base.rstrip('/')}/generate", json={
        "prompt": prompt,
        "negative_prompt": negative,
        "steps": steps,
        "width": width,
        "height": height,
        "guidance_scale": cfg,
    }, timeout=timeout)
    r.raise_for_status()
    b64 = r.json().get("image")
    if not b64:
        raise RuntimeError("gak ada image di response")
    return base64.b64decode(b64)


if __name__ == "__main__":
    import sys
    out = generate(sys.argv[1] if len(sys.argv) > 1 else "a beautiful cat, cinematic lighting")
    open("/tmp/sd_test.png", "wb").write(out)
    print(f"OK: {len(out)} bytes → /tmp/sd_test.png")
