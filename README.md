# 🎬 XH Stream Bot — Unified Multimedia Aggregator & Telegram Streaming Engine

Platform bot Telegram multimedia & streaming serba-guna dengan integrasi 15+ provider scraper konten (film, series, drakor, dracin, anime, manga/manhwa, video dewasa), didukung engine bypass Cloudflare Turnstile/Juicy berbasis Node.js, AI Stable Diffusion generator, dan sistem multi-proxy rotasi.

---

## 🚀 Fitur Utama & Modul Scraper

### 1. Provider Streaming & Indeks Film/Serial
* **Drakor & Asian Drama:** `scraper_drbest.py` & `index_drbest.py`
* **Drama China (Dracin):** `scraper_dracin.py` & `index_dracin.py`
* **Bioskop & LayarKaca21:** `scraper_lk21.py` & `scraper_film.py`
* **Short Drama / Series:** `scraper_series.py`
* **Media Indo:** `scraper_indo.py`
* **China Media Stream:** `scraper_china.py`

### 2. Anime, Manga, & Adult Entertainment
* **Manga / Manhwa / Doujin:** `scraper_nh.py`, `scraper_nhen.py`, `index_nh.py`, `scraper_hentai.py`
* **JAV & Video Databases:** `scraper_javdb.py`, `scraper_nsfw.py`, `scraper_porntrex.py`, `scraper_candy.py`, `scraper_redgifs.py`, `scraper_erome.py`, `scraper_cam.py`
* **Creators Content Aggregator:** `scraper_kemono.py` (`kemono_creators.json`), `scraper_coomer.py` (`coomer_creators.json`)
* **Anime Discovery:** `scraper_kitsu.py`, `scraper_kdj.py`

### 3. AI & Stable Diffusion Engine
* **AI Image Generation:** `sd_client.py` terintegrasi dengan backend GPU Oracle Cloud (`setup_oracle_sd.sh`).
* **Scraper AI Discovery:** `scraper_ai2.py` & `index_ai2.py`.

### 4. Bypass Engine & Resolusi Browser
* **Headless Resolver (Node.js):** `run_juicy.js` dan `debug_juicy.js` untuk bypass anti-bot JavaScript kompleks dan ekstraksi direct video stream link.
* **Stream Resolver:** `juicy_resolve.py` & `browser_fetch.py`.
* **Multi-Proxy Rotation:** Mendukung pool proxy rotasi otomatis (`.dr_good_proxies`, `.ws_farm_proxies.txt`).

---

## 🛠️ Persyaratan Sistem

* **Python 3.11+**
* **Node.js 18+** (untuk modul bypass `juicy`)
* **Playwright / Camoufox** (jika menggunakan browser resolver)
* **Virtual Display (`Xvfb`)** untuk lingkungan server headless.

---

## 📦 Panduan Instalasi & Menjalankan

1. **Clone Repositori:**
   ```bash
   git clone https://github.com/zonesky-1/xh-stream-bot.git
   cd xh-stream-bot
   ```

2. **Pasang Dependensi Python:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Konfigurasi Lingkungan (`.env`):**
   Salin file contoh konfigurasi dan masukkan Token Bot Telegram:
   ```bash
   cp .env.example .env
   # Edit .env dan masukkan BOT_TOKEN Anda
   ```

4. **Jalankan Bot:**
   ```bash
   bash run.sh
   # atau langsung via Python
   python3 bot.py
   ```

---

## 🔒 Keamanan & Data Sensitif

* File `.env`, token bot, cache session (`states.pkl`, `stats.pkl`, `prefs.pkl`), dan log aktivitas diabaikan secara otomatis oleh `.gitignore` untuk mencegah kebocoran kredensial.
