# language: Python 3.11, file: bot.py, target: Telegram (python-telegram-bot v21+), VPS Linux
from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import pickle
import re
import random
import time
import types
import uuid
from collections import OrderedDict
from pathlib import Path

import httpx
from PIL import Image
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      InputMediaDocument, InputMediaPhoto, Update)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

import scraper
import scraper_dracin
import scraper_drbest
import scraper_candy
import scraper_film
import scraper_ai2
import scraper_lk21
import scraper_epai
import scraper_series
import scraper_nsfw
import sd_client
import scraper_kdj
import scraper_nh
import scraper_hentai
import scraper_indo

BASE_DIR = Path(__file__).resolve().parent
DL_DIR = BASE_DIR / "dl"
LOG_FILE = BASE_DIR / "bot.log"

WELCOME = (
    "🔞 <b>xHamster Bot</b>\n\n"
    "pilih menu di bawah — atau langsung ketik perintahnya:\n\n"
    "🔍 <code>/cari &lt;judul&gt;</code> — cari apa aja\n"
    "kalau tombol basi, /help lagi aja."
)

# menu tombol: key → (label, teks cara pakai)
MENU = {
    "film": ("🎬 Film &amp; Series",
             "🎬 <b>Film (LK21 — 27rb mainstream)</b>\n\n"
             "<code>/film &lt;judul&gt;</code> — cari judul\n"
             "kosong = film terbaru\n\n"
             "<b>filter arsip:</b>\n"
             "• <code>/film genre:horror</code> (aksi, komedi, "
             "percintaan, animasi…)\n"
             "• <code>/film tahun:2024</code>\n"
             "• <code>/film negara:jepang</code> (korea, china, "
             "amerika…)\n\n"
             "🇮🇩 semua film <b>subtitle Indonesia</b> "
             "(di-burn ke video)\n"
             "contoh: <code>/film genre:komedi negara:jepang</code>"),
    "lain": ("⚙️ Utilitas (stat/hemat/acak)",
             "⚙️ <b>Utilitas</b>\n\n"
             "<code>/stat</code> — statistik pemakaian bot\n"
             "<code>/acak genre:horror</code> — rekomendasi random\n"
             "<code>/hemat on|off</code> — Nonton default 360p (hemat kuota)\n"
             "<code>/lanjut</code> — video terakhir lu\n"
             "<code>/koleksi</code> — daftar simpanan\n"
             "<code>/sub genre:horror</code> — notif film baru\n\n"
             "semua fitur lain tetep bisa diketik manual."),
    "komik": ("📚 Komik (Doujin)",
              "📚 <b>Komik Doujin (KomikDoujin)</b>\n\n"
              "<code>/komik &lt;judul&gt;</code> — manhwa/doujin\n"
              "kosong = terbaru\n\n"
              "📖 mode strip: semua chapter di-flatten\n"
              "kompres ringan biar enak digeser\n"
              "✅ tandain selesai baca"),
    "ai": ("🤖 AI Video",
           "🤖 <b>AI Porno</b>\n\n"
           "<code>/ai [judul]</code> — Candy AI Shorts\n"
           "seri porno AI, EP awal <b>gratis</b>\n\n"
           "<code>/ai2 [judul]</code> — Swaplse\n"
           "1.891 video AI, <b>semua gratis</b>, tanpa login\n"
           "contoh: <code>/ai2 stepmom</code>"),
    "dracin": ("🎭 Dracin",
               "🎭 <b>Drama China 18+</b>\n\n"
               "<code>/dracin [judul]</code> — dracinema (189rb)\n"
               "<code>/dracin2 [judul]</code> — dracin.best\n"
               "full episode <b>tanpa login</b>\n\n"
               "kosong = terbaru • klik EP = langsung nonton\n"
               "contoh: <code>/dracin love</code>"),
    "amatir": ("🇨🇳 China Amatir",
               "🇨🇳 <b>Bokep China Amatir (Playable)</b>\n\n"
               "<code>/amatir</code> — daftar video amatir terbaru\n"
               "<code>/amatir [kata]</code> — cari spesifik (hotel, pijat, dll)\n"
               "Langsung bisa ditonton & diunduh di Telegram!"),
    "china": ("🇨🇳 China (Madou)",
             "🇨🇳 <b>Bokep China / Madou Media</b>\n\n"
             "<code>/china</code> — video populer\n"
             "<code>/china [kata]</code> — cari judul/model\n"
             "cover + magnet full resolution"),
    "jav": ("📀 JAV (magnet)",
            "📀 <b>JAV — JavDB</b>\n\n"
            "<code>/jav &lt;kode&gt;</code> — cari JAV\n"
            "<code>/jav SSIS-001</code>\n\n"
            "hasil: cover + <b>link magnet</b>\n"
            "paste magnet ke torrent app\n"
            "buat download full (5GB)"),
    "ptx": ("🔥 PornTrex",
            "🔥 <b>PornTrex (video barat)</b>\n\n"
            "<code>/ptx &lt;kata&gt;</code>\n"
            "contoh: <code>/ptx pov</code>\n\n"
            "download + kirim langsung\n"
            "sebagai video playable"),
    "mdx": ("📚 MangaDex (doujin)",
            "📚 <b>MangaDex Doujin 18+</b>\n\n"
            "<code>/mdx &lt;judul&gt;</code>\n"
            "contoh: <code>/mdx netorare</code>\n\n"
            "chapter → kirim album halaman\n"
            "rating pornographic prioritized"),
    "anime": ("📺 Info Anime",
              "📺 <b>Info Anime (Kitsu)</b>\n\n"
              "<code>/anime &lt;judul&gt;</code>\n"
              "contoh: <code>/anime solo leveling</code>\n\n"
              "score + episode + tahun + poster\n"
              "sinopsis singkat"),
    "meme": ("😂 Meme",
             "😂 <b>Meme Random</b>\n\n"
             "<code>/meme</code>\n"
             "meme-api.com — random\n"
             "klik = meme baru"),
    "wsg": ("🖼️ 4chan /wsg/",
            "🖼️ <b>4chan /wsg/ Random</b>\n\n"
             "<code>/wsg</code>\n"
             "random image work-safe/gif\n"
             "klik = gambar lain"),
    "jelajah": ("🧭 Jelajah (tanpa judul)",
             "🧭 <b>JELAJAH — tanpa perlu tahu judul</b>\n" +
             "Ketuk tombol, langsung keluar daftar terbaru/populer.\n" +
             "\n" +
             "<code>/jelajah</code> — dashboard\n" +
             "<code>/acak</code> — rekomendasi acak\n" +
             "\n" +
             "bisa juga command tanpa judul:\n" +
             "<code>/jav</code> <code>/ptx</code> <code>/mdx</code> <code>/anime</code> <code>/film</code> <code>/series</code>"),
    "gen": ("🎨 Generate (SD)", 
            "🎨 <b>Generate Gambar AI</b> (Stable Diffusion)\n\n"
            "<code>/gen [prompt]</code>\n"
            "contoh: <code>/gen catgirl maid solo</code>\n"
            "CPU ARM ~1-3 menit/gambar"),
    "r34": ("🔞 Gambar Dewasa", 
            "🔞 <b>Gambar Dewasa</b> (rule34/e621)\n\n"
            "<code>/r34</code> — random\n"
            "<code>/r34 [tag]</code> — spesifik\n"
            "tombol 🎲 = gambar lain\n"
            "contoh: <code>/r34 catgirl solo</code>\n\n"
            "tag anak-anak = DITOLAK"),
    "hentai": ("😈 Hentai",
               "😈 <b>Hentai Video</b>\n\n"
               "<code>/hentai [judul]</code> — video hentai\n"
               "<code>/hvid [judul]</code> — hentai <b>sub Indo</b>\n"
               "video per episode, semua gratis\n\n"
               "contoh: <code>/hvid isekai</code>"),
    "series": ("📺 TV Series",
               "📺 <b>TV Series</b> (sparkott)\n\n"
               "<code>/series</code> — rilis terbaru\n"
               "<code>/series [judul]</code> — cari series\n"
               "964 series, <b>sub Indo otomatis</b>\n"
               "contoh: <code>/series euphoria</code>"),
    "manhwa": ("📖 Manhwa",
               "📖 <b>Manhwa / Doujin</b>\n\n"
               "<code>/manhwa [query]</code> — manhwa/doujin\n"
               "default: \"manhwa\"\n\n"
               "<code>/manhwaid [query]</code> — doujin "
               "<b>bahasa Indonesia</b> (kosong = terbaru)\n\n"
               "mode strip scroll + anti-basi + ✅ selesai"),
    "cari": ("🔍 Cari",
             "🔍 <b>Cari apa aja</b>\n\n"
             "<code>/cari &lt;judul&gt;</code> — atau langsung "
             "ketik judulnya aja\n\n"
             "hasil per halaman + navigasi ⬅️ ➡️\n"
             "klik angka → detail + thumbnail\n\n"
             "▶️ Nonton — streaming di chat\n"
             "⬇️ Download — file mp4\n"
             "🌐 Situs — halaman aslinya"),
}


def menu_kb() -> InlineKeyboardMarkup:
    """Keyboard menu utama — semua fitur kelihatan."""
    rows = []
    order = [
        ["film", "series", "komik"],
        ["manhwa", "jav", "china"],
        ["hentai", "ptx", "mdx"],
        ["anime", "meme", "wsg"],
        ["r34", "ai", "gen"],
        ["jelajah", "cari", "lain"],
    ]
    for row in order:
        rows.append([InlineKeyboardButton(MENU[k][0], callback_data=f"mn|{k}")
                     for k in row])
    return InlineKeyboardMarkup(rows)


def menu_detail_kb(key: str) -> InlineKeyboardMarkup:
    """Detail satu menu + tombol kembali."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Menu", callback_data="mn|back"),
        InlineKeyboardButton(MENU[key][0], callback_data=f"mn|{key}"),
    ]])


async def h_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    key = q.data.split("|", 1)[1]
    try:
        if key == "back" or key not in MENU:
            await q.edit_message_text(WELCOME, parse_mode=ParseMode.HTML,
                                      reply_markup=menu_kb())
        else:
            await q.edit_message_text(MENU[key][1], parse_mode=ParseMode.HTML,
                                      reply_markup=menu_detail_kb(key))
    except TelegramError as e:
        log.warning("menu edit gagal: %s", e)
    try:
        await q.answer()
    except Exception:
        pass


# ── allowlist: hanya ID tersimpan yang boleh pakai bot ─────────────────────
ADMINS_FILE = BASE_DIR / "admins.json"
OWNER_ID = 7998819216                     # user utama (ID Telegram lu)
ALLOWED_IDS: set = set()


def _load_admins():
    global OWNER_ID, ALLOWED_IDS
    try:
        d = json.loads(ADMINS_FILE.read_text())
        OWNER_ID = int(d.get("owner", OWNER_ID))
        ALLOWED_IDS = {int(x) for x in d.get("allowed", [])}
    except Exception:
        ALLOWED_IDS = set()
    ALLOWED_IDS.add(OWNER_ID)


def _save_admins():
    try:
        ADMINS_FILE.write_text(json.dumps(
            {"owner": OWNER_ID, "allowed": sorted(ALLOWED_IDS)}, indent=1))
    except Exception:
        log.exception("simpan admins gagal")


async def _notify_owner(context, note: str, update: Update = None):
    """Kirim catatan + forward pesan asli ke owner (biar tau siapa yg chat)."""
    try:
        await context.bot.send_message(OWNER_ID, note, parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning("kirim note owner gagal: %s", e)
    if update is not None:
        msg = update.effective_message
        chat = update.effective_chat
        if msg is not None and chat is not None:
            try:
                await context.bot.forward_message(OWNER_ID, chat.id,
                                                  msg.message_id)
            except Exception as e:
                log.warning("forward ke owner gagal: %s", e)


async def _gate_ok(update: Update, context) -> bool:
    """True = boleh lanjut. SEMUA chat non-owner di-forward ke owner."""
    u = update.effective_user
    chat = update.effective_chat
    if u is None or chat is None:
        return True
    if u.id == OWNER_ID:
        return True
    nama = esc(u.full_name or "?")
    un = f"@{u.username}" if u.username else "-"
    terizinkan = u.id in ALLOWED_IDS
    tag = "✅ user terizinkan" if terizinkan else "⛔ user tak dikenal"
    await _notify_owner(
        context,
        f"{tag}\n{nama} ({un}) · id <code>{u.id}</code>\nchat: <code>{chat.id}</code>",
        update)
    if terizinkan:
        return True
    try:
        await update.effective_message.reply_text(
            "⛔ Bot private — ID lu belum diizinkan admin.\n"
            "Pesan lu udah diteruskan ke admin.")
    except Exception:
        pass
    return False


def _protect(fn):
    """Bungkus handler → cek allowlist dulu (dipasang di build_app)."""
    async def wrapper(update, context):
        if not await _gate_ok(update, context):
            return
        return await fn(update, context)
    wrapper.__name__ = getattr(fn, "__name__", "h")
    wrapper._gate = True
    return wrapper


async def h_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only kelola allowlist: /admin add|del|list <id>."""
    u = update.effective_user
    if u is None or u.id != OWNER_ID:
        return
    args = context.args or []
    if not args or args[0] == "list":
        ids = ", ".join(str(i) for i in sorted(ALLOWED_IDS)) or "(kosong)"
        await update.message.reply_text(
            f"👥 allowlist (yg boleh pakai bot):\n<code>{ids}</code>",
            parse_mode=ParseMode.HTML)
        return
    cmd = args[0].lower()
    if len(args) < 2 or not args[1].lstrip("-").isdigit():
        await update.message.reply_text(
            "pakai: /admin add 123456 • /admin del 123456 • /admin list")
        return
    tid = int(args[1])
    if cmd == "add":
        ALLOWED_IDS.add(tid)
        _save_admins()
        await update.message.reply_text(f"✅ <code>{tid}</code> boleh pakai bot.",
                                        parse_mode=ParseMode.HTML)
    elif cmd == "del":
        if tid == OWNER_ID:
            await update.message.reply_text("owner nggak bisa dihapus.")
            return
        ALLOWED_IDS.discard(tid)
        _save_admins()
        await update.message.reply_text(f"🗑 <code>{tid}</code> diblokir.",
                                        parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            "pakai: /admin add|del|list <id>")


_load_admins()


def _load_token() -> str:
    env = BASE_DIR / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("BOT_TOKEN nggak ada di .env")


TOKEN = _load_token()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("xhbot")

STATES: "OrderedDict[str, dict]" = OrderedDict()
BUSY: set[int] = set()
SEM = asyncio.Semaphore(2)
MEDIA_TIMEOUT = 1200


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def new_state(sp: scraper.SearchPage) -> str:
    qid = uuid.uuid4().hex[:8]
    STATES[qid] = {"sp": sp}
    STATES.move_to_end(qid)
    while len(STATES) > 150:
        STATES.popitem(last=False)
    return qid


def render_list(sp: scraper.SearchPage, qid: str):
    n = len(sp.items)
    head = (f"🔍 <b>{esc(sp.query)}</b> — halaman <b>{sp.page}</b> dari {sp.max_pages}"
            f" (±{sp.max_pages * scraper.RESULTS_PER_PAGE:,} total)\n"
            f"semua hasil halaman ini: <b>{n}</b> video\n\n")
    if not n:
        return (head + "nggak ada hasil — coba kata kunci lain.",
                InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ulang", callback_data=f"p|{qid}|{sp.page}")]]))
    room = 3900 - len(head)
    per = max(24, room // n)
    lines = []
    for it in sp.items:
        t = esc(it.title)
        if len(t) > per:
            t = t[: per - 1] + "…"
        meta = " · ".join(x for x in (it.duration, it.views) if x)
        line = f"<b>{it.idx}.</b> {t}"
        if meta:
            line += f" <i>({esc(meta)})</i>"
        lines.append(line)
    text = head + "\n".join(lines)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for it in sp.items:
        row.append(InlineKeyboardButton(str(it.idx), callback_data=f"k|{qid}|{it.idx}"))
        if len(row) == 6:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[InlineKeyboardButton] = []
    if sp.page > 1:
        nav.append(InlineKeyboardButton("⬅️ prev", callback_data=f"p|{qid}|{sp.page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {sp.page}/{sp.max_pages}", callback_data=f"noop|{qid}"))
    if sp.page < sp.max_pages:
        nav.append(InlineKeyboardButton("next ➡️", callback_data=f"p|{qid}|{sp.page + 1}"))
    rows.append(nav)
    return text, InlineKeyboardMarkup(rows)


def detail_caption(it: scraper.Result) -> str:
    meta = " · ".join(x for x in (it.duration, it.views) if x)
    cap = f"<b>{esc(it.title)}</b>"
    if meta:
        cap += f"\n{esc(meta)}"
    cap += ("\n\n▶️ <b>Nonton</b> — streaming langsung di chat (480p)\n"
            "⬇️ <b>Download</b> — file mp4 full quality\n"
            "🌐 buka halaman aslinya di situs")
    return cap


async def fetch_thumb(url: str) -> io.BytesIO | None:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(headers={"User-Agent": scraper.UA},
                                     timeout=20, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        if img.width > 640:
            img = img.resize((640, max(1, int(img.height * 640 / img.width))))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return buf
    except Exception as e:
        log.warning("thumb gagal: %s", e)
        return None


def _state(qid: str) -> dict | None:
    st = STATES.get(qid)
    if st:
        STATES.move_to_end(qid)
    return st


def card_caption(it: scraper.Result, idx: int, total: int) -> str:
    meta = " · ".join(x for x in (it.duration, it.views) if x)
    cap = f"<b>{esc(it.title)}</b>\n{idx}/{total}"
    if meta:
        cap += f" · {esc(meta)}"
    cap += "\n\n▶️ Nonton · ⬇️ Download · 🌐 Situs"
    return cap


def card_kb(sp: scraper.SearchPage, qid: str, idx: int):
    total = len(sp.items)
    it = sp.items[idx - 1]
    nav: list[InlineKeyboardButton] = []
    if idx > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"k|{qid}|{idx - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {idx}/{total}", callback_data=f"noop|{qid}"))
    if idx < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"k|{qid}|{idx + 1}"))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton(f"{h}p", callback_data=f"s|{qid}|{idx}|{h}") for h in (360, 480, 720, 1080)],
        [InlineKeyboardButton("▶️ Nonton", callback_data=f"n|{qid}|{idx}"),
         InlineKeyboardButton("⬇️ Download", callback_data=f"d|{qid}|{idx}"),
         InlineKeyboardButton("🌐 Situs", url=it.url)],
    ])


async def send_card(reply_target, sp: scraper.SearchPage, qid: str, idx: int):
    """Kirim kartu preview (thumbnail + caption + tombol) sebagai pesan baru.
    Balik Message-nya biar caller bisa simpan id-nya ke state."""
    it = sp.items[idx - 1]
    cap = card_caption(it, idx, len(sp.items))
    kb = card_kb(sp, qid, idx)
    photo = await fetch_thumb(it.thumb)
    if photo:
        return await reply_target.reply_photo(photo=photo, caption=cap,
                                              parse_mode=ParseMode.HTML, reply_markup=kb)
    return await reply_target.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)


def _store_card(qid: str, msg) -> None:
    st = STATES.get(qid)
    if st is not None and msg is not None:
        st["card"] = (msg.chat.id, msg.message_id)


async def update_card(q, context, sp: scraper.SearchPage, qid: str, idx: int):
    """Ganti isi kartu preview ke item idx.
    q: CallbackQuery (atau Update — ambil .callback_query-nya).
    Kartu punya message_id sendiri di state, jadi tombol di pesan MANAPUN
    (daftar/kartu lama) tetep ngedit kartu yang bener. Kalau kartu udah
    mati/hilang → kirim kartu baru dan update state."""
    if not hasattr(q, "edit_message_media"):
        q = q.callback_query
    it = sp.items[idx - 1]
    cap = card_caption(it, idx, len(sp.items))
    kb = card_kb(sp, qid, idx)
    photo = await fetch_thumb(it.thumb)
    st = _state(qid)
    card = (st or {}).get("card")
    if card:
        try:
            if photo:
                await context.bot.edit_message_media(
                    chat_id=card[0], message_id=card[1],
                    media=InputMediaPhoto(photo, caption=cap, parse_mode=ParseMode.HTML),
                    reply_markup=kb)
                return
            # kartu lama text-only: coba edit teksnya
            await context.bot.edit_message_text(
                chat_id=card[0], message_id=card[1], text=cap,
                parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except TelegramError as e:
            log.warning("kartu lama gagal diedit (%s) — kirim kartu baru", e)
    # fallback: belum pernah ada kartu / kartu udah mati
    msg = await send_card(q.message, sp, qid, idx)
    _store_card(qid, msg)


async def h_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.HTML,
                                    reply_markup=menu_kb())


async def do_search(update: Update, query: str):
    q = re.sub(r"\s+", " ", query).strip()[:80]
    if not q:
        await update.message.reply_text("format: /cari <judul>\ncontoh: /cari japanese uncensored")
        return
    msg = await update.message.reply_text(f"🔍 mencari <b>{esc(q)}</b>…",
                                          parse_mode=ParseMode.HTML)
    try:
        sp = await scraper.search(q, 1)
    except Exception as e:
        log.exception("search gagal")
        await msg.edit_text(f"❌ gagal nyari: {esc(str(e))[:200]}", parse_mode=ParseMode.HTML)
        return
    qid = new_state(sp)
    text, kb = render_list(sp, qid)
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list gagal: %s", e)
    # kartu preview hasil pertama (thumbnail + tombol ▶️/⬇️ + navigasi ◀️▶️)
    if sp.items:
        try:
            m = await send_card(msg, sp, qid, 1)
            _store_card(qid, m)
        except TelegramError as e:
            log.warning("kirim kartu preview gagal: %s", e)


async def h_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_search(update, " ".join(context.args or []))

async def h_amatir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari video China amatir langsung (playable di Telegram)."""
    q = " ".join(context.args or []).strip()
    query = f"chinese amateur {q}".strip() if q else "chinese amateur"
    await do_search(update, query)



# ─── SHORTCUT LOMPAT ANGKA (halaman manhwa / episode dracin) ──────────────
# Chat → sesi baca/nonton terakhir yang dibuka user. Angka yang diketik di
# chat = lompat langsung (manhwa → halaman n; dracin → picker EP ke halaman
# EP n). Dibersihkan saat ✅ selesai / state basi.
LAST: dict[int, dict] = {}


def _set_last(chat_id: int, kind: str, **kw) -> None:
    LAST[chat_id] = dict(kind=kind, **kw)


def _pop_last(chat_id: int) -> None:
    LAST.pop(chat_id, None)


async def _noop_answer(*_a, **_k):
    return None


async def _shortcut_jump(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         n: int) -> bool:
    """Angka murni + sesi aktif → lompat. True = udah ditangani."""
    chat = update.message.chat.id
    last = LAST.get(chat)
    if not last:
        return False
    if last["kind"] == "m":
        st = _state_m(last["qid"])
        if not st or not (1 <= last["idx"] <= len(st["gp"].items)):
            _pop_last(chat)
            return False
        it = st["gp"].items[last["idx"] - 1]
        try:
            d = await _m_detail(st, it)
        except Exception as e:
            log.exception("shortcut lompat halaman gagal")
            await update.message.reply_text(
                f"❌ gagal: {esc(str(e))[:120]}", parse_mode=ParseMode.HTML)
            return True
        if n > d.pages:
            await update.message.reply_text(
                f"📟 halaman cuma {d.pages} — angka kelewat")
            return True
        # shim callback_query → pakai mesin reader yang sama (edit in-place)
        shim = types.SimpleNamespace(
            data=f"mr|{last['qid']}|{last['idx']}|{n}",
            message=update.message, answer=_noop_answer)
        orig = update.callback_query
        update.callback_query = shim
        try:
            await m_read(update, context, last["qid"], last["idx"], n)
        finally:
            update.callback_query = orig
        return True
    if last["kind"] == "d":
        st = _state_d(last["qid"])
        if not st or not (1 <= last["idx"] <= len(st.get("items", []))):
            _pop_last(chat)
            return False
        e0, e1 = st.get("eps", {}).get(last["idx"], (1, 0))
        if e1 < e0 or not (e0 <= n <= e1):
            await update.message.reply_text(
                f"📟 EP {n} nggak ada di judul ini (EP {e0}–{e1})")
            return True
        ep_page = (n - e0) // 12 + 1
        kb = d_eps_kb(last["qid"], last["idx"], ep_page, e0, e1,
                      last.get("site", ""))
        mid = last.get("msg")
        try:
            if mid:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat, message_id=mid, reply_markup=kb)
            else:
                await update.message.reply_text(
                    f"🎯 EP {n}:", reply_markup=kb)
        except TelegramError as e:
            log.warning("shortcut picker EP gagal: %s", e)
            await update.message.reply_text(f"🎯 EP {n}:", reply_markup=kb)
        return True
    return False


async def h_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    # ketik ANGKA pas sesi baca/nonton aktif = shortcut lompat
    if txt.isdigit() and int(txt) > 0:
        if await _shortcut_jump(update, context, int(txt)):
            return
    await do_search(update, txt)


async def show_detail(update: Update, qid: str, idx: int):
    q = update.callback_query
    st = _state(qid)
    if not st or not (1 <= idx <= len(st["sp"].items)):
        await q.answer("hasil sudah basi — /cari lagi", show_alert=True)
        return
    it = st["sp"].items[idx - 1]
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Nonton", callback_data=f"n|{qid}|{idx}"),
         InlineKeyboardButton("⬇️ Download", callback_data=f"d|{qid}|{idx}")],
        [InlineKeyboardButton("🌐 Buka di situs", url=it.url)],
        [InlineKeyboardButton("🔙 Kembali ke daftar", callback_data=f"b|{qid}|{idx}")],
    ])
    cap = detail_caption(it)
    photo = await fetch_thumb(it.thumb)
    if photo:
        await q.message.reply_photo(photo=photo, caption=cap, parse_mode=ParseMode.HTML,
                                    reply_markup=kb)
    else:
        await q.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)


async def goto_page(update: Update, qid: str, page: int):
    q = update.callback_query
    st = _state(qid)
    if not st:
        await q.answer("hasil sudah basi — /cari lagi", show_alert=True)
        return
    sp0 = st["sp"]
    if page < 1 or page > sp0.max_pages or page == sp0.page:
        await q.answer()
        return
    await q.answer("⏳ memuat…")
    try:
        sp = await scraper.search(sp0.query, page)
    except Exception as e:
        log.exception("paging gagal")
        try:
            await q.message.reply_text(f"❌ gagal pindah halaman: {esc(str(e))[:200]}",
                                       parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        return
    st["sp"] = sp
    text, kb = render_list(sp, qid)
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list gagal: %s", e)


# limit upload Bot API (tanpa Local Bot API) — di bawah 50MB biar aman dari
# pembulatan/koneksi: file lebih ini TIDAK akan pernah diterima Telegram
TG_UPLOAD_LIMIT = 49 * 1024 * 1024


def _faststart(path: str) -> str:
    """Remux mp4 +faststart (moov di depan) — biar bisa di-seek/rewind
    di player Telegram. Hasil remux ffmpeg -c copy = moov di AKHIR file
    (bukti: ftyp,free,mdat,moov) → player gak bisa rewind."""
    if not path.lower().endswith(".mp4") or not os.path.isfile(path):
        return path
    tmp = path + ".fs.mp4"
    try:
        import subprocess
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
             "-c", "copy", "-movflags", "+faststart", tmp],
            capture_output=True, timeout=900)
        if rc.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            try:
                os.remove(path)
            except OSError:
                pass
            return tmp
        if os.path.isfile(tmp):
            os.remove(tmp)
    except Exception as e:
        log.info("faststart dilewati: %s", e)
    return path


def _shrink(path: str, max_bytes: int) -> str:
    """Re-encode h264 kalau file > max_bytes — biar tetap dikirim sebagai
    VIDEO (bisa ditonton), bukan part zip. Coba crf 26→30→34."""
    if not os.path.isfile(path) or os.path.getsize(path) <= max_bytes:
        return path
    import subprocess
    for crf in (26, 30, 34):
        tmp = path + f".sh{crf}.mp4"
        try:
            rc = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                 "-vf", "scale='min(1280,iw)':-2",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                 "-c:a", "aac", "-b:a", "128k",
                 "-movflags", "+faststart", tmp],
                capture_output=True, timeout=3600)
            if (rc.returncode == 0 and os.path.isfile(tmp)
                    and os.path.getsize(tmp) <= max_bytes):
                log.info("kompres: %s → %.1fMB (crf %s)",
                         os.path.basename(path)[:40],
                         os.path.getsize(tmp) / 1048576, crf)
                try:
                    os.remove(path)
                except OSError:
                    pass
                return tmp
            if os.path.isfile(tmp):
                os.remove(tmp)
        except Exception as e:
            log.warning("kompres crf %s gagal: %s", crf, e)
    return path


# ── antrian download per chat (serial, bukan nolak) ──
from collections import deque as _deq
_QUEUES: dict = {}          # chat → deque[(label, coro_factory)]
_WORKING: set = set()       # chat yang lagi di-drain worker


async def _enqueue(chat: int, label: str, job):
    """Masukin job ke antrian per chat. Kalau chat idle → langsung jalan."""
    q = _QUEUES.setdefault(chat, _deq())
    q.append((label, job))
    if chat in _WORKING:
        return len(q)                       # masih ada yang jalan → antri
    _WORKING.add(chat)
    BUSY.add(chat)
    try:
        while _QUEUES.get(chat):
            lbl, jb = _QUEUES[chat].popleft()
            try:
                await jb()
            except Exception:
                log.exception("antrian job gagal: %s", lbl)
    finally:
        _WORKING.discard(chat)
        BUSY.discard(chat)
        _QUEUES.pop(chat, None)
    return 0


async def _send_retry(send, *, attempts: int = 3, delays=(4, 12)):
    """Jalankan coroutine kirim file; retry cuma utk NetworkError (koneksi putus
    pas upload — httpx.ReadError dkk). BadRequest (file ditolak API) lempar
    langsung tanpa retry."""
    for i in range(attempts):
        try:
            return await send()
        except (BadRequest, Forbidden):
            # ditolak API permanen (file terlalu besar dll) — jangan retry
            raise
        except (NetworkError, TimedOut):
            # NB: BadRequest/Forbidden SUBCLASS NetworkError — urutan except penting!
            if i == attempts - 1:
                raise
            w = delays[min(i, len(delays) - 1)]
            log.warning("upload putus/timeout — coba lagi dalam %ds (%d/%d)", w, i + 2, attempts)
            await asyncio.sleep(w)


async def run_media(update: Update, qid: str, idx: int, mode: str,
                    context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    st = _state(qid)
    if not st or not (1 <= idx <= len(st["sp"].items)):
        await q.answer("hasil sudah basi — /cari lagi", show_alert=True)
        return
    chat = q.message.chat.id
    if chat in BUSY:
        await q.answer("⏳ masih memproses permintaan sebelumnya…")
        return
    await q.answer()
    it = st["sp"].items[idx - 1]
    BUSY.add(chat)
    detail = q.message
    kb = detail.reply_markup
    if mode == "stream":
        label = "Streaming 480p"
    elif mode.startswith("h"):
        label = f"Streaming {mode[1:]}p"
    else:
        label = "Download full quality"
    path: str | None = None

    async def set_cap(text: str, markup=None):
        try:
            await detail.edit_caption(caption=text, parse_mode=ParseMode.HTML,
                                      reply_markup=markup)
        except TelegramError as e:
            log.info("caption edit dilewati: %s", e)

    try:
        await detail.edit_reply_markup(None)
        await set_cap(f"⏳ <b>{label}</b> — ambil info video…", None)
        info = await asyncio.wait_for(scraper.resolve(it.url), 90)
        fmt = scraper.pick_format(info, mode)
        loop = asyncio.get_running_loop()
        state = {"last": 0.0, "pct": -1}

        def progress(done: int, total: int):
            if total <= 0 or done < 0:
                return
            pct = int(done * 100 / total)
            now = time.monotonic()
            if pct == state["pct"]:
                return
            if pct < 100 and now - state["last"] < 2.5:
                return
            state["pct"] = pct
            state["last"] = now
            asyncio.run_coroutine_threadsafe(
                set_cap(f"⏳ <b>{label}</b> — {pct}% ({done / 1048576:.1f}/{total / 1048576:.1f} MB)",
                        None),
                loop)

        _dlErr = None
        for _att in (1, 2):
            try:
                async with SEM:
                    path = await asyncio.wait_for(
                        asyncio.to_thread(scraper.download_sync, it.url, fmt,
                                          str(DL_DIR), progress),
                        MEDIA_TIMEOUT)
                _dlErr = None
                break
            except Exception as _e:
                _dlErr = _e
                log.warning("download att %s gagal: %s", _att, _e)
                await asyncio.sleep(6)
        if _dlErr is not None:
            raise _dlErr

        path = _faststart(path)          # moov di depan → bisa rewind
        if 48 * 1048576 < os.path.getsize(path) <= 200 * 1048576:
            path = _shrink(path, 46 * 1048576)   # kompres biar tetep video
        size = os.path.getsize(path)
        safe = re.sub(r"[^\w .&+-]", "_", it.title).strip(" ._")[:70] or "video"
        safe += ".mp4"
        meta = " · ".join(x for x in (it.duration, it.views) if x)
        cap = f"<b>{esc(it.title)}</b>\n{esc(meta)}\n✅ {label} · {size / 1048576:.1f} MB"

        # cek limit upload SEBELUM buang waktu upload (Telegram nolak >50MB)
        if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
            warn_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{h}p", callback_data=f"s|{qid}|{idx}|{h}")
                 for h in (360, 480, 720)],
                [InlineKeyboardButton("🌐 Situs", url=it.url)],
            ])
            await set_cap(
                f"⚠️ <b>file {size / 1048576:.0f} MB kegedean buat Telegram</b>\n"
                f"limit upload bot = 50MB (server lokal belum aktif).\n"
                f"Pilih resolusi lebih kecil buat didownload:", warn_kb)
            log.warning("file dilewati (limit 50MB): %s %.1fMB", it.title[:40],
                        size / 1048576)
            return

        await set_cap(f"⬆️ <b>{label}</b> — upload ke Telegram…", None)
        # semua video ≤ 48MB dikirim sebagai VIDEO (bisa ditonton langsung),
        # bukan document — document = harus didownload dulu, gak ada player
        if size <= 48 * 1048576:
            try:
                await _send_retry(lambda: context.bot.send_video(
                    chat_id=chat, video=path, caption=cap, parse_mode=ParseMode.HTML,
                    supports_streaming=True, write_timeout=600, read_timeout=180))
            except TelegramError as e:
                log.warning("send_video gagal, fallback document: %s", e)
                await _send_retry(lambda: context.bot.send_document(
                    chat_id=chat, document=path, filename=safe, caption=cap,
                    parse_mode=ParseMode.HTML, write_timeout=900, read_timeout=180))
        else:
            await _send_retry(lambda: context.bot.send_document(
                chat_id=chat, document=path, filename=safe, caption=cap,
                parse_mode=ParseMode.HTML, write_timeout=900, read_timeout=180))
        await set_cap(f"✅ <b>selesai</b> — {label} ada di atas", kb)
        log.info("media terkirim: %s (%s, %.1f MB)", it.title[:50], mode, size / 1048576)
        _bump("video")
        _lanjut_set(chat, "hentai", it.title, it.url)
    except asyncio.TimeoutError:
        log.warning("media timeout: %s", it.url)
        await set_cap("❌ timeout — sumber lagi apes, coba lagi", kb)
    except Exception as e:
        log.exception("media gagal")
        msg = f"❌ gagal: {esc(str(e))[:400]}"
        if "REQUEST_ENTITY_TOO_LARGE" in str(e) or "too big" in str(e).lower():
            msg = ("❌ file kegedean (limit bot 50MB) — pilih resolusi "
                   "lebih kecil lewat tombol di kartu")
        await set_cap(msg, kb)
    finally:
        BUSY.discard(chat)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


async def h_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data or ""
    parts = data.split("|")
    kind = parts[0]
    qid = parts[1] if len(parts) > 1 else ""
    try:
        num = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        num = 0
    if kind == "noop":
        await update.callback_query.answer()
    elif kind == "s":
        # streaming pada resolusi pilihan (360/480/720/1080)
        h = parts[3] if len(parts) > 3 else "480"
        st = _state(qid)
        if not st or not h.isdigit() or not (1 <= num <= len(st["sp"].items)):
            await update.callback_query.answer("hasil sudah basi — /cari lagi", show_alert=True)
            return
        await run_media(update, qid, num, f"h{int(h)}", context)
    elif kind == "k":
        # lompat kartu preview ke angka ini (dari daftar atau ◀️/▶️ di kartu)
        st = _state(qid)
        if not st or not (1 <= num <= len(st["sp"].items)):
            await update.callback_query.answer("hasil sudah basi — /cari lagi", show_alert=True)
            return
        it = st["sp"].items[num - 1]
        await update.callback_query.answer(
            f"▶️ {num}/{len(st['sp'].items)} · {it.title[:60]}")
        try:
            await update_card(update, context, st["sp"], qid, num)
        except TelegramError as e:
            log.warning("update kartu gagal: %s", e)
    elif kind == "v":
        await show_detail(update, qid, num)
    elif kind == "b":
        try:
            await update.callback_query.message.delete()
        except TelegramError:
            pass
        await update.callback_query.answer()
    elif kind == "p":
        await goto_page(update, qid, num)
    elif kind in ("n", "d"):
        mode = "best" if kind == "d" else "stream"
        _u = getattr(update, "effective_user", None)
        if kind == "n" and _u is not None and _pref(_u.id, "hemat"):
            mode = "h360"        # mode hemat: Nonton default 360p
        await run_media(update, qid, num, mode, context)


# ─── MANHWA (HentaiFox) ─────────────────────────────────────────────

STATES_M: "OrderedDict[str, dict]" = OrderedDict()
MAX_ZIP_BYTES = 46 * 1024 * 1024  # aman di bawah limit upload Telegram 50MB


def new_state_m(gp: scraper_hentai.GalleryPage) -> str:
    qid = uuid.uuid4().hex[:8]
    STATES_M[qid] = {"gp": gp, "details": {}}
    STATES_M.move_to_end(qid)
    while len(STATES_M) > 120:
        STATES_M.popitem(last=False)
    return qid


def _mod(st: dict):
    """Sumber galeri untuk state ini: dojing.net (utk /manhwaid) atau HentaiFox."""
    return st.get("mod") or scraper_hentai


def _state_m(qid: str) -> dict | None:
    st = STATES_M.get(qid)
    if st:
        STATES_M.move_to_end(qid)
    return st


def render_mlist(gp: scraper_hentai.GalleryPage, qid: str):
    n = len(gp.items)
    head = (f"🌸 <b>{esc(gp.query)}</b> — halaman <b>{gp.page}</b> dari {gp.max_pages}\n"
            f"gallery di halaman ini: <b>{n}</b>\n\n")
    if not n:
        return (head + "nggak ada hasil — coba kata kunci lain.",
                InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ulang", callback_data=f"mp|{qid}|{gp.page}")]]))
    lines = []
    for it in gp.items:
        t = esc(it.title[:90])
        cat = f" <i>({esc(it.cat)})</i>" if it.cat else ""
        lines.append(f"<b>{it.idx}.</b> {t}{cat}")
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for it in gp.items:
        row.append(InlineKeyboardButton(str(it.idx), callback_data=f"mv|{qid}|{it.idx}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[InlineKeyboardButton] = []
    if gp.page > 1:
        nav.append(InlineKeyboardButton("⬅️ prev", callback_data=f"mp|{qid}|{gp.page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {gp.page}/{gp.max_pages}", callback_data=f"mo|{qid}"))
    if gp.page < gp.max_pages:
        nav.append(InlineKeyboardButton("next ➡️", callback_data=f"mp|{qid}|{gp.page + 1}"))
    rows.append(nav)
    return head + "\n".join(lines), InlineKeyboardMarkup(rows)


# ── /series — TV SERIES (sparkott: 964 series, sub Indo VTT bawaan) ─────
import glob

STATE_SERIES: Dict[str, dict] = {}


def _state_series(qid):
    st = STATE_SERIES.get(qid)
    if not st:
        return None
    if time.time() - st["ts"] > 3600:
        STATE_SERIES.pop(qid, None)
        return None
    return st


def _series_render(q, page, items, total):
    lines = [f"📺 <b>TV Series — {esc(q or 'rilis terbaru')}</b>",
             f"tot: {total} series · hal {page}", ""]
    kb = []
    for i, it in enumerate(items, 1):
        yr = f" ({it['year']})" if it.get("year") else ""
        lines.append(f"{i} • {esc(it['title'])}{yr}")
        kb.append([InlineKeyboardButton(
            f"{i} · {it['title'][:58]}",
            callback_data=f"srs|__qid__|{i}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"srs|__qid__|p{page - 1}"))
    nav.append(InlineKeyboardButton(f" hal {page} ", callback_data="noop"))
    if page * 20 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"srs|__qid__|p{page + 1}"))
    kb.append(nav)
    return "\n".join(lines), kb


async def h_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    msg = await update.message.reply_text("🔎 nyari series…", parse_mode="HTML")
    try:
        page = 1
        m = re.search(r"h(\d+)$", q)
        if m:
            page = int(m.group(1))
            q = q[: m.start()].strip()
        items, total = await asyncio.to_thread(scraper_series.search, q, page)
    except Exception as e:
        log.exception("series search gagal")
        return await msg.edit_text(f"❌ cari gagal: {esc(str(e)[:150])}",
                                   parse_mode="HTML")
    if not items:
        return await msg.edit_text("hasil kosong", parse_mode="HTML")
    qid = uuid.uuid4().hex
    STATE_SERIES[qid] = {"items": items, "page": page, "total": total,
                         "q": q, "eps": None, "ts": time.time()}
    text, kb = _series_render(q, page, items, total)
    kb2 = [[InlineKeyboardButton(b.text,
                                 callback_data=b.callback_data.replace("__qid__", qid))
            for b in row] for row in kb]
    await msg.edit_text(text, parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(kb2))


async def h_series_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""
    # download episode: ser|qid|epidx
    if action == "ser" and len(parts) >= 4:
        qid = parts[2]
        st = _state_series(qid)
        if not st or not st.get("eps"):
            return await q.answer("hasil sudah basi — /series lagi",
                                   show_alert=True)
        epidx = int(parts[3])
        eps = st["eps"]
        jud = st.get("eps_title", "series")
        if not (1 <= epidx <= len(eps)):
            return await q.answer("episode di luar jangkauan", show_alert=True)
        lbl, url = eps[epidx - 1]
        await q.edit_message_text(
            f"🎬 <b>{esc(jud)}</b> — {esc(lbl)}\n\n"
            "⬇️ download episode… (sub Indo otomatis keburn)",
            parse_mode="HTML")
        t0 = time.time()
        state = {"last": 0.0}

        def prog(i, n):
            if time.time() - state["last"] > 5:
                state["last"] = time.time()

        try:
            out, dur, burned = await asyncio.wait_for(asyncio.to_thread(
                scraper_series.download, url, None, True, prog), MEDIA_TIMEOUT)
        except Exception as e:
            log.exception("series download gagal")
            return await q.edit_message_text(
                f"❌ gagal: {esc(str(e)[:180])}", parse_mode="HTML")
        try:
            out2 = _faststart(out)
            size = os.path.getsize(out2)
            files = []
            if size > TG_UPLOAD_LIMIT:
                out2 = _shrink(out2, int(TG_UPLOAD_LIMIT * 0.94))
                size = os.path.getsize(out2)
            if size <= TG_UPLOAD_LIMIT:
                files = [out2]
            else:
                import subprocess as _sp
                n_part = (size // TG_UPLOAD_LIMIT) + 1
                seglen = max(60, int(dur // n_part) + 1)
                base = os.path.splitext(out2)[0]
                _sp.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out2,
                         "-c", "copy", "-map", "0",
                         "-f", "segment", "-segment_time", str(seglen),
                         "-reset_timestamps", "1", base + "-p%02d.mp4"],
                        capture_output=True, timeout=1800)
                files = sorted(f for f in glob.glob(base + "-p*.mp4"))
            cap = (f"🎬 <b>{esc(jud)}</b> — {esc(lbl)}\n"
                   f"{dur / 60:.0f} menit · {len(files)} part · "
                   f"{'sub Indo ✓' if burned else '⚠️ sub nggak tersedia'} · "
                   f"{time.time() - t0:.0f}s")
            for n_, fp in enumerate(files, 1):
                suf = f" ({n_}/{len(files)})" if len(files) > 1 else ""
                try:
                    await _send_retry(lambda: context.bot.send_video(
                        chat_id=q.message.chat.id, video=open(fp, "rb"),
                        caption=cap + suf, parse_mode="HTML",
                        supports_streaming=True, read_timeout=MEDIA_TIMEOUT,
                        write_timeout=MEDIA_TIMEOUT), attempts=3)
                finally:
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
            await q.edit_message_text("✅ episode terkirim (file sisa dihapus)")
        except Exception as e:
            log.exception("series kirim gagal")
            for fp in glob.glob("series-*.mp4"):
                try:
                    os.remove(fp)
                except OSError:
                    pass
            await q.edit_message_text(f"❌ gagal kirim: {esc(str(e)[:150])}",
                                      parse_mode="HTML")
        return
    if not arg.isdigit():
        if arg.startswith("p") and arg[1:].isdigit():
            st = _state_series(parts[1])
            if not st or not st.get("eps"):
                return await q.answer("hasil sudah basi", show_alert=True)
            page = int(arg[1:])
            eps = st["eps"]
            per = 8
            paged = eps[(page - 1) * per: page * per]
            lines = [f"📺 <b>{esc(st.get('eps_title', 'series'))}</b>",
                     f"tot: {len(eps)} episode · hal {page}", ""]
            kb = []
            for i, (lbl, _) in enumerate(paged):
                gi = (page - 1) * per + i + 1
                lines.append(f"{gi} • {esc(lbl)}")
                kb.append([InlineKeyboardButton(
                    f"{gi} · {lbl}", callback_data=f"srs|ser|{parts[1]}|{gi}")])
            nav = []
            if page > 1:
                nav.append(InlineKeyboardButton(
                    "⬅️", callback_data=f"srs|{parts[1]}|p{page - 1}"))
            nav.append(InlineKeyboardButton(f" hal {page} ",
                                            callback_data="noop"))
            if page * per < len(eps):
                nav.append(InlineKeyboardButton(
                    "➡️", callback_data=f"srs|{parts[1]}|p{page + 1}"))
            kb.append(nav)
            await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(kb))
            return
        return await q.answer("tombol basi", show_alert=True)
    n = int(arg)
    st = _state_series(parts[1])
    if not st:
        return await q.answer("hasil sudah basi — /series lagi", show_alert=True)
    if not st.get("eps"):        # klik judul → ambil daftar episode
        it = st["items"][n - 1]
        await q.edit_message_text("📖 ngambil daftar episode…", parse_mode="HTML")
        try:
            det = await asyncio.to_thread(scraper_series.detail,
                                          it["url"], it.get("id"))
        except Exception as e:
            return await q.edit_message_text(
                f"❌ gagal: {esc(str(e)[:150])}", parse_mode="HTML")
        if not det["eps"]:
            return await q.edit_message_text("series ini belum ada episode-nya")
        st["eps"] = det["eps"]
        st["eps_title"] = det["title"]
    per = 8
    paged = st["eps"][:per]
    lines = [f"📺 <b>{esc(st['eps_title'])}</b>",
             f"tot: {len(st['eps'])} episode · hal 1", ""]
    kb = []
    for i, (lbl, _) in enumerate(paged):
        lines.append(f"{i + 1} • {esc(lbl)}")
        kb.append([InlineKeyboardButton(
            f"{i + 1} · {lbl}", callback_data=f"srs|ser|{parts[1]}|{i + 1}")])
    nav = [InlineKeyboardButton(" hal 1 ", callback_data="noop")]
    if len(st["eps"]) > per:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"srs|{parts[1]}|p2"))
    kb.append(nav)
    await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup(kb))


    try:
        from telegram.error import TimedOut
    except Exception:
        pass
SD_API_URL = os.getenv("SD_API_URL", "http://100.81.10.96:7860").strip()


async def h_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    if not SD_API_URL:
        return await update.message.reply_text(
            "⏸ generator belum online (Oracle A1 lagi disiapkan)")
    if not q:
        return await update.message.reply_text(
            "pakai: /gen [prompt]\ncontoh: /gen catgirl maid solo")
    msg = await update.message.reply_text(
        "🎨 generate… (CPU 8-Core ~30-60 detik)")
    try:
        data = await asyncio.wait_for(asyncio.to_thread(
            sd_client.generate, q, api_base=SD_API_URL), 900)
    except Exception as e:
        log.warning("gen gagal: %s", e)
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:150])}")
    out_path = os.path.join(str(DL_DIR), f"gen_{uuid.uuid4().hex[:8]}.png")
    with open(out_path, "wb") as f:
        f.write(data)

    await msg.edit_text("✅ jadi — kirim…")
    def _make_send():
        return context.bot.send_photo(
            chat_id=update.effective_chat.id, photo=open(out_path, "rb"),
            caption=f"🎨 <code>{esc(q[:200])}</code>", parse_mode="HTML",
            read_timeout=120, write_timeout=120)
    try:
        await _send_retry(_make_send, attempts=3)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ kirim gagal: {esc(str(e)[:120])}")
    finally:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass


async def h_r34(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gambar dewasa acak (rule34 → e621), tag bebas, filter kejam."""
    q = " ".join(context.args or []).strip()
    try:
        it = await asyncio.to_thread(scraper_nsfw.random_post, q)
    except Exception as e:
        log.warning("r34 gagal: %s", e)
        return await update.message.reply_text(
            f"❌ gagal: {esc(str(e)[:120])}")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎲 lainnya", callback_data=f"r34r|{q[:60]}"),
    ]])
    await update.message.reply_photo(
        photo=it["url"],
        caption=f"🔞 <code>{esc(q or 'random')}</code> · score {it['score']}\n"
                f"<i>{esc(it['tags'][:120])}</i>",
        parse_mode="HTML", reply_markup=kb)


async def h_r34_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tag = (q.data.split("|", 1) + [""])[1]
    try:
        it = await asyncio.to_thread(scraper_nsfw.random_post, tag)
    except Exception as e:
        return await q.answer(f"gagal: {str(e)[:60]}", show_alert=True)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎲 lainnya", callback_data=f"r34r|{tag[:60]}"),
    ]])
    try:
        await context.bot.send_photo(
            chat_id=q.message.chat.id, photo=it["url"],
            caption=f"🔞 <code>{esc(tag or 'random')}</code> · score {it['score']}\n"
                    f"<i>{esc(it['tags'][:120])}</i>",
            parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        await q.answer(f"kirim gagal: {str(e)[:60]}", show_alert=True)


# ── BATCH TARGET BARU: /mdx /ptx /anime /meme /wsg ─────────────────────
import scraper_mdx
import scraper_porntrex
import scraper_kitsu

STATE_MDX: Dict[str, dict] = {}
STATE_PTX: Dict[str, dict] = {}


def _st_mdx(qid):
    st = STATE_MDX.get(qid)
    if st and time.time() - st["ts"] > 3600:
        STATE_MDX.pop(qid, None)
        return None
    return st


def _st_ptx(qid):
    st = STATE_PTX.get(qid)
    if st and time.time() - st["ts"] > 3600:
        STATE_PTX.pop(qid, None)
        return None
    return st


# ── /mdx — MangaDex doujin (komik hentai 3 sumber) ─────────────────────
async def h_mdx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    if not q:
        # tanpa judul → doujin terbaru
        msg = await update.message.reply_text("📚 ngambil doujin terbaru…")
        try:
            items = await asyncio.to_thread(scraper_mdx.browse_latest)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        qid = uuid.uuid4().hex
        STATE_MDX[qid] = {"items": items[:10], "ts": time.time()}
        lines = ["📚 <b>MangaDex — doujin terbaru</b>",
                 "<i>tulis /mdx [kata] buat cari spesifik</i>", ""]
        kb = []
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['title'][:56])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                            callback_data=f"mdx|{qid}|{i}")])
        return await msg.edit_text('\n'.join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))
    msg = await update.message.reply_text("🔎 nyari di MangaDex…")
    try:
        items = await asyncio.to_thread(scraper_mdx.search, q)
    except Exception as e:
        log.exception("mdx search gagal")
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not items:
        return await msg.edit_text("hasil kosong")
    qid = uuid.uuid4().hex
    STATE_MDX[qid] = {"items": items[:10], "ts": time.time()}
    lines = [f"📚 <b>MangaDex — {esc(q)}</b>", ""]
    kb = []
    for i, it in enumerate(items[:10], 1):
        tag = "🔥" if "pornographic" in it["rating"] else "·"
        lines.append(f"{i} {tag} {esc(it['title'])}")
        kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                        callback_data=f"mdx|{qid}|{i}")])
    await msg.edit_text("\n".join(lines), parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(kb))


async def h_mdx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    if len(parts) < 3 or not parts[2].isdigit():
        return await q.answer("tombol basi", show_alert=True)
    st = _st_mdx(parts[1])
    if not st:
        return await q.answer("hasil sudah basi — /mdx lagi", show_alert=True)
    it = st["items"][int(parts[2]) - 1]
    await q.edit_message_text(f"📖 {esc(it['title'])}\nngambil daftar chapter…",
                              parse_mode="HTML")
    try:
        chs = await asyncio.to_thread(scraper_mdx.chapters, it["id"])
    except Exception as e:
        return await q.edit_message_text(f"❌ gagal: {esc(str(e)[:120])}",
                                         parse_mode="HTML")
    if not chs:
        return await q.edit_message_text("chapter kosong")
    st["chs"] = chs
    per = 8
    lines = [f"📖 <b>{esc(it['title'])}</b>",
             f"tot: {len(chs)} chapter · hal 1", ""]
    kb = []
    for i, ch in enumerate(chs[:per]):
        lbl = f"Ch {ch['chapter']} {ch['title']}".strip()[:60]
        lines.append(f"{i + 1} • {lbl}")
        kb.append([InlineKeyboardButton(lbl,
                                        callback_data=f"mdxr|{parts[1]}|{i + 1}")])
    nav = [InlineKeyboardButton(" hal 1 ", callback_data="noop")]
    if len(chs) > per:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"mdxp|{parts[1]}|p2"))
    kb.append(nav)
    await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup(kb))


async def h_mdx_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim halaman chapter (album foto)."""
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    if parts[1] == "p":               # navigasi halaman chapter
        qid, pg = parts[2], int(parts[3][1:])
        st = _st_mdx(qid)
        if not st or not st.get("chs"):
            return await q.answer("basi", show_alert=True)
        per = 8
        chs = st["chs"]
        paged = chs[(pg - 1) * per: pg * per]
        lines = [f"📖 <b>{esc(st['items'][0]['title'])}</b>",
                 f"tot: {len(chs)} chapter · hal {pg}", ""]
        kb = []
        for i, ch in enumerate(paged):
            gi = (pg - 1) * per + i + 1
            lbl = f"Ch {ch['chapter']} {ch['title']}".strip()[:60]
            lines.append(f"{gi} • {lbl}")
            kb.append([InlineKeyboardButton(lbl,
                                            callback_data=f"mdxr|{qid}|{gi}")])
        nav = []
        if pg > 1:
            nav.append(InlineKeyboardButton("⬅️",
                        callback_data=f"mdxp|{qid}|p{pg - 1}"))
        nav.append(InlineKeyboardButton(f" hal {pg} ", callback_data="noop"))
        if pg * per < len(chs):
            nav.append(InlineKeyboardButton("➡️",
                        callback_data=f"mdxp|{qid}|p{pg + 1}"))
        kb.append(nav)
        return await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(kb))
    # baca chapter: mdxr|qid|idx
    qid, idx = parts[1], int(parts[2])
    st = _st_mdx(qid)
    if not st or not st.get("chs"):
        return await q.answer("basi", show_alert=True)
    ch = st["chs"][idx - 1]
    await q.edit_message_text(f"📖 ngirim chapter {ch['chapter']}…")
    try:
        pgs = await asyncio.to_thread(scraper_mdx.pages, ch["id"])
    except Exception as e:
        return await q.edit_message_text(f"❌ gagal: {esc(str(e)[:120])}",
                                         parse_mode="HTML")
    cap = f"📖 {ch['chapter']} · {len(pgs)} hal"
    media = []
    for i, u in enumerate(pgs[:30], 1):
        media.append(types.InputMediaPhoto(u, caption=f"{cap}" if i == 1 else None))
    for i in range(0, len(media), 10):
        try:
            await _send_retry(lambda m=media[i:i + 10]: context.bot.send_media_group(
                chat_id=q.message.chat.id, media=m), attempts=3)
        except Exception as e:
            await q.edit_message_text(f"❌ kirim gagal: {esc(str(e)[:120])}",
                                      parse_mode="HTML")
            return
    await q.edit_message_text(
        f"✅ chapter {ch['chapter']} terkirim ({len(pgs)} hal) · "
        "file sisa dihapus")


# ── /ptx — PornTrex video barat ────────────────────────────────────────
async def h_ptx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    if not q:
        # tanpa judul → video populer
        msg = await update.message.reply_text("🔥 ngambil video populer…")
        try:
            items = await asyncio.to_thread(scraper_porntrex.browse_popular)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        qid = uuid.uuid4().hex
        STATE_PTX[qid] = {"items": items[:10], "ts": time.time()}
        lines = ["🔥 <b>PornTrex — paling populer</b>",
                 "<i>tulis /ptx [kata] buat cari spesifik</i>", ""]
        kb = []
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['title'][:56])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                            callback_data=f"ptxr|{qid}|{i}")])
        return await msg.edit_text('\n'.join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))
    msg = await update.message.reply_text("🔎 nyari di PornTrex…")
    try:
        items = await asyncio.to_thread(scraper_porntrex.search, q)
    except Exception as e:
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not items:
        return await msg.edit_text("hasil kosong")
    qid = uuid.uuid4().hex
    STATE_PTX[qid] = {"items": items[:10], "ts": time.time()}
    lines = [f"🔥 <b>PornTrex — {esc(q)}</b>", ""]
    kb = []
    for i, it in enumerate(items[:10], 1):
        lines.append(f"{i} • {esc(it['title'][:60])}")
        kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                        callback_data=f"ptxr|{qid}|{i}")])
    await msg.edit_text("\n".join(lines), parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(kb))


async def h_ptx_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    if len(parts) < 3 or not parts[2].isdigit():
        return await q.answer("tombol basi", show_alert=True)
    st = _st_ptx(parts[1])
    if not st:
        return await q.answer("hasil sudah basi — /ptx lagi", show_alert=True)
    it = st["items"][int(parts[2]) - 1]
    await q.edit_message_text(f"🎬 {esc(it['title'])}\nngambil link video…",
                              parse_mode="HTML")
    try:
        d = await asyncio.to_thread(scraper_porntrex.detail, it["url"])
    except Exception as e:
        return await q.edit_message_text(f"❌ gagal: {esc(str(e)[:120])}",
                                         parse_mode="HTML")
    t0 = time.time()
    out = os.path.join(str(DL_DIR), f"ptx-{uuid.uuid4().hex[:8]}.mp4")
    try:
        # download mp4 streaming (httpx via scraper session)
        await q.edit_message_text("⬇️ download…", parse_mode="HTML")
        def _dl():
            from curl_cffi import requests as _rq
            s = _rq.Session(impersonate="chrome")
            with s.stream("GET", d["mp4"], timeout=90,
                          headers={"Referer": SITE_REF}) as r:
                r.raise_for_status()
                with open(out, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        f.write(chunk)
            return out
        await asyncio.wait_for(asyncio.to_thread(_dl), MEDIA_TIMEOUT)
        out2 = _faststart(out)
        size = os.path.getsize(out2)
        if size > TG_UPLOAD_LIMIT:
            out2 = _shrink(out2, int(TG_UPLOAD_LIMIT * 0.94))
            size = os.path.getsize(out2)
        cap = f"🔥 <b>{esc(d['title'][:80])}</b>\n{size / 1048576:.1f} MB"
        if size <= TG_UPLOAD_LIMIT:
            await _send_retry(lambda: context.bot.send_video(
                chat_id=q.message.chat.id, video=open(out2, "rb"),
                caption=cap, parse_mode="HTML", supports_streaming=True,
                read_timeout=MEDIA_TIMEOUT, write_timeout=MEDIA_TIMEOUT),
                attempts=3)
        else:
            await q.edit_message_text("⚠️ kegedean buat Telegram, coba yang lain")
            return
        await q.edit_message_text("✅ terkirim (file sisa dihapus)")
    except Exception as e:
        log.exception("ptx gagal")
        await q.edit_message_text(f"❌ gagal: {esc(str(e)[:120])}",
                                  parse_mode="HTML")
    finally:
        for fp in glob.glob(out + "*"):
            try:
                os.remove(fp)
            except OSError:
                pass


SITE_REF = "https://www.porntrex.com/"


# ── /anime — info anime (Kitsu) ────────────────────────────────────────
async def h_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    if not q:
        # tanpa judul → anime top
        msg = await update.message.reply_text("📺 ngambil anime top…")
        try:
            items = await asyncio.to_thread(scraper_kitsu.top_anime)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        qid = uuid.uuid4().hex
        STATE_BROWSE[qid] = {"items": items[:10], "ts": time.time()}
        lines = ["📺 <b>Anime top (ongoing)</b>",
                 "<i>tulis /anime [kata] buat cari spesifik</i>", ""]
        kb = []
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['title'][:56])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                            callback_data=f"jelani|{qid}|{i}")])
        return await msg.edit_text('\n'.join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))
    try:
        items = await asyncio.to_thread(scraper_kitsu.search, q)
    except Exception as e:
        return await update.message.reply_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not items:
        return await update.message.reply_text("hasil kosong")
    it = items[0]
    txt = (f"📺 <b>{esc(it['title'])}</b>\n"
           f"⭐ {it['score']} · {it['eps']} eps · {it['year']} · {it['status']}\n\n"
           f"<i>{esc(it['synopsis'][:400])}</i>")
    try:
        await update.message.reply_photo(photo=it["poster"], caption=txt,
                                         parse_mode="HTML")
    except Exception:
        await update.message.reply_text(txt, parse_mode="HTML")
    if len(items) > 1:
        lain = " · ".join(esc(x["title"][:25]) for x in items[1:4])
        await update.message.reply_text(f"mirip: {lain}", parse_mode="HTML")


# ── /meme — meme random (meme-api) ──────────────────────────────────────
async def h_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import httpx as _hx
    r = await asyncio.to_thread(lambda: _hx.get(
        "https://meme-api.com/gimme", timeout=20).json())
    if not r.get("url"):
        return await update.message.reply_text("❌ meme API gagal")
    try:
        await update.message.reply_photo(
            photo=r["url"],
            caption=f"😂 {esc((r.get('title') or '')[:100])}\n"
                    f"r/{r.get('subreddit', '')}",
            parse_mode="HTML")
    except Exception:
        await update.message.reply_text(r["url"])


# ── /wsg — gambar 4chan /wsg/ random ───────────────────────────────────
async def h_wsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import httpx as _hx

    def _pick():
        c = _hx.Client(timeout=20)
        boards = c.get("https://a.4cdn.org/wsg/threads.json").json()
        ths = []
        for b in boards:
            for t in b.get("threads", []):
                for f in t.get("files", [])[:1]:
                    if f.get("ext") in (".jpg", ".png", ".webp"):
                        ths.append((f"i{f['tim']}{f['ext']}",
                                    (t.get("sub") or t.get("com") or "wsg")[:80]))
        return ths

    try:
        ths = await asyncio.to_thread(_pick)
    except Exception as e:
        return await update.message.reply_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not ths:
        return await update.message.reply_text("board lagi sepi")
    fn, cap = random.choice(ths)
    url = f"https://i.4cdn.org/wsg/{fn}"
    try:
        await update.message.reply_photo(
            photo=url, caption=f"🖼️ {esc(cap)}", parse_mode="HTML")
    except Exception:
        await update.message.reply_text(url)


# ── /jav — JavDB: search JAV + magnet + cover ─────────────────────────
import scraper_javdb

STATE_JAV: Dict[str, dict] = {}


def _st_jav(qid):
    st = STATE_JAV.get(qid)
    if st and time.time() - st["ts"] > 3600:
        STATE_JAV.pop(qid, None)
        return None
    return st


def card_caption_jav(it: dict, idx: int, total: int) -> str:
    code_str = f"[{it['code']}] " if it.get("code") else ""
    cap = f"📀 <b>{esc(code_str)}{esc(it.get('title', ''))}</b>\n{idx}/{total}"
    cap += "\n\n🧲 Detail & Magnet · 🌐 Situs"
    return cap


def card_kb_jav(qid: str, idx: int, total: int, url: str):
    nav: list[InlineKeyboardButton] = []
    if idx > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"jvk|{qid}|{idx - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {idx}/{total}", callback_data=f"noop|{qid}"))
    if idx < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"jvk|{qid}|{idx + 1}"))
    return InlineKeyboardMarkup([
        nav,
        [
            InlineKeyboardButton("🧲 Detail & Magnet", callback_data=f"jvmg|{qid}|{idx}"),
            InlineKeyboardButton("🌐 Situs", url=url or SITE_REF),
        ],
    ])


async def send_card_jav(reply_target, qid: str, items: list, idx: int):
    it = items[idx - 1]
    cap = card_caption_jav(it, idx, len(items))
    kb = card_kb_jav(qid, idx, len(items), it.get("url", SITE_REF))
    photo = await fetch_thumb(it.get("cover", ""))
    if photo:
        return await reply_target.reply_photo(
            photo=photo, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
    return await reply_target.reply_text(
        cap, parse_mode=ParseMode.HTML, reply_markup=kb)


async def update_card_jav(q, context, qid: str, items: list, idx: int):
    if not hasattr(q, "edit_message_media"):
        q = q.callback_query
    it = items[idx - 1]
    cap = card_caption_jav(it, idx, len(items))
    kb = card_kb_jav(qid, idx, len(items), it.get("url", SITE_REF))
    photo = await fetch_thumb(it.get("cover", ""))
    st = _st_jav(qid)
    card = (st or {}).get("card")
    if card:
        try:
            if photo:
                await context.bot.edit_message_media(
                    chat_id=card[0], message_id=card[1],
                    media=InputMediaPhoto(photo, caption=cap, parse_mode=ParseMode.HTML),
                    reply_markup=kb)
                return
            await context.bot.edit_message_text(
                chat_id=card[0], message_id=card[1], text=cap,
                parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except TelegramError as e:
            log.warning("kartu jav lama gagal diedit (%s) — kirim kartu baru", e)
    msg = await send_card_jav(q.message, qid, items, idx)
    if st is not None and msg is not None:
        st["card"] = (msg.chat.id, msg.message_id)


async def h_jav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    if not q:
        # tanpa judul → rilis terbaru
        msg = await update.message.reply_text("📀 ngambil rilis terbaru…")
        try:
            items = await asyncio.to_thread(scraper_javdb.browse_latest)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        qid = uuid.uuid4().hex
        STATE_JAV[qid] = {"items": items[:10], "ts": time.time(), "card": None}
        lines = ["📀 <b>JavDB — rilis terbaru</b>",
                 "<i>tulis /jav [kata/kode] buat cari spesifik</i>", ""]
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['code'])} {esc(it['title'][:44])}")
        num_rows = []
        row = []
        for i in range(1, len(items[:10]) + 1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"jvk|{qid}|{i}"))
            if len(row) == 5:
                num_rows.append(row)
                row = []
        if row:
            num_rows.append(row)
        await msg.edit_text('\n'.join(lines), parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(num_rows))
        try:
            card_m = await send_card_jav(msg, qid, items[:10], 1)
            if card_m:
                STATE_JAV[qid]["card"] = (card_m.chat.id, card_m.message_id)
        except TelegramError as e:
            log.warning("kirim kartu jav gagal: %s", e)
        return

    msg = await update.message.reply_text("🔎 nyari di JavDB…")
    try:
        items = await asyncio.to_thread(scraper_javdb.search, q)
    except Exception as e:
        log.exception("jav search gagal")
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not items:
        return await msg.edit_text("hasil kosong")
    qid = uuid.uuid4().hex
    STATE_JAV[qid] = {"items": items[:10], "ts": time.time(), "card": None}
    lines = [f"📀 <b>JavDB — {esc(q)}</b>", ""]
    for i, it in enumerate(items[:10], 1):
        lines.append(f"{i} · {esc(it['code'])} {esc(it['title'][:44])}")
    num_rows = []
    row = []
    for i in range(1, len(items[:10]) + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"jvk|{qid}|{i}"))
        if len(row) == 5:
            num_rows.append(row)
            row = []
    if row:
        num_rows.append(row)
    await msg.edit_text("\n".join(lines), parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(num_rows))
    try:
        card_m = await send_card_jav(msg, qid, items[:10], 1)
        if card_m:
            STATE_JAV[qid]["card"] = (card_m.chat.id, card_m.message_id)
    except TelegramError as e:
        log.warning("kirim kartu jav gagal: %s", e)


async def h_jav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split("|")
    kind = parts[0]
    if len(parts) < 3 or not parts[2].isdigit():
        return await q.answer("tombol basi", show_alert=True)
    qid = parts[1]
    st = _st_jav(qid)
    if not st:
        return await q.answer("hasil sudah basi — /jav lagi", show_alert=True)
    idx = int(parts[2])
    items = st["items"]
    if not (1 <= idx <= len(items)):
        return await q.answer("nomor di luar jangkauan", show_alert=True)
    it = items[idx - 1]

    # Navigasi kartu preview (klik nomor di list / panah ◀️ ▶️ di kartu)
    if kind in ("jvk", "jv"):
        await q.answer(f"▶️ {idx}/{len(items)} · {it['code']}")
        try:
            await update_card_jav(q, context, qid, items, idx)
        except TelegramError as e:
            log.warning("update kartu jav gagal: %s", e)
        return

    # Ambil detail + magnet (klik 🧲 Detail & Magnet)
    await q.answer("mengambil magnet...")
    status_msg = await q.message.reply_text(f"📀 <b>{esc(it['code'])}</b> — mengambil magnet & detail…",
                                            parse_mode=ParseMode.HTML)
    try:
        d = await asyncio.to_thread(scraper_javdb.detail, it["url"])
    except Exception as e:
        return await status_msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}",
                                          parse_mode=ParseMode.HTML)
    mg_txt = "\n".join(
        f"{i}. <code>magnet:?xt=urn:btih:{h}&amp;dn=jav</code> <i>({sz})</i>"
        for i, (h, sz) in enumerate(d.get("magnets", [])[:6], 1)) if d.get("magnets") else "<i>(tidak ada magnet publik)</i>"
    genres_str = ' · '.join(g for g in d.get('genres', []) if g not in ('Tags',))[:60]
    cap = (f"📀 <b>{esc(d['title'][:150])}</b>\n"
           f"{len(d.get('magnets', []))} magnet · {esc(genres_str)}\n\n"
           f"{mg_txt}\n\n"
           "<i>paste magnet ke torrent app buat download</i>")
    photo = await fetch_thumb(d.get("cover", it.get("cover", "")))
    try:
        if photo:
            await q.message.reply_photo(photo=photo, caption=cap, parse_mode=ParseMode.HTML)
        else:
            await q.message.reply_text(cap, parse_mode=ParseMode.HTML)
        await status_msg.delete()
    except TelegramError as e:
        await status_msg.edit_text(cap, parse_mode=ParseMode.HTML)



# ── /jelajah — dashboard: browse tanpa judul ──────────────────────────
# Tiap command baru sekarang jalan TANPA judul → tampilin terbaru/populer.
STATE_BROWSE: Dict[str, dict] = {}


async def h_jelajah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dashboard — pilih sumber, langsung keluar daftar tanpa ngetik judul."""
    kb = [
        [InlineKeyboardButton("🔥 PornTrex populer", callback_data="jel|ptx"),
         InlineKeyboardButton("🇨🇳 91porny 自拍", callback_data="jel|cn")],
        [InlineKeyboardButton("🇨🇳 China xHamster", callback_data="jel|ch_amatir")],
        [InlineKeyboardButton("📀 JAV terbaru", callback_data="jel|jav")],
        [InlineKeyboardButton("📚 Doujin terbaru", callback_data="jel|mdx"),
         InlineKeyboardButton("📺 Anime top", callback_data="jel|anime")],
        [InlineKeyboardButton("😈 Hentai terbaru", callback_data="jel|hentai"),
         InlineKeyboardButton("🎬 Film terbaru", callback_data="jel|film")],
        [InlineKeyboardButton("📺 Series terbaru", callback_data="jel|series"),
         InlineKeyboardButton("🎭 Dracin terbaru", callback_data="jel|dracin")],
        [InlineKeyboardButton("😂 Meme", callback_data="jel|meme"),
         InlineKeyboardButton("🖼️ 4chan", callback_data="jel|wsg"),
         InlineKeyboardButton("🎲 /r34", callback_data="jel|r34")],
        [InlineKeyboardButton("📚 Komik terbaru", callback_data="jel|komik"),
         InlineKeyboardButton("📖 Manhwa", callback_data="jel|manhwa")],
        [InlineKeyboardButton("🔄 Acak semua", callback_data="jel|acak")],
    ]
    txt = ("🧭 <b>JELAJAH — tanpa perlu tahu judul</b>\n\n"
           "Ketuk tombol, langsung keluar daftar terbaru/populer.\n"
           "Bisa juga ketik command tanpa judul, misal:\n"
           "<code>/jav</code> · <code>/ptx</code> · <code>/mdx</code> · "
           "<code>/anime</code> · <code>/film</code> · <code>/series</code>\n\n"
           "🎲 <b>/acak</b> — rekomendasi acak semua kategori")
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(
                txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        log.warning("jelajah menu: %s", e)
        await update.message.reply_text(txt, parse_mode="HTML",
                                        reply_markup=InlineKeyboardMarkup(kb))


async def h_jel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tombol di dashboard — dispatch ke sumber terkait."""
    q = update.callback_query
    await q.answer()
    kind = q.data.split("|")[1]
    msg = q.message

    async def say(t):
        try:
            await q.edit_message_text(t, parse_mode="HTML")
        except Exception:
            pass

    # ── China Amatir ──
    if kind == "ch_amatir":
        await say("🇨🇳 ngambil video China amatir…")
        context.args = []
        fake = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=q.from_user.id if q.from_user else 7998819216,
                                                  full_name="lu", username=""),
            effective_chat=msg.chat, effective_message=msg, message=msg,
            callback_query=None)
        return await h_amatir(fake, context)

    # ── 91porny 自拍 (amatir China asli, playable) ──
    if kind == "cn":
        await say("🇨🇳 ngambil video amatir China (91porny)...")
        try:
            items = await asyncio.to_thread(scraper_china.search, "", 10)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        items = [it for it in items if it.get("m3u8")]
        if not items:
            return await say("kosong")
        qid = uuid.uuid4().hex
        STATE_CN[qid] = {"items": items[:10], "ts": time.time(), "card": None}
        lines = ["🇨🇳 <b>91porny — 国产自拍 terbaru</b>", ""]
        for i, it in enumerate(items[:10], 1):
            dur_str = f" <i>({it['dur']})</i>" if it.get("dur") else ""
            lines.append(f"{i} · {esc(it['title'][:48])}{dur_str}")
        num_rows = []
        row = []
        for i in range(1, len(items[:10]) + 1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"cnk|{qid}|{i}"))
            if len(row) == 5:
                num_rows.append(row)
                row = []
        if row:
            num_rows.append(row)
        await msg.edit_text("\n".join(lines), parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(num_rows))
        try:
            card_m = await send_card_cn(msg, qid, items[:10], 1)
            if card_m:
                STATE_CN[qid]["card"] = (card_m.chat.id, card_m.message_id)
        except TelegramError as e:
            log.warning("kirim kartu cn jelajah gagal: %s", e)
        return

    # ── PornTrex populer ──
    if kind == "ptx":
        await say("🔥 ngambil video populer PornTrex…")
        try:
            items = await asyncio.to_thread(scraper_porntrex.browse_popular)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await say("kosong")
        qid = uuid.uuid4().hex
        STATE_PTX[qid] = {"items": items[:10], "ts": time.time()}
        lines, kb = ["🔥 <b>PornTrex — paling populer</b>", ""]
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} • {esc(it['title'][:58])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                            callback_data=f"ptxr|{qid}|{i}")])
        return await msg.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))

    # ── JAV terbaru ──
    if kind == "jav":
        await say("📀 ngambil rilis terbaru JavDB…")
        try:
            items = await asyncio.to_thread(scraper_javdb.browse_latest)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await say("kosong")
        qid = uuid.uuid4().hex
        STATE_JAV[qid] = {"items": items[:10], "ts": time.time(), "card": None}
        lines = ["📀 <b>JavDB — rilis terbaru</b>", ""]
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['code'])} {esc(it['title'][:42])}")
        num_rows = []
        row = []
        for i in range(1, len(items[:10]) + 1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"jvk|{qid}|{i}"))
            if len(row) == 5:
                num_rows.append(row)
                row = []
        if row:
            num_rows.append(row)
        await msg.edit_text("\n".join(lines), parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(num_rows))
        try:
            card_m = await send_card_jav(msg, qid, items[:10], 1)
            if card_m:
                STATE_JAV[qid]["card"] = (card_m.chat.id, card_m.message_id)
        except TelegramError as e:
            log.warning("kirim kartu jav jelajah gagal: %s", e)
        return

    # ── Doujin terbaru (MangaDex) ──
    if kind == "mdx":
        await say("📚 ngambil doujin terbaru MangaDex…")
        try:
            items = await asyncio.to_thread(scraper_mdx.browse_latest)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await say("kosong")
        qid = uuid.uuid4().hex
        STATE_MDX[qid] = {"items": items[:10], "ts": time.time()}
        lines, kb = ["📚 <b>MangaDex — doujin terbaru</b>", ""]
        for i, it in enumerate(items[:10], 1):
            tag = "🔥" if it["rating"] == "pornographic" else "·"
            lines.append(f"{i} {tag} {esc(it['title'][:56])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['title'][:56]}",
                                            callback_data=f"mdx|{qid}|{i}")])
        return await msg.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))

    # ── Anime top ──
    if kind == "anime":
        await say("📺 ngambil anime terpopuler…")
        try:
            items = await asyncio.to_thread(scraper_kitsu.top_anime)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await say("kosong")
        qid = uuid.uuid4().hex
        STATE_BROWSE[qid] = {"items": items, "ts": time.time()}
        lines, kb = ["📺 <b>Anime top (ongoing)</b>", ""]
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · ⭐{it['score']} {esc(it['title'][:50])}")
            kb.append([InlineKeyboardButton(f"⭐{it['score']} {it['title'][:50]}",
                                            callback_data=f"jelani|{qid}|{i}")])
        return await msg.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))

    # ── hentai / film / series / dracin / komik / manhwa terbaru ──
    if kind in ("hentai", "film", "series", "dracin", "komik", "manhwa"):
        cmdmap = {"hentai": "/hentai", "film": "/film", "series": "/series",
                  "dracin": "/dracin", "komik": "/komik", "manhwa": "/manhwa"}
        label = {"hentai": "😈 Hentai terbaru", "film": "🎬 Film terbaru",
                 "series": "📺 Series terbaru", "dracin": "🎭 Dracin terbaru",
                 "komik": "📚 Komik terbaru", "manhwa": "📖 Manhwa"}
        await say(f"{label[kind]} — ngambil…")
        # panggil handler command yang udah ada tanpa args
        context.args = []
        fake = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=q.from_user.id if q.from_user else 7998819216,
                                                  full_name="lu", username=""),
            effective_chat=msg.chat, effective_message=msg, message=msg,
            callback_query=None)
        try:
            if kind == "hentai":
                await h_hentai(fake, context)
            elif kind == "film":
                await h_film(fake, context)
            elif kind == "series":
                await h_series(fake, context)
            elif kind == "dracin":
                await h_dracin(fake, context)
            elif kind == "komik":
                await h_komik(fake, context)
            elif kind == "manhwa":
                await h_manhwa(fake, context)
        except Exception as e:
            log.exception("jel dispatch %s", kind)
            return await say(f"❌ {esc(str(e)[:100])}")
        return

    # ── random ──
    if kind in ("meme", "wsg", "r34"):
        context.args = []
        fake = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=7998819216, full_name="lu", username=""),
            effective_chat=msg.chat, effective_message=msg, message=msg,
            callback_query=None)
        try:
            if kind == "meme":
                await h_meme(fake, context)
            elif kind == "wsg":
                await h_wsg(fake, context)
            elif kind == "r34":
                await h_r34(fake, context)
        except Exception as e:
            return await say(f"❌ {esc(str(e)[:100])}")
        return

    # ── acak semua ──
    if kind == "acak":
        import random as _rnd
        await say("🎲 milih acak…")
        pick = _rnd.choice(["ptx", "jav", "mdx", "anime", "meme", "wsg"])
        q.data = f"jel|{pick}"
        return await h_jel_cb(update, context)


async def h_jelani_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tombol anime top → kirim detail + poster."""
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    st = STATE_BROWSE.get(parts[1])
    if not st:
        return await q.answer("basi — /jelajah lagi", show_alert=True)
    it = st["items"][int(parts[2]) - 1]
    txt = (f"📺 <b>{esc(it['title'])}</b>\n"
           f"⭐ {it['score']} · {it['eps']} eps · {it['year']} · {it['status']}\n\n"
           f"<i>{esc(it['synopsis'][:400])}</i>")
    try:
        await context.bot.send_photo(chat_id=q.message.chat.id,
                                     photo=it["poster"], caption=txt,
                                     parse_mode="HTML")
    except Exception:
        await context.bot.send_message(chat_id=q.message.chat.id, text=txt,
                                       parse_mode="HTML")


# ── /china — Bokep China / Madou Media (MD/MDX) ─────────────────────────
import scraper_china

STATE_CHINA: Dict[str, dict] = {}

async def h_china(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari / browse video dewasa China / Madou."""
    q = " ".join(context.args or []).strip()
    if not q:
        msg = await update.message.reply_text("🇨🇳 ngambil video China / Madou populer…")
        try:
            items = await asyncio.to_thread(scraper_china.browse_china_popular, 10)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        qid = uuid.uuid4().hex
        STATE_JAV[qid] = {"items": items[:10], "ts": time.time()}
        lines = ["🇨🇳 <b>Koleksi China / Madou Media</b>",
                 "<i>tulis /china [kata] buat cari spesifik</i>", ""]
        kb = []
        for i, it in enumerate(items[:10], 1):
            lines.append(f"{i} · {esc(it['code'])} {esc(it['title'][:42])}")
            kb.append([InlineKeyboardButton(f"{i} · {it['code']} {it['title'][:48]}",
                                            callback_data=f"jv|{qid}|{i}")])
        return await msg.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))

    msg = await update.message.reply_text("🔎 nyari video China…")
    try:
        items = await asyncio.to_thread(scraper_china.search_china, q, 10)
    except Exception as e:
        log.exception("china search gagal")
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}")
    if not items:
        return await msg.edit_text("hasil kosong")
    qid = uuid.uuid4().hex
    STATE_JAV[qid] = {"items": items[:10], "ts": time.time()}
    lines = [f"🇨🇳 <b>China / Madou — {esc(q)}</b>", ""]
    kb = []
    for i, it in enumerate(items[:10], 1):
        lines.append(f"{i} · {esc(it['code'])} {esc(it['title'][:44])}")
        kb.append([InlineKeyboardButton(f"{i} · {it['code']} {it['title'][:48]}",
                                        callback_data=f"jv|{qid}|{i}")])
    await msg.edit_text("\n".join(lines), parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(kb))



# ── /cn — Video Amatir China 91porny (国产自拍) — kartu preview + player ──
STATE_CN: Dict[str, dict] = {}


def _st_cn(qid):
    st = STATE_CN.get(qid)
    if st and time.time() - st["ts"] > 3600:
        STATE_CN.pop(qid, None)
        return None
    return st


def card_caption_cn(it: dict, idx: int, total: int) -> str:
    cap = f"🇨🇳 <b>{esc(it.get('title', ''))}</b>\n{idx}/{total}"
    if it.get("dur"):
        cap += f" · ⏱ {esc(it['dur'])}"
    cap += "\n\n▶️ Nonton · ⬇️ Unduh · 🌐 Situs"
    return cap


def card_kb_cn(qid: str, idx: int, total: int, url: str):
    nav: list[InlineKeyboardButton] = []
    if idx > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"cnk|{qid}|{idx - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {idx}/{total}", callback_data=f"noop|{qid}"))
    if idx < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"cnk|{qid}|{idx + 1}"))
    return InlineKeyboardMarkup([
        nav,
        [
            InlineKeyboardButton("▶️ Nonton", callback_data=f"cndl|{qid}|{idx}"),
            InlineKeyboardButton("⬇️ Unduh", callback_data=f"cndl|{qid}|{idx}"),
            InlineKeyboardButton("🌐 Situs", url=url or SITE_REF),
        ],
    ])


async def send_card_cn(reply_target, qid: str, items: list, idx: int):
    it = items[idx - 1]
    cap = card_caption_cn(it, idx, len(items))
    kb = card_kb_cn(qid, idx, len(items), it.get("url", SITE_REF))
    photo = await fetch_thumb(it.get("poster", ""))
    if photo:
        return await reply_target.reply_photo(
            photo=photo, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
    return await reply_target.reply_text(
        cap, parse_mode=ParseMode.HTML, reply_markup=kb)


async def update_card_cn(q, context, qid: str, items: list, idx: int):
    if not hasattr(q, "edit_message_media"):
        q = q.callback_query
    it = items[idx - 1]
    cap = card_caption_cn(it, idx, len(items))
    kb = card_kb_cn(qid, idx, len(items), it.get("url", SITE_REF))
    photo = await fetch_thumb(it.get("poster", ""))
    st = _st_cn(qid)
    card = (st or {}).get("card")
    if card:
        try:
            if photo:
                await context.bot.edit_message_media(
                    chat_id=card[0], message_id=card[1],
                    media=InputMediaPhoto(photo, caption=cap, parse_mode=ParseMode.HTML),
                    reply_markup=kb)
                return
            await context.bot.edit_message_text(
                chat_id=card[0], message_id=card[1], text=cap,
                parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except TelegramError as e:
            log.warning("kartu cn lama gagal diedit (%s) — kirim kartu baru", e)
    msg = await send_card_cn(q.message, qid, items, idx)
    if st is not None and msg is not None:
        st["card"] = (msg.chat.id, msg.message_id)


async def h_cn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari / browse video amatir China (91porny) — daftar + kartu preview."""
    q = " ".join(context.args or []).strip()
    if not q:
        msg = await update.message.reply_text("🇨🇳 ngambil video amatir China terbaru...")
        try:
            items = await asyncio.to_thread(scraper_china.search, "", 10)
        except Exception as e:
            return await msg.edit_text(f"❌ {esc(str(e)[:100])}")
        if not items:
            return await msg.edit_text("kosong")
        items = [it for it in items if it.get("m3u8")]
        qid = uuid.uuid4().hex
        STATE_CN[qid] = {"items": items[:10], "ts": time.time(), "card": None}
        lines = ["🇨🇳 <b>91porny — 国产自拍 terbaru</b>",
                 "<i>tulis /cn [kata] (hotel, selingkuh, pijat, mahasiswi...)</i>", ""]
        for i, it in enumerate(items[:10], 1):
            dur_str = f" <i>({it['dur']})</i>" if it.get("dur") else ""
            lines.append(f"{i} · {esc(it['title'][:48])}{dur_str}")
        num_rows = []
        row = []
        for i in range(1, len(items[:10]) + 1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"cnk|{qid}|{i}"))
            if len(row) == 5:
                num_rows.append(row)
                row = []
        if row:
            num_rows.append(row)
        await msg.edit_text("\n".join(lines), parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(num_rows))
        try:
            card_m = await send_card_cn(msg, qid, items[:10], 1)
            if card_m:
                STATE_CN[qid]["card"] = (card_m.chat.id, card_m.message_id)
        except TelegramError as e:
            log.warning("kirim kartu cn gagal: %s", e)
        return

    zh_keyword = scraper_china.to_chinese_keyword(q)
    sub = f" ({esc(zh_keyword)})" if zh_keyword != q else ""
    msg = await update.message.reply_text(f"🔎 nyari amatir China: <b>{esc(q)}</b>{sub}...",
                                          parse_mode="HTML")
    try:
        items = await asyncio.to_thread(scraper_china.search, q, 10)
    except Exception as e:
        log.exception("cn search gagal")
        return await msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}")
    items = [it for it in items if it.get("m3u8")]
    if not items:
        return await msg.edit_text("hasil kosong")
    qid = uuid.uuid4().hex
    STATE_CN[qid] = {"items": items[:10], "ts": time.time(), "card": None}
    lines = [f"🇨🇳 <b>91porny — {esc(q)}{sub}</b>", ""]
    for i, it in enumerate(items[:10], 1):
        dur_str = f" <i>({it['dur']})</i>" if it.get("dur") else ""
        lines.append(f"{i} · {esc(it['title'][:48])}{dur_str}")
    num_rows = []
    row = []
    for i in range(1, len(items[:10]) + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"cnk|{qid}|{i}"))
        if len(row) == 5:
            num_rows.append(row)
            row = []
    if row:
        num_rows.append(row)
    await msg.edit_text("\n".join(lines), parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(num_rows))
    try:
        card_m = await send_card_cn(msg, qid, items[:10], 1)
        if card_m:
            STATE_CN[qid]["card"] = (card_m.chat.id, card_m.message_id)
    except TelegramError as e:
        log.warning("kirim kartu cn gagal: %s", e)


async def h_cn_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split("|")
    kind = parts[0]
    if len(parts) < 3 or not parts[2].isdigit():
        return await q.answer("tombol basi", show_alert=True)
    qid = parts[1]
    st = _st_cn(qid)
    if not st:
        return await q.answer("hasil sudah basi — /cn lagi", show_alert=True)
    idx = int(parts[2])
    items = st["items"]
    if not (1 <= idx <= len(items)):
        return await q.answer("nomor di luar jangkauan", show_alert=True)
    it = items[idx - 1]

    # Navigasi kartu preview (klik nomor di list / panah ◀️ ▶️ di kartu)
    if kind in ("cnk", "cn"):
        await q.answer(f"▶️ {idx}/{len(items)} · {it['title'][:55]}")
        try:
            await update_card_cn(q, context, qid, items, idx)
        except TelegramError as e:
            log.warning("update kartu cn gagal: %s", e)
        return

    # Download / play video (klik ▶️ Nonton / ⬇️ Unduh)
    await q.answer()
    status_msg = await q.message.reply_text(
        f"🎬 <b>{esc(it['title'][:70])}</b>\n⬇️ mengunduh video China...",
        parse_mode="HTML")
    out = os.path.join(str(DL_DIR), f"cn-{uuid.uuid4().hex[:8]}.mp4")
    try:
        ok = await asyncio.wait_for(
            asyncio.to_thread(scraper_china.download, it["m3u8"], out),
            MEDIA_TIMEOUT)
        if not ok or not os.path.exists(out):
            return await status_msg.edit_text("❌ gagal download video ini, coba yang lain",
                                              parse_mode="HTML")
        out2 = _faststart(out)
        size = os.path.getsize(out2)
        if size > TG_UPLOAD_LIMIT:
            out2 = _shrink(out2, int(TG_UPLOAD_LIMIT * 0.94))
            size = os.path.getsize(out2)
        cap = f"🇨🇳 <b>{esc(it['title'][:80])}</b>\n{size / 1048576:.1f} MB"
        if size <= TG_UPLOAD_LIMIT:
            await _send_retry(lambda: context.bot.send_video(
                chat_id=q.message.chat.id, video=open(out2, "rb"),
                caption=cap, parse_mode="HTML", supports_streaming=True,
                read_timeout=MEDIA_TIMEOUT, write_timeout=MEDIA_TIMEOUT),
                attempts=3)
        else:
            return await status_msg.edit_text("⚠️ kegedean buat Telegram, coba yang lain")
        await status_msg.edit_text("✅ terkirim (file sisa dihapus)")
    except Exception as e:
        log.exception("cn gagal")
        await status_msg.edit_text(f"❌ gagal: {esc(str(e)[:120])}", parse_mode="HTML")
    finally:
        try:
            import shutil as _sh
            _sh.rmtree(out + "_parts", ignore_errors=True)
            if os.path.exists(out):
                os.unlink(out)
        except OSError:
            pass


async def h_hentai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip()
    await do_search(update, f"hentai {q}".strip())


async def h_manhwa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args or []).strip() or "manhwa"
    msg = await update.message.reply_text(f"🌸 mencari manhwa <b>{esc(q)}</b>…",
                                          parse_mode=ParseMode.HTML)
    try:
        gp = await scraper_hentai.search(q, 1)
    except Exception as e:
        log.exception("manhwa search gagal")
        await msg.edit_text(f"❌ gagal nyari: {esc(str(e))[:200]}", parse_mode=ParseMode.HTML)
        return
    qid = new_state_m(gp)
    text, kb = render_mlist(gp, qid)
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list manhwa gagal: %s", e)


async def h_komik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/komik [judul] — KomikDoujin: doujin Indonesia, semua chapter."""
    q = " ".join(context.args or []).strip()
    label = f"<b>{esc(q)}</b>" if q else "update terbaru"
    msg = await update.message.reply_text(
        f"📖 mencari komik doujin {label}…", parse_mode=ParseMode.HTML)
    try:
        gp = await scraper_kdj.search(q, 1)
    except Exception as e:
        log.exception("komik search gagal")
        await msg.edit_text(f"❌ gagal nyari: {esc(str(e))[:200]}",
                            parse_mode=ParseMode.HTML)
        return
    qid = new_state_m(gp)
    STATES_M[qid]["mod"] = scraper_kdj
    if not gp.items:
        await msg.edit_text("❌ nggak ketemu — coba kata lain",
                            parse_mode=ParseMode.HTML)
        return
    text, kb = render_mlist(gp, qid)
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list komik gagal: %s", e)


async def h_manhwa_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Doujin berbahasa Indonesia (source: dojing.net)."""
    q = " ".join(context.args or []).strip()
    label = f"<b>{esc(q)}</b>" if q else "update terbaru"
    msg = await update.message.reply_text(
        f"🇮🇩 mencari doujin Indonesia {label}…", parse_mode=ParseMode.HTML)
    try:
        gp = await scraper_indo.search(q, 1)
    except Exception as e:
        log.exception("manhwa indonesia search gagal")
        await msg.edit_text(f"❌ gagal nyari: {esc(str(e))[:200]}", parse_mode=ParseMode.HTML)
        return
    qid = new_state_m(gp)
    STATES_M[qid]["mod"] = scraper_indo
    if not gp.items:
        await msg.edit_text("❌ nggak ketemu — coba kata lain, atau /manhwaid tanpa argumen",
                            parse_mode=ParseMode.HTML)
        return
    text, kb = render_mlist(gp, qid)
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list manhwa-id gagal: %s", e)


async def m_goto_page(update: Update, qid: str, page: int):
    q = update.callback_query
    st = _state_m(qid)
    if not st:
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    gp0 = st["gp"]
    if page < 1 or page > gp0.max_pages or page == gp0.page:
        await q.answer()
        return
    await q.answer("⏳ memuat…")
    try:
        gp = await _mod(st).search(gp0.query, page)
    except Exception as e:
        log.exception("paging manhwa gagal")
        try:
            await q.message.reply_text(f"❌ gagal pindah halaman: {esc(str(e))[:200]}",
                                       parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        return
    st["gp"] = gp
    text, kb = render_mlist(gp, qid)
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list manhwa gagal: %s", e)


async def _m_detail(st: dict, it) -> scraper_hentai.GalleryDetail:
    d = st["details"].get(it.url)
    if not d:
        d = await _mod(st).gallery(it.url)
        st["details"][it.url] = d
    return d


async def m_detail(update: Update, qid: str, idx: int):
    q = update.callback_query
    st = _state_m(qid)
    if not st or not (1 <= idx <= len(st["gp"].items)):
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    it = st["gp"].items[idx - 1]
    await q.answer("⏳ memuat detail…")
    try:
        d = await _m_detail(st, it)
    except Exception as e:
        log.exception("detail manhwa gagal")
        await q.answer(f"❌ gagal: {esc(str(e))[:120]}", show_alert=True)
        return
    _uK = getattr(update, "effective_user", None)
    _bkPos = _bk_get(_uK.id, f"m|{getattr(it, 'url', '')}") if _uK else None
    _rowsM = []
    if _bkPos and _bkPos > 1:
        _rowsM.append([InlineKeyboardButton(
            f"▶️ lanjut hal {_bkPos}", callback_data=f"mr|{qid}|{idx}|{_bkPos}")])
    kb = InlineKeyboardMarkup(_rowsM + [
        [InlineKeyboardButton("📖 Baca (slide)", callback_data=f"mr|{qid}|{idx}|1"),
         InlineKeyboardButton(f"🖼 10 halaman", callback_data=f"m10|{qid}|{idx}"),
         InlineKeyboardButton("⬇️ ZIP", callback_data=f"mz|{qid}|{idx}")],
        [InlineKeyboardButton("🌐 Buka di situs", url=d.url),
         InlineKeyboardButton("🔙 Kembali", callback_data=f"mb|{qid}|{idx}")],
    ])
    cap = (f"<b>{esc(d.title[:150])}</b>\n"
           f"{d.pages} halaman · {esc(it.cat)}\n\n"
           "📖 <b>Baca (slide)</b> — 1 halaman per langkah, geser ◀️▶️, tanpa download\n"
           "🖼 <b>10 halaman</b> — album 10 foto pertama (bisa di-swipe di viewer)\n"
           "⬇️ <b>ZIP</b> — semua halaman dalam 1 file (maks ~46MB)")
    try:
        await q.message.reply_photo(photo=d.cover, caption=cap,
                                    parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        log.info("cover kirim gagal (%s), fallback teks", e)
        await q.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)


def _finish_kb_btn(qid: str, idx: int):
    return InlineKeyboardButton("✅ selesai", callback_data=f"mf|{qid}|{idx}")


async def _recover_reader(q, st, kind: str, path: str, cap: str, kb):
    """AUTO-RECOVERY anti-basi (kebijakan user): pesan reader hilang/ke-edit
    gagal → LANGSUNG bikin pesan baca baru + tracker ke-refresh. Pengguna ga
    pernah mentok alert 'basi'. kind: 'photo' (mode halaman) / 'doc' (strip)."""
    try:
        if kind == "doc":
            sent = await q.message.reply_document(
                document=path, caption=cap, parse_mode=ParseMode.HTML,
                reply_markup=kb)
        else:
            sent = await q.message.reply_photo(
                photo=path, caption=cap, parse_mode=ParseMode.HTML,
                reply_markup=kb)
        st["reader"] = (sent.chat.id, sent.message_id)
        await q.answer("📖 lanjut di pesan baca baru")
    except TelegramError as e:
        log.warning("recovery reader gagal: %s", e)
        try:
            await q.answer("❌ gagal bikin pesan baca — coba buka lagi dari 📖",
                           show_alert=True)
        except TelegramError:
            pass


def reader_kb(qid: str, idx: int, page: int, total: int):
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"mr|{qid}|{idx}|{page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {page}/{total}", callback_data=f"mo|{qid}"))
    if page < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"mr|{qid}|{idx}|{page + 1}"))
    rows = [nav]
    # shortcut lompat halaman (khusus chapter panjang)
    if total > 10:
        rows.append([
            InlineKeyboardButton("⏮", callback_data=f"mr|{qid}|{idx}|1"),
            InlineKeyboardButton("⏪10",
                                 callback_data=f"mr|{qid}|{idx}|{max(1, page - 10)}"),
            InlineKeyboardButton("10⏩",
                                 callback_data=f"mr|{qid}|{idx}|{min(total, page + 10)}"),
            InlineKeyboardButton("⏭", callback_data=f"mr|{qid}|{idx}|{total}"),
        ])
    rows.append(
        [InlineKeyboardButton("📜 scroll", callback_data=f"ms|{qid}|{idx}|1"),
         _finish_kb_btn(qid, idx),
         InlineKeyboardButton("⬇️ ZIP", callback_data=f"mz|{qid}|{idx}"),
         InlineKeyboardButton("🔙 ke detail", callback_data=f"mv|{qid}|{idx}")])
    return InlineKeyboardMarkup(rows)


# ─── MODE SCROLL (kayak scroll web: strip vertikal panjang, viewer zoom) ──
# Kenapa gambar besar di kirim sebagai DOKUMEN (bukan foto): foto di-resize
# Telegram maks ~1280px → kecil & blur buat baca; dokumen = resolusi penuh,
# viewer Telegram bisa pinch-zoom + drag vertikal = feel infinite scroll.
SCROLL_PER = 6       # halaman per strip (≈8000-9000px tinggi — pas di-scroll)
STRIP_W = 1000       # lebar gabungan px


def _pbar(page: int, total: int, n: int = 10) -> str:
    if total <= 0:
        return "▰" * n
    filled = max(0, min(n, round(n * page / total)))
    return "▰" * filled + "▱" * (n - filled)


def _merge_vertical(paths: list[str], out: str, width: int = STRIP_W) -> str:
    """Gabung halaman jadi 1 strip vertikal JPEG (resolusi cukup buat zoom)."""
    from PIL import Image
    imgs = []
    for p in paths:
        try:
            im = Image.open(p)
            im.load()
            imgs.append(im.convert("RGB"))
        except Exception as e:
            log.warning("halaman rusak dilewati di strip: %s", e)
    if not imgs:
        raise RuntimeError("gagal baca halaman buat strip")
    scaled = []
    for im in imgs:
        if im.width != width:
            h = round(im.height * width / im.width)
            im = im.resize((width, h), Image.LANCZOS)
        scaled.append(im)
    canvas = Image.new("RGB", (width, sum(i.height for i in scaled)),
                       (255, 255, 255))
    y = 0
    for im in scaled:
        canvas.paste(im, (0, y))
        y += im.height
    canvas.save(out, "JPEG", quality=85, optimize=True)
    if os.path.getsize(out) > 40 * 1024 * 1024:   # jaga-jaga
        canvas.save(out, "JPEG", quality=68, optimize=True)
    return out


async def _get_strip(st: dict, d, idx: int, strip: int) -> str:
    """Path strip ke-N (cache hit = instan). LRU 4 strip, file lama dibersih."""
    cache: dict = st.setdefault("strip_cache", {})
    if strip in cache and os.path.exists(cache[strip]):
        return cache[strip]
    work = st.get("_mstrip_dir")
    if not work:
        work = os.path.join(DL_DIR, f"ms_{uuid.uuid4().hex[:8]}")
        st["_mstrip_dir"] = work
    start = (strip - 1) * SCROLL_PER
    limit = min(SCROLL_PER, d.pages - start)
    if limit <= 0:
        raise RuntimeError("strip di luar jangkauan")
    files, _ = await _mod(st).download_pages(d, work, start=start, limit=limit)
    if not files:
        raise RuntimeError("halaman strip gagal diunduh")
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, f"strip_{strip}.jpg")
    try:
        _merge_vertical(files, out)
    finally:
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
    cache[strip] = out
    while len(cache) > 4:
        k_old = next(iter(cache))
        if k_old == strip:
            break
        v_old = cache.pop(k_old)
        try:
            os.remove(v_old)
        except OSError:
            pass
    return out


def _prefetch_strip(st: dict, d, idx: int, strip: int):
    """Task background: strip berikutnya sudah siap pas user pencet ⏭."""
    async def _run():
        try:
            await _get_strip(st, d, idx, strip)
        except Exception as e:
            log.info("prefetch strip %s dilewati: %s", strip, e)
    return asyncio.create_task(_run())


def scroll_kb(qid: str, idx: int, strip: int, n_strips: int, page0: int):
    nav: list[InlineKeyboardButton] = []
    if strip > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"ms|{qid}|{idx}|{strip - 1}"))
    nav.append(InlineKeyboardButton(f"📜 {strip}/{n_strips}", callback_data=f"mo|{qid}"))
    if strip < n_strips:
        nav.append(InlineKeyboardButton("⏭️", callback_data=f"ms|{qid}|{idx}|{strip + 1}"))
    rows = [nav]
    # shortcut lompat strip (mode scroll)
    if n_strips > 2:
        rows.append([
            InlineKeyboardButton("⏮", callback_data=f"ms|{qid}|{idx}|1"),
            InlineKeyboardButton("⏪3",
                                 callback_data=f"ms|{qid}|{idx}|{max(1, strip - 3)}"),
            InlineKeyboardButton("3⏩",
                                 callback_data=f"ms|{qid}|{idx}|{min(n_strips, strip + 3)}"),
            InlineKeyboardButton("⏭", callback_data=f"ms|{qid}|{idx}|{n_strips}"),
        ])
    rows.append(
        [InlineKeyboardButton("🧩 per halaman",
                              callback_data=f"mr|{qid}|{idx}|{page0 + 1}"),
         _finish_kb_btn(qid, idx),
         InlineKeyboardButton("⬇️ ZIP", callback_data=f"mz|{qid}|{idx}"),
         InlineKeyboardButton("🔙 ke detail", callback_data=f"mv|{qid}|{idx}")])
    return InlineKeyboardMarkup(rows)


async def m_scroll(update: Update, context: ContextTypes.DEFAULT_TYPE,
                   qid: str, idx: int, strip: int):
    """Mode scroll: edit-in-place pesan reader jadi strip vertikal (dokumen
    full-res) — viewer Telegram: drag + pinch-zoom kayak scroll web."""
    q = update.callback_query
    st = _state_m(qid)
    if not st or not (1 <= idx <= len(st["gp"].items)):
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    it = st["gp"].items[idx - 1]
    _set_last(q.message.chat.id, "m", qid=qid, idx=idx)   # shortcut ketik-angka
    try:
        d = await _m_detail(st, it)
    except Exception as e:
        log.exception("detail manhwa gagal")
        await q.answer(f"❌ gagal: {esc(str(e))[:120]}", show_alert=True)
        return
    n_strips = max(1, -(-d.pages // SCROLL_PER))   # ceil
    if strip < 1 or strip > n_strips:
        await q.answer("udah di ujung ✌️")
        return
    try:
        merged = await _get_strip(st, d, idx, strip)
        start0 = (strip - 1) * SCROLL_PER
        p0, p1 = start0 + 1, min(d.pages, start0 + SCROLL_PER)
        cap = (f"<b>{esc(d.title[:120])}</b>\n"
               f"📜 halaman {p0}–{p1}/{d.pages} · {_pbar(p1, d.pages)}\n"
               f"👇 scroll ke bawah buat lanjut (zoom bebas)")
        kb = scroll_kb(qid, idx, strip, n_strips, start0)
        reader = (st or {}).get("reader")
        with open(merged, "rb") as fh:
            # NB: InputMediaDocument PTB ini TANPA reply_markup di konstruktor
            # → reply_markup dikirim terpisah di edit_message_media / send_document
            media = InputMediaDocument(fh, caption=cap,
                                       parse_mode=ParseMode.HTML)
            if reader:
                try:
                    await context.bot.edit_message_media(
                        chat_id=reader[0], message_id=reader[1], media=media,
                        reply_markup=kb)
                except BadRequest as e:
                    if "not modified" in str(e).lower():
                        await q.answer()      # strip sama (double-tap) — bukan error
                        return
                    log.info("strip basi (%s) → auto-recovery", e)
                    await _recover_reader(q, st, "doc", merged, cap, kb)
                    return
                except TelegramError as e:
                    log.warning("edit strip gagal (%s) → auto-recovery", e)
                    await _recover_reader(q, st, "doc", merged, cap, kb)
                    return
            else:
                sent = await q.message.reply_document(
                    document=merged, caption=cap, parse_mode=ParseMode.HTML,
                    reply_markup=kb)
                st["reader"] = (sent.chat.id, sent.message_id)
        # siapin strip berikutnya biar ⏭️ instan
        if strip < n_strips:
            _prefetch_strip(st, d, idx, strip + 1)
        await q.answer()
    except (TelegramError, RuntimeError, OSError) as e:
        log.warning("mode scroll gagal: %s", e)
        try:
            await q.answer(f"❌ gagal: {esc(str(e))[:100]}", show_alert=True)
        except TelegramError:
            pass


def _fastjpg(path: str, max_w: int = 1100, quality: int = 78) -> str:
    """Kompres halaman buat mode baca: resize ≤ max_w + JPEG q78 → file kecil
    = upload Telegram jauh lebih cepat → ◀️/▶️ next-next responsif.
    Fail-safe: apapun errornya, balikin path asli (tetep dikirim)."""
    try:
        from PIL import Image
        im = Image.open(path)
        im.load()
        im = im.convert("RGB")
        if im.width > max_w:
            h = round(im.height * max_w / im.width)
            im = im.resize((max_w, h), Image.LANCZOS)
        small = path + ".sm.jpg"
        im.save(small, "JPEG", quality=quality, optimize=True)
        if os.path.getsize(small) < os.path.getsize(path):
            return small
    except Exception as e:
        log.info("kompres dilewati (%s): %s", os.path.basename(path), e)
    return path


async def m_finish(update: Update, context: ContextTypes.DEFAULT_TYPE,
                   qid: str, idx: int, st: dict | None = None,
                   msg: str = "✅ selesai baca — mantap!"):
    """✅ selesai baca/tonton: hapus pesan (reader/kartu), tracker dilepas,
    cache strip dibersih — sesi ditutup rapi tanpa pesan nyangkut.
    Dipakai 2 jalur: manhwa (st=state manhwa) & dracin (st=state dracin)."""
    q = update.callback_query
    if st is None:
        st = _state_m(qid)
    _pop_last(q.message.chat.id)          # sesi tutup → shortcut mati
    try:
        await q.message.delete()
    except TelegramError as e:
        log.info("hapus pesan saat selesai gagal: %s", e)
    if st:
        st.pop("reader", None)
        wd = st.pop("_mstrip_dir", None)
        if wd:
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        st.get("strip_cache", {}).clear()
    try:
        await q.answer(msg)
    except TelegramError:
        pass


async def m_read(update: Update, context: ContextTypes.DEFAULT_TYPE,
                 qid: str, idx: int, page: int):
    """Mode baca slide: tampilkan halaman `page` (1-based) sebagai foto yang
    di-edit in-place tiap kali ◀️/▶️ ditekan — tanpa download permanen."""
    q = update.callback_query
    st = _state_m(qid)
    if not st or not (1 <= idx <= len(st["gp"].items)):
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    it = st["gp"].items[idx - 1]
    _set_last(q.message.chat.id, "m", qid=qid, idx=idx)   # shortcut ketik-angka
    try:
        d = await _m_detail(st, it)
    except Exception as e:
        log.exception("detail manhwa gagal")
        await q.answer(f"❌ gagal: {esc(str(e))[:120]}", show_alert=True)
        return
    if page < 1 or page > d.pages:
        await q.answer("udah di ujung ✌️")
        return
    # NB: answer CUMA sekali (di outcome) — Telegram nolak answer kedua
    files: list[str] = []
    send_path = None
    try:
        files, _ = await _mod(st).download_pages(
            d, str(DL_DIR), start=page - 1, limit=1)
        if not files:
            raise RuntimeError("halaman gagal diunduh")
        send_path = _fastjpg(files[0])
        cap = (f"<b>{esc(d.title[:120])}</b>\n"
               f"📖 halaman {page}/{d.pages}")
        kb = reader_kb(qid, idx, page, d.pages)
        reader = (st or {}).get("reader")
        sent = None
        if reader:
            # NB: InputMediaPhoto(path) di PTB ini jadi 'file://...' (local_mode)
            # yang ditolak Telegram asli → WAJIB lewat file handle biar jadi InputFile
            try:
                with open(send_path, "rb") as fh:
                    await context.bot.edit_message_media(
                        chat_id=reader[0], message_id=reader[1],
                        media=InputMediaPhoto(fh, caption=cap, parse_mode=ParseMode.HTML),
                        reply_markup=kb)
            except BadRequest as e:
                if "not modified" in str(e).lower():
                    await q.answer()          # halaman sama (double-tap) — bukan error
                    return
                log.info("reader basi (%s) → auto-recovery", e)
                await _recover_reader(q, st, "photo", send_path, cap, kb)
                return
            except TelegramError as e:
                log.warning("reader gagal diedit (%s) → auto-recovery", e)
                await _recover_reader(q, st, "photo", send_path, cap, kb)
                return
        else:
            sent = await q.message.reply_photo(
                photo=send_path, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            st["reader"] = (sent.chat.id, sent.message_id)
        await q.answer()
    except (TelegramError, RuntimeError, OSError) as e:
        log.warning("reader gagal: %s", e)
        try:
            await q.answer(f"❌ gagal: {esc(str(e))[:100]}", show_alert=True)
        except TelegramError:
            pass
    finally:
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
        # file .sm.jpg turunan _fastjpg
        if send_path and send_path.endswith(".sm.jpg"):
            try:
                os.remove(send_path)
            except OSError:
                pass


async def m_send10(update: Update, context: ContextTypes.DEFAULT_TYPE, qid: str, idx: int):
    q = update.callback_query
    st = _state_m(qid)
    if not st or not (1 <= idx <= len(st["gp"].items)):
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    chat = q.message.chat.id
    if chat in BUSY:
        await q.answer("⏳ masih memproses permintaan sebelumnya…")
        return
    await q.answer()
    it = st["gp"].items[idx - 1]
    BUSY.add(chat)
    files: list[str] = []
    try:
        d = await _m_detail(st, it)
        status = await q.message.reply_text("⏳ mengunduh 10 halaman…")
        files, _ = await _mod(st).download_pages(d, str(DL_DIR), start=0, limit=10)
        if not files:
            raise RuntimeError("gagal unduh halaman")
        # file handle (bukan path) — path jadi 'file://...' (local_mode) & ditolak Telegram
        # + kompres dulu tiap halaman → upload grup jauh lebih cepat
        send_paths = [_fastjpg(f) for f in files]
        from contextlib import ExitStack
        with ExitStack() as stack:
            media = []
            for i, sp in enumerate(send_paths):
                fh = stack.enter_context(open(sp, "rb"))
                media.append(InputMediaPhoto(
                    fh, caption=esc(d.title[:120]) if i == 0 else None))
            await context.bot.send_media_group(chat_id=chat, media=media)
        await status.delete()
        log.info("10 halaman terkirim: %s", d.title[:50])
    except Exception as e:
        log.exception("kirim 10 halaman gagal")
        try:
            await q.message.reply_text(f"❌ gagal: {esc(str(e))[:300]}", parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
    finally:
        BUSY.discard(chat)
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
            try:
                os.remove(f + ".sm.jpg")   # turunan _fastjpg
            except OSError:
                pass


async def m_zip(update: Update, context: ContextTypes.DEFAULT_TYPE, qid: str, idx: int):
    q = update.callback_query
    st = _state_m(qid)
    if not st or not (1 <= idx <= len(st["gp"].items)):
        await q.answer("hasil sudah basi — /manhwa lagi", show_alert=True)
        return
    chat = q.message.chat.id
    if chat in BUSY:
        await q.answer("⏳ masih memproses permintaan sebelumnya…")
        return
    await q.answer()
    it = st["gp"].items[idx - 1]
    BUSY.add(chat)
    files: list[str] = []
    zpath: str | None = None
    status = None
    try:
        d = await _m_detail(st, it)
        status = await q.message.reply_text(f"⏳ mengunduh {d.pages} halaman…")
        files, trunc = await _mod(st).download_pages(d, str(DL_DIR), max_bytes=MAX_ZIP_BYTES)
        if not files:
            raise RuntimeError("nggak ada halaman yang berhasil diunduh")
        safe = re.sub(r"[^\w .&+-]", "_", d.title).strip(" ._")[:60] or "manhwa"
        zpath = _mod(st).zip_files(files, str(DL_DIR / f"{safe}.zip"))
        size = os.path.getsize(zpath)
        note = "\n⚠️ dipotong di %d halaman (batas 46MB)" % len(files) if trunc else ""
        cap = f"<b>{esc(d.title[:150])}</b>\n{len(files)}/{d.pages} halaman · {size / 1048576:.1f} MB{note}"
        await status.edit_text("⬆️ upload ke Telegram…")
        await _send_retry(lambda: context.bot.send_document(
            chat_id=chat, document=zpath,
            filename=f"{safe}.zip", caption=cap,
            parse_mode=ParseMode.HTML,
            write_timeout=600, read_timeout=180))
        await status.delete()
        log.info("zip manhwa terkirim: %s (%.1f MB)", d.title[:50], size / 1048576)
        _bump("komik-zip")
    except Exception as e:
        log.exception("zip manhwa gagal")
        try:
            await (status or q.message).edit_text(f"❌ gagal: {esc(str(e))[:300]}",
                                                  parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
    finally:
        BUSY.discard(chat)
        for f in files + ([zpath] if zpath else []):
            try:
                if f and os.path.isfile(f):
                    os.remove(f)
            except OSError:
                pass


async def h_cb_m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data or ""
    parts = data.split("|")
    kind = parts[0]
    qid = parts[1] if len(parts) > 1 else ""
    try:
        num = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        num = 0
    if kind == "mo":
        await update.callback_query.answer()
    elif kind == "mv":
        await m_detail(update, qid, num)
    elif kind == "mp":
        await m_goto_page(update, qid, num)
    elif kind == "m10":
        await m_send10(update, context, qid, num)
    elif kind == "mr":
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
        await m_read(update, context, qid, num, page)
    elif kind == "mf":
        await m_finish(update, context, qid, num)
    elif kind == "ms":
        strip = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
        await m_scroll(update, context, qid, num, strip)
    elif kind == "mz":
        await m_zip(update, context, qid, num)
    elif kind == "mb":
        try:
            await update.callback_query.message.delete()
        except TelegramError:
            pass
        await update.callback_query.answer()


# ─── DRACIN (dracinema.com — drama China 18+ sub Indo) ───────────────────
# Rantai kerja (fakta lapangan): index lokal FTS5 (index_dracin.py) buat
# search — search server-side mereka MATI. Download: POST /api/playback
# (+X-API-Key) → videoUrls → CDN playsverse DIRECT (tanpa proxy).
# Ep 1-5 kind=ok; ep 6+ login_required → jujur aja ke user (tanpa akun farm).
STATES_D: "OrderedDict[str, dict]" = OrderedDict()
DR_PER_PAGE = 10
# label sumber biar konsisten di list/detail/status
DR_LABEL = {"drc": "dracinema", "best": "dracin.best",
            "film": "🎬 LK21 Film", "ai2": "🤖 Swaplse AI",
            # catatan: /film sekarang = layarkaca21.dev (27rb film mainstream,
            # semua sub Indo — mirror gashouse isinya bokep, dibuang)
            "candy": "Candy AI Shorts", "nh": "NontonHentai"}
DR_ORDER = ["drc", "best", "candy", "nh", "film", "ai2"]   # urutan siklus tombol 🔁 ganti sumber


def _dr_next(src: str) -> str:
    i = DR_ORDER.index(src) if src in DR_ORDER else 0
    return DR_ORDER[(i + 1) % len(DR_ORDER)]


def _dr_mod(src: str):
    """Sumber: 'drc' (dracinema, butuh proxy), 'best' (dracin.best, direct),
    'candy' (Candy AI Shorts — seri porno AI, EP awal gratis, CDN geo-block)."""
    return {"drc": scraper_dracin, "best": scraper_drbest,
            "candy": scraper_candy, "nh": scraper_nh,
            "film": scraper_lk21, "ai2": scraper_ai2}.get(src, scraper_dracin)


def _dr_search(src: str, q: str, page: int) -> tuple[list, int]:
    return _dr_mod(src).search(q, page)


def new_state_d(q: str, page: int, total: int, items: list,
                src: str = "drc") -> str:
    qid = uuid.uuid4().hex[:8]
    STATES_D[qid] = {"q": q, "page": page, "total": total, "items": items,
                     "src": src, "details": {}}
    STATES_D.move_to_end(qid)
    while len(STATES_D) > 120:
        STATES_D.popitem(last=False)
    return qid


def _state_d(qid: str) -> dict | None:
    st = STATES_D.get(qid)
    if st:
        STATES_D.move_to_end(qid)
    return st


def d_pages(total: int) -> int:
    return max(1, (total + DR_PER_PAGE - 1) // DR_PER_PAGE)


def render_dlist(st: dict, qid: str):
    items, total, page = st["items"], st["total"], st["page"]
    label = st["q"] or "update terbaru"
    src = st.get("src", "drc")
    other = _dr_next(src)
    maxp = d_pages(total)
    head = (f"🎬 <b>{esc(label)}</b> — {DR_LABEL[src]} — halaman <b>{page}</b> "
            f"dari {maxp}\nhasil di halaman ini: <b>{len(items)}</b> dari "
            f"{total:,} judul\n\n")
    if not items:
        return (head + "nggak ada hasil — coba kata lain, atau /dracin buat terbaru.",
                InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔄 terbaru", callback_data=f"drs|{qid}|1")]]))
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"<b>{i}.</b> {esc(it['title'][:100])}")
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(1, len(items) + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"drk|{qid}|{i}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ prev", callback_data=f"drs|{qid}|{page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {page}/{maxp}", callback_data=f"drs|{qid}|{page}"))
    if page < maxp:
        nav.append(InlineKeyboardButton("next ➡️", callback_data=f"drs|{qid}|{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(
        f"🔁 ganti sumber → {DR_LABEL[other]}", callback_data=f"drg|{qid}|0")])
    return head + "\n".join(lines), InlineKeyboardMarkup(rows)


async def _do_dracin(update: Update, query: str, src: str):
    q = re.sub(r"\s+", " ", query).strip()[:80]
    msg = await update.message.reply_text(
        f"🎬 mencari <b>{esc(q)}</b> di {DR_LABEL[src]}…" if q
        else f"🎬 memuat terbaru dari {DR_LABEL[src]}…",
        parse_mode=ParseMode.HTML)
    try:
        items, total = await asyncio.to_thread(_dr_search, src, q, 1)
    except Exception as e:
        log.exception("dracin search gagal")
        await msg.edit_text(f"❌ {esc(str(e))[:200]}", parse_mode=ParseMode.HTML)
        return
    qid = new_state_d(q, 1, total, items, src)
    text, kb = render_dlist(_state_d(qid), qid)
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list dracin gagal: %s", e)


async def h_dracin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dracin [judul] — cari dari index lokal; kosong = terbaru."""
    await _do_dracin(update, " ".join(context.args or []), "drc")


async def h_dracin2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dracin2 [judul] — sumber dracin.best (full episode tanpa gate)."""
    await _do_dracin(update, " ".join(context.args or []), "best")


async def h_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ai [judul] — Candy AI Shorts: seri porno AI (EP awal gratis per judul)."""
    await _do_dracin(update, " ".join(context.args or []), "candy")


async def h_hvid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hvid [judul] — NontonHentai: video hentai sub Indo, semua EP gratis."""
    await _do_dracin(update, " ".join(context.args or []), "nh")


# ═══ STATISTIK + PREFERENSI + /acak + /hemat ═══════════════════════════════════
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.pkl")
PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prefs.pkl")


def _stats_load() -> dict:
    try:
        return pickle.loads(open(STATS_FILE, "rb").read())
    except Exception:
        return {"total": {}, "hari": {}, "tgl": ""}


def _bump(kind: str):
    """Counter video/zip terkirim — dipanggil dari tiap log 'terkirim'."""
    import datetime as _dt
    s = _stats_load()
    tgl = _dt.date.today().isoformat()
    if s.get("tgl") != tgl:
        s["tgl"], s["hari"] = tgl, {}
    s["total"][kind] = s["total"].get(kind, 0) + 1
    s["hari"][kind] = s["hari"].get(kind, 0) + 1
    try:
        open(STATS_FILE, "wb").write(pickle.dumps(s))
    except OSError:
        pass


async def h_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stat — statistik pemakaian bot (hari ini + total)."""
    s = _stats_load()
    lines = ["📊 <b>Statistik bot</b>", "", "<b>hari ini:</b>"]
    for k, v in sorted(s.get("hari", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {k}: <b>{v}</b>")
    lines.append(f"  ─ total hari ini: <b>{sum(s.get('hari', {}).values())}</b>")
    lines += ["", "<b>sejak awal:</b>"]
    for k, v in sorted(s.get("total", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {k}: <b>{v}</b>")
    await update.message.reply_text("\n".join(lines),
                                    parse_mode=ParseMode.HTML)


def _prefs_load() -> dict:
    try:
        return pickle.loads(open(PREFS_FILE, "rb").read())
    except Exception:
        return {}


def _pref(uid: int, key: str, default=None):
    return _prefs_load().get(str(uid), {}).get(key, default)


def _pref_set(uid: int, key: str, val):
    p = _prefs_load()
    p.setdefault(str(uid), {})[key] = val
    try:
        open(PREFS_FILE, "wb").write(pickle.dumps(p))
    except OSError:
        pass


async def h_hemat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hemat on|off — mode hemat kuota: stream default 360p."""
    uid = update.effective_user.id
    arg = (context.args or ["status"])[0].lower()
    if arg in ("on", "1", "ya", "nyala"):
        _pref_set(uid, "hemat", True)
        await update.message.reply_text(
            "💧 <b>mode hemat AKTIF</b> — tombol ▶️ Nonton sekarang default "
            "<b>360p</b> (lebih hemat, kalau butuh jernih pilih resolusi "
            "di tombol lain)", parse_mode=ParseMode.HTML)
    elif arg in ("off", "0", "engga", "mati"):
        _pref_set(uid, "hemat", False)
        await update.message.reply_text(
            "🎬 mode hemat <b>mati</b> — Nonton default 480p lagi.")
    else:
        st = "AKTIF 💧" if _pref(uid, "hemat") else "mati"
        await update.message.reply_text(
            f"mode hemat: <b>{st}</b>\n/hemat on — /hemat off",
            parse_mode=ParseMode.HTML)


async def h_acak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/acak [genre:xxx|tahun:xxxx|negara:xxx] — rekomendasi film random."""
    import random as _rnd
    q = " ".join(context.args or [])
    fq = scraper_lk21.parse_query(q)
    try:
        if fq.get("kind"):
            mp = scraper_lk21._maxpage(fq["kind"], fq["slug"])
            page = _rnd.randint(1, min(mp, 15))
            items, _tot = scraper_lk21._archive(fq["kind"], fq["slug"], page)
            label = fq["label"]
        else:
            items, _tot = scraper_lk21.search("", _rnd.randint(1, 3))
            label = "film terbaru"
    except Exception as e:
        await update.message.reply_text(f"❌ acak gagal: {e}")
        return
    if not items:
        await update.message.reply_text("kosong — coba /acak lagi.")
        return
    it = _rnd.choice(items)
    try:
        d = await asyncio.to_thread(scraper_lk21.detail, it["url"])
    except Exception as e:
        await update.message.reply_text(f"❌ detail gagal: {e}")
        return
    cap = (f"🎲 <b>Rekomendasi {esc(label)}</b>\n"
           f"<b>{esc(d['title'][:70])}</b> · {esc(d.get('year') or '')}\n"
           f"{esc(', '.join(d.get('genres', [])[:4]))}\n\n"
           f"{esc((d.get('synopsis') or '')[:280])}…\n\n"
           f"🇮🇩 sub Indo (di-burn) · tombol ↓")
    qidA = new_state_d(label, 1, 1, [it], "film")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬇️ unduh film", callback_data=f"drd|{qidA}|1"),
        InlineKeyboardButton("🎲 lagi", callback_data="acak_lagi|" + q),
    ], [InlineKeyboardButton("🌐 situs", url=it["url"]),
        InlineKeyboardButton("🏠 menu", callback_data="mn|back")]])
    try:
        if d.get("poster"):
            await update.message.reply_photo(d["poster"], caption=cap,
                                             parse_mode=ParseMode.HTML,
                                             reply_markup=kb)
        else:
            await update.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                            reply_markup=kb)
    except Exception:
        await update.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                        reply_markup=kb)


async def h_acak_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """acak_lagi|<q> — regen rekomendasi."""
    q = update.callback_query
    await q.answer("🎲 ...")
    upd = types.SimpleNamespace(
        message=q.message, effective_user=update.effective_user,
        effective_chat=update.effective_chat)
    await h_acak(upd, types.SimpleNamespace(args=q.data.split("|", 1)[1:]))


# ═══ FAVORIT / BOOKMARK / LANJUT (sqlite personal) ════════════════════════════
import sqlite3

FAV_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favorit.db")


def _db():
    c = sqlite3.connect(FAV_DB, timeout=15)
    c.execute("CREATE TABLE IF NOT EXISTS fav("
              "id INTEGER PRIMARY KEY, uid INT, src TEXT, url TEXT,"
              "title TEXT, added TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS bk(uid INT, key TEXT, pos INT,"
              " PRIMARY KEY(uid, key))")
    c.execute("CREATE TABLE IF NOT EXISTS last(uid INT PRIMARY KEY, src TEXT,"
              " title TEXT, url TEXT, ep TEXT, tgl TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS subs(uid INT, kind TEXT, slug TEXT,"
              " label TEXT, PRIMARY KEY(uid, kind, slug))")
    c.execute("CREATE TABLE IF NOT EXISTS seen(url TEXT PRIMARY KEY)")
    return c


def _bk_get(uid: int, key: str):
    try:
        with _db() as c:
            r = c.execute("SELECT pos FROM bk WHERE uid=? AND key=?",
                          (uid, key)).fetchone()
            return r[0] if r else None
    except sqlite3.Error:
        return None


def _bk_set(uid: int, key: str, pos: int):
    try:
        with _db() as c:
            c.execute("INSERT INTO bk(uid, key, pos) VALUES(?,?,?) "
                      "ON CONFLICT(uid, key) DO UPDATE SET pos=excluded.pos",
                      (uid, key, pos))
    except sqlite3.Error:
        pass


def _lanjut_set(uid: int, src: str, title: str, url: str, ep=""):
    import datetime as _dt
    try:
        with _db() as c:
            c.execute("INSERT INTO last(uid, src, title, url, ep, tgl) "
                      "VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET "
                      "src=excluded.src, title=excluded.title,"
                      " url=excluded.url, ep=excluded.ep, tgl=excluded.tgl",
                      (uid, src, title[:80], url, str(ep),
                       _dt.datetime.now().strftime("%d/%m %H:%M")))
    except sqlite3.Error:
        pass


async def h_simpan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """sv|<qid>|<idx> — simpan item ke favorit (dari tombol 💾)."""
    q = update.callback_query
    data = q.data or ""
    _, qid, idx = (data.split("|", 2) + ["", ""])[:3]
    _uSV = getattr(update, "effective_user", None)
    uid = _uSV.id if _uSV else 0
    st = STATES_D.get(qid)
    if not st:
        await q.answer("state basi — cari ulang", show_alert=True)
        return
    try:
        it = st["items"][int(idx) - 1]
    except (ValueError, IndexError):
        await q.answer("index invalid", show_alert=True)
        return
    url, title = it.get("url", ""), it.get("title", "?")
    with _db() as c:
        dup = c.execute("SELECT id FROM fav WHERE uid=? AND url=?",
                        (uid, url)).fetchone()
        if not dup:
            import datetime as _dt
            c.execute("INSERT INTO fav(uid, src, url, title, added)"
                      " VALUES(?,?,?,?,?)",
                      (uid, st.get("src", "?"), url, title[:90],
                       _dt.datetime.now().strftime("%d/%m")))
    await q.answer(f"💾 disimpan: {title[:50]}")
    try:
        await q.message.reply_text(
            f"💾 <b>{esc(title[:70])}</b> masuk koleksi\n"
            f"lihat: /koleksi", parse_mode=ParseMode.HTML)
    except TelegramError:
        pass


async def h_koleksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/koleksi — daftar favorit lu + tombol unduh (film) / situs."""
    uid = update.effective_user.id
    with _db() as c:
        rows = c.execute("SELECT id, src, url, title, added FROM fav"
                         " WHERE uid=? ORDER BY id DESC LIMIT 15",
                         (uid,)).fetchall()
    if not rows:
        await update.message.reply_text(
            "kosong — klik 💾 di detail film buat simpan.")
        return
    teks = "💾 <b>Koleksi lu</b>\n\n"
    rows_kb = []
    for fid, src, url, title, added in rows:
        teks += f"<b>{esc(title[:60])}</b> <i>({esc(src)}, {esc(added)})</i>\n"
        if src == "film":
            rows_kb.append([
                InlineKeyboardButton(f"⬇️ {title[:26]}…",
                                     callback_data=f"kdl|{fid}"),
                InlineKeyboardButton("🗑", callback_data=f"kh|{fid}")])
        else:
            rows_kb.append([
                InlineKeyboardButton(f"🌐 {title[:26]}…", url=url),
                InlineKeyboardButton("🗑", callback_data=f"kh|{fid}")])
    rows_kb.append([InlineKeyboardButton("🏠 menu", callback_data="mn|back")])
    await update.message.reply_text(teks, parse_mode=ParseMode.HTML,
                                    reply_markup=InlineKeyboardMarkup(rows_kb))


async def h_koleksi_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """kh|<id> hapus favorit · kdl|<id> unduh film favorit."""
    q = update.callback_query
    kind, fid = (q.data.split("|", 1) + [""])[:2]
    _uKC = getattr(update, "effective_user", None)
    uid = _uKC.id if _uKC else 0
    with _db() as c:
        row = c.execute("SELECT src, url, title FROM fav WHERE id=? AND uid=?",
                        (int(fid), uid)).fetchone() if fid.isdigit() else None
        if kind == "kh" and row:
            c.execute("DELETE FROM fav WHERE id=? AND uid=?",
                      (int(fid), uid))
    if kind == "kh":
        await q.answer("🗑 dihapus")
        try:
            await q.message.delete()
        except TelegramError:
            pass
        return
    if not row:
        await q.answer("favorit basi", show_alert=True)
        return
    src, url, title = row
    if src != "film":
        await q.answer("buka linknya aja ya", show_alert=True)
        return
    await q.answer("⏳ siapkan film…")
    qidF = new_state_d(title, 1, 1,
                       [{"title": title, "url": url, "slug": "", "year": ""}],
                       "film")
    await h_cb_d(types.SimpleNamespace(
        callback_query=types.SimpleNamespace(
            data=f"drd|{qidF}|1", answer=q.answer, message=q.message),
        effective_user=update.effective_user), context)


async def h_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sub genre:horror — notif film baru; /sub list · /sub del genre:x"""
    uid = update.effective_user.id
    args = context.args or []
    cmd = (args[0] if args else "list").lower()
    if cmd == "list":
        with _db() as c:
            rows = c.execute("SELECT kind, label FROM subs WHERE uid=?",
                             (uid,)).fetchall()
        if not rows:
            await update.message.reply_text(
                "belum subscribe — coba: /sub genre:horror\n"
                "(notif tiap ada film baru di arsip itu)")
            return
        teks = "🔔 <b>subscribe aktif:</b>\n" + "\n".join(
            f"  • {esc(lbl)} ({kd})" for kd, lbl in rows)
        await update.message.reply_text(teks, parse_mode=ParseMode.HTML)
        return
    if cmd == "del":
        fq = scraper_lk21.parse_query(" ".join(args[1:]))
        if not fq.get("kind"):
            await update.message.reply_text(
                "pakai: /sub del genre:horror (samain sama waktu /sub)")
            return
        with _db() as c:
            c.execute("DELETE FROM subs WHERE uid=? AND kind=? AND slug=?",
                      (uid, fq["kind"], fq["slug"]))
        await update.message.reply_text(f"🔕 unsubscribe {esc(fq['label'])}.",
                                        parse_mode=ParseMode.HTML)
        return
    fq = scraper_lk21.parse_query(" ".join(args))
    if not fq.get("kind"):
        await update.message.reply_text(
            "pakai: /sub genre:horror · /sub tahun:2026 · /sub negara:jepang\n"
            "/sub list · /sub del genre:horror")
        return
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO subs(uid, kind, slug, label)"
                  " VALUES(?,?,?,?)", (uid, fq["kind"], fq["slug"], fq["label"]))
        # tandai yang udah ada sekarang biar gak langsung spam
        try:
            items, _t = scraper_lk21._archive(fq["kind"], fq["slug"], 1)
            for i in items[:30]:
                c.execute("INSERT OR IGNORE INTO seen(url) VALUES(?)",
                          (i["url"],))
        except Exception:
            pass
    await update.message.reply_text(
        f"🔔 subscribe <b>{esc(fq['label'])}</b> aktif\n"
        "gua cek tiap 6 jam — film baru gua kabarin di sini.",
        parse_mode=ParseMode.HTML)


async def _sub_check_once(app=None):
    """Cek semua subscribe → kirim notif film baru (max 5/jalur)."""
    with _db() as c:
        subs = c.execute("SELECT uid, kind, slug, label FROM subs").fetchall()
        if not subs:
            return
        seen = {r[0] for r in c.execute("SELECT url FROM seen").fetchall()}
    baru_total = []
    for uid, kind, slug, label in subs:
        try:
            items, _t = await asyncio.to_thread(
                scraper_lk21._archive, kind, slug, 1)
        except Exception as e:
            log.warning("sub check %s gagal: %s", label, e)
            continue
        baru = [i for i in items if i["url"] not in seen][:5]
        baru_total.append((uid, label, baru))
        with _db() as c:
            for i in baru:
                c.execute("INSERT OR IGNORE INTO seen(url) VALUES(?)",
                          (i["url"],))
    if not baru_total:
        return
    bot_app = app
    for uid, label, baru in baru_total:
        if not baru:
            continue
        text = (f"🔔 <b>film baru — {esc(label)}</b>\n\n" + "\n".join(
            f"• {esc(i['title'][:60])}" for i in baru))
        try:
            await bot_app.bot.send_message(uid, text,
                                           parse_mode=ParseMode.HTML)
        except Exception as e:
            log.warning("kirim notif sub gagal: %s", e)


async def _sub_loop(app):
    """Loop background: cek subscribe tiap 6 jam."""
    await asyncio.sleep(120)            # tunggu bot stabil dulu
    while True:
        try:
            await _sub_check_once(app)
        except Exception:
            log.exception("sub loop error")
        await asyncio.sleep(6 * 3600)


async def h_lanjut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lanjut — video/film terakhir yang lu tonton."""
    uid = update.effective_user.id
    with _db() as c:
        row = c.execute("SELECT src, title, url, ep, tgl FROM last"
                        " WHERE uid=?", (uid,)).fetchone()
    if not row:
        await update.message.reply_text("belum ada yang bisa diterusin.")
        return
    src, title, url, ep, tgl = row
    text = (f"▶️ <b>Lanjut terakhir</b> ({esc(tgl)})\n"
            f"{esc(title)}" + (f" · EP {esc(ep)}" if ep else "") + "\n"
            f"<i>{esc(src)}</i>")
    rows = []
    if src == "film":
        qidF = new_state_d(title, 1, 1,
                           [{"title": title, "url": url, "slug": "",
                             "year": ""}], "film")
        rows.append([InlineKeyboardButton("⬇️ unduh lagi",
                                          callback_data=f"drd|{qidF}|1")])
    rows.append([InlineKeyboardButton("🌐 situs", url=url)])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                    reply_markup=InlineKeyboardMarkup(rows))


# ═══ /aiv — AI VIDEO (EPORNER kategori AI, video AI-generated) ═══════════════
AIV_PG: Dict[int, Dict] = {}        # qid → {q, page, total}
AIV_D: Dict[int, tuple] = {}        # idx → (url, res, judul)
AIV_MAX = 45 * 1024 * 1024          # batas kirim video Telegram


async def _aiv_send_list(update_or_msg, context, qid):
    st = AIV_PG.get(qid)
    if not st:
        return
    try:
        items, tot = await asyncio.to_thread(
            scraper_epai.search, st["q"], st["page"])
    except Exception as e:
        log.warning("aiv search gagal: %s", e)
        return
    if not items:
        return
    limit = max(len(items), 1)
    total_pages = max(-(-tot // limit), 1)
    label = st["q"] or "AI terbaru"
    teks = (f"🤖 <b>AI Video — {esc(label)}</b>\n"
            f"hal. {st['page']}/{total_pages} · sumber EPORNER (AI-generated)\n\n")
    rows = []
    for i, it in enumerate(items):
        teks += f"<code>{i + 1}</code> {esc(it['title'][:56])}\n"
        rows.append([InlineKeyboardButton(f"{i + 1}. {it['title'][:30]}…",
                                          callback_data=f"aiv|{i}|{it['url']}")])
    nav = []
    if st["page"] > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data="aivn|-1"))
    nav.append(InlineKeyboardButton("🔄 ulang", callback_data=f"aivr"))
    if st["page"] * limit < tot:
        nav.append(InlineKeyboardButton("➡️", callback_data="aivn|1"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🏠 menu", callback_data="mn|back")])
    reply_markup = InlineKeyboardMarkup(rows)
    try:
        await update_or_msg.edit_message_text(teks, parse_mode=ParseMode.HTML,
                                              reply_markup=reply_markup)
    except Exception:
        await update_or_msg.reply_text(teks, parse_mode=ParseMode.HTML,
                                       reply_markup=reply_markup)


async def h_aiv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"/aiv [query]" — video AI-generated (EPORNER kategori AI)."""
    q = " ".join(context.args or [])
    qid = update.effective_user.id
    try:
        items, tot = await asyncio.to_thread(scraper_epai.search, q, 1)
    except Exception as e:
        await update.message.reply_text(f"❌ gagal ambil daftar AI: {e}")
        return
    if not items:
        await update.message.reply_text("tidak ada hasil — /aiv aja (AI terbaru).")
        return
    AIV_PG[qid] = {"q": q, "page": 1, "total": tot}
    await _aiv_send_list(update.message, context, qid)


async def h_aiv_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """aiv|n|<url> — detail + tombol kualitas (auto < 45MB)."""
    q = update.callback_query
    await q.answer()
    _, idx, url = q.data.split("|", 2)
    try:
        d = await asyncio.to_thread(scraper_epai.detail, url)
    except Exception as e:
        await q.edit_message_text(f"❌ detail gagal: {e}")
        return
    kual = [k for k in d["qualities"] if k["bytes"] < AIV_MAX] or d["qualities"][:1]
    caption = (f"🤖 <b>{esc(d['title'][:70])}</b>\n"
               f"⏱ {esc(d['duration'] or '?')} · {len(d['qualities'])} kualitas\n"
               f"pilih kualitas ↓ (auto &lt; 45MB biar muat Telegram)")
    rows = [[InlineKeyboardButton(
        f"⬇️ {k['res']} ({k['size']})",
        callback_data=f"aivd|{idx}|{url}|{k['res']}")] for k in kual]
    rows.append([InlineKeyboardButton("🌐 situs", url=url),
                 InlineKeyboardButton("⬅️ daftar", callback_data="aivb")])
    if d.get("thumb"):
        try:
            await q.message.reply_photo(
                d["thumb"], caption=caption, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows))
            await q.message.delete()
            return
        except Exception as e:
            log.warning("aiv thumb gagal: %s", e)
    await q.edit_message_text(caption, parse_mode=ParseMode.HTML,
                              reply_markup=InlineKeyboardMarkup(rows))


async def h_aiv_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """aivd|<idx>|<url>|<res> — download + kirim video."""
    q = update.callback_query
    await q.answer()
    _, idx, url, res = q.data.split("|", 3)
    jud = AIV_D.get(int(idx) if idx.isdigit() else 0, ("",))[0]
    await q.edit_message_text(f"⏳ download {res}… (biasanya cepet, < 1 menit)")
    out = f"aiv-{uuid.uuid4().hex[:8]}.mp4"
    try:
        path, size = await asyncio.wait_for(asyncio.to_thread(
            scraper_epai.download, url, out, res), timeout=1800)
        path = _faststart(path)
        size = os.path.getsize(path)
    except Exception as e:
        await q.edit_message_text(f"❌ download gagal: {e}")
        return
    try:
        with open(path, "rb") as f:
            await q.message.reply_video(
                f, caption=f"🤖 AI video ({res}) · {size / 1e6:.1f} MB · "
                f"EPORNER/AI-generated", supports_streaming=False)
        log.info("aiv terkirim: %s (%.1fMB)", jud or url[-24:], size / 1e6)
        _bump("ai-video")
        _lanjut_set(q.message.chat.id, "ai-video", jud or "AI video", url)
    except Exception as e:
        log.warning("aiv kirim gagal: %s", e)
        await q.edit_message_text(f"❌ kirim gagal: {e}")
    finally:
        os.remove(path)


async def h_aiv_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """aivn|±1 / aivb / aivr — navigasi daftar aiv."""
    q = update.callback_query
    await q.answer()
    qid = update.effective_user.id
    st = AIV_PG.get(qid)
    if not st:
        await q.edit_message_text("daftar basi — /aiv lagi aja.")
        return
    if q.data == "aivb":
        st["page"] = max(1, st["page"] - 1)
    elif q.data == "aivn|-1":
        st["page"] = max(1, st["page"] - 1)
    elif q.data == "aivn|1":
        st["page"] += 1
    await _aiv_send_list(q.message, context, qid)


async def h_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"/film [judul]" — LK21: cari film & series gratis (27rb+ judul)."""
    await _do_dracin(update, " ".join(context.args or []), "film")


async def h_ai2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ai2 [judul] — Swaplse: video hentai AI, semua GRATIS tanpa login."""
    await _do_dracin(update, " ".join(context.args or []), "ai2")


async def d_goto_page(update: Update, qid: str, page: int):
    q = update.callback_query
    st = _state_d(qid)
    if not st:
        await q.answer("hasil sudah basi — /dracin lagi", show_alert=True)
        return
    maxp = d_pages(st["total"])
    if page < 1 or page > maxp or page == st["page"]:
        await q.answer()
        return
    await q.answer("⏳ memuat…")
    try:
        items, total = await asyncio.to_thread(
            _dr_search, st.get("src", "drc"), st["q"], page)
    except Exception as e:
        log.exception("paging dracin gagal")
        try:
            await q.message.reply_text(f"❌ gagal pindah halaman: {esc(str(e))[:160]}",
                                       parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        return
    st.update(page=page, items=items, total=total)
    text, kb = render_dlist(st, qid)
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("edit list dracin gagal: %s", e)


def d_eps_kb(qid: str, idx: int, ep_page: int, e0: int, e1: int, site: str):
    eps = list(range(e0, e1 + 1))
    per = 12
    pages = max(1, (len(eps) + per - 1) // per)
    ep_page = max(1, min(ep_page, pages))
    chunk = eps[(ep_page - 1) * per: ep_page * per]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for ep in chunk:
        row.append(InlineKeyboardButton(f"EP {ep}", callback_data=f"drd|{qid}|{idx}|{ep}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("💾 simpan ke koleksi",
                                      callback_data=f"sv|{qid}|{idx}")])
    if pages > 1:
        nav: list[list[InlineKeyboardButton]] = [
            InlineKeyboardButton("⏮", callback_data=f"drp|{qid}|{idx}|1")]
        if ep_page > 1:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"drp|{qid}|{idx}|{ep_page - 1}"))
        nav.append(InlineKeyboardButton(f"📄 ep {ep_page}/{pages}", callback_data=f"drp|{qid}|{idx}|{ep_page}"))
        if ep_page < pages:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"drp|{qid}|{idx}|{ep_page + 1}"))
        nav.append(InlineKeyboardButton("⏭", callback_data=f"drp|{qid}|{idx}|{pages}"))
        rows.append(nav)
    rows.append([_finish_kb_btn(qid, idx),
                 InlineKeyboardButton("🌐 Situs", url=site),
                 InlineKeyboardButton("🔙 Daftar", callback_data=f"drs|{qid}|1")])
    return InlineKeyboardMarkup(rows)


async def d_detail(update: Update, qid: str, idx: int):
    q = update.callback_query
    st = _state_d(qid)
    if not st or not (1 <= idx <= len(st["items"])):
        await q.answer("hasil sudah basi — /dracin lagi", show_alert=True)
        return
    it = st["items"][idx - 1]
    if st.get("src") == "nh":
        # NontonHentai: SEMUA episode gratis — daftar EP dari series page
        await q.answer("⏳ memuat detail…")
        try:
            d = st.setdefault("details", {}).get(it["url"])
            if not d:
                d = await asyncio.wait_for(scraper_nh.detail(it["url"]), 40)
                st["details"][it["url"]] = d
        except Exception as e:
            log.exception("detail nh gagal")
            try:
                await q.message.reply_text(
                    f"❌ gagal ambil detail: {esc(str(e))[:200]}",
                    parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        e0, e1 = 1, d["total"]
        st.setdefault("eps", {})[idx] = (e0, e1)
        cap = (f"<b>{esc(d['title'] or it['title'])}</b>\n"
               f"🎬 {e1} episode · hentai <b>sub Indo</b> · "
               f"<b>semua episode GRATIS</b>\n\n"
               f"pilih episode di bawah\n⬇️ unduh = MP4 full (ffmpeg, cepat)")
        kb = d_eps_kb(qid, idx, 1, e0, e1, it["url"])
        photo = await fetch_thumb(d.get("thumb") or "")
        sent = None
        try:
            if photo:
                sent = await q.message.reply_photo(photo=photo, caption=cap,
                                                   parse_mode=ParseMode.HTML,
                                                   reply_markup=kb)
            else:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
        except TelegramError as e:
            log.warning("kirim detail nh gagal: %s", e)
            try:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
            except TelegramError:
                pass
        _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
                  msg=getattr(sent, "message_id", None), site=it.get("url", ""))
        return
    if st.get("src") == "ai2":
        # Swaplse AI: 1 karya = 1 video pendek — 1 tombol EP 1
        await q.answer("⏳ memuat detail…")
        try:
            d = st.setdefault("details", {}).get(it["url"])
            if not d:
                d = await asyncio.wait_for(scraper_ai2.detail(it["url"]), 30)
                st["details"][it["url"]] = d
        except Exception as e:
            log.exception("detail ai2 gagal")
            try:
                await q.message.reply_text(
                    f"❌ gagal ambil detail: {esc(str(e))[:200]}",
                    parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        st.setdefault("eps", {})[idx] = (1, 1)
        cap = (f"<b>{esc(d['title'] or it['title'])}</b>\n"
               f"🎬 video AI pendek (3-30 detik) · <b>semua GRATIS</b> "
               f"tanpa login · {DR_LABEL['ai2']}\n\n"
               f"⬇️ unduh = MP4 direct")
        kb = d_eps_kb(qid, idx, 1, 1, 1, it["url"])
        photo = await fetch_thumb("")
        sent = None
        try:
            if photo:
                sent = await q.message.reply_photo(photo=photo, caption=cap,
                                                   parse_mode=ParseMode.HTML,
                                                   reply_markup=kb)
            else:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
        except TelegramError as e:
            log.warning("kirim detail ai2 gagal: %s", e)
            try:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
            except TelegramError:
                pass
        _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
                  msg=getattr(sent, "message_id", None), site=it.get("url", ""))
        return
    if st.get("src") == "film":
        # LK21.dev: film mainstream, sub Indo — 1 tombol unduh
        await q.answer("⏳ memuat detail film…")
        try:
            d = st.setdefault("details", {}).get(it["url"])
            if not d:
                d = await asyncio.wait_for(
                    asyncio.to_thread(scraper_lk21.detail, it["url"]), 40)
                st["details"][it["url"]] = d
        except Exception as e:
            log.exception("detail film gagal")
            try:
                await q.message.reply_text(
                    f"❌ gagal ambil detail: {esc(str(e))[:200]}",
                    parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        if not d.get("embed"):
            await q.message.reply_text(
                "❌ film ini lagi nggak punya server streaming",
                parse_mode=ParseMode.HTML)
            return
        st.setdefault("eps", {})[idx] = (1, 1)
        meta = " · ".join(x for x in [(d.get("year") or None)]
                          if x) or "film"
        cap = (f"<b>{esc(d['title'] or it['title'])}</b>\n"
               f"🎬 {esc(meta)} · {DR_LABEL['film']}\n"
               + (f"🎭 {esc(', '.join(d['genres'][:5]))}\n" if d.get("genres") else "")
               + "\n" + esc((d.get("synopsis") or "sinopsis nggak tersedia")[:600])
               + "\n\n🇮🇩 <b>subtitle Indonesia</b> — di-burn ke video\n"
                 "🎬 <b>film penuh</b> — 1 tombol unduh di bawah")
        kb = d_eps_kb(qid, idx, 1, 1, 1, it["url"])
        photo = await fetch_thumb(d.get("poster") or "")
        sent = None
        try:
            if photo:
                sent = await q.message.reply_photo(photo=photo, caption=cap,
                                                   parse_mode=ParseMode.HTML,
                                                   reply_markup=kb)
            else:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
        except TelegramError as e:
            log.warning("kirim detail film gagal: %s", e)
            try:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
            except TelegramError:
                pass
        _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
                  msg=getattr(sent, "message_id", None), site=it.get("url", ""))
        return
    if st.get("src") == "candy":
        # Candy AI Shorts: EP gratis = bagian awal (free-episode-limit=2).
        # Jawab SEKALI dulu (Telegram nolak answer kedua).
        await q.answer("⏳ memuat detail…")
        try:
            d = st.setdefault("details", {}).get(it["url"])
            if not d:
                d = await asyncio.wait_for(scraper_candy.detail(it["url"]), 40)
                st["details"][it["url"]] = d
        except Exception as e:
            log.exception("detail candy gagal")
            try:
                await q.message.reply_text(
                    f"❌ gagal ambil detail: {esc(str(e))[:200]}",
                    parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        free = [e["n"] for e in d["eps"] if e["free"]]
        if not free:
            try:
                await q.message.reply_text(
                    "judul ini nggak punya episode gratis — coba judul lain "
                    "(/ai).")
            except TelegramError:
                pass
            return
        # tombol EP = rentang EP gratis (umumnya 1..2, kontigu dari awal)
        e0, e1 = min(free), max(free)
        st.setdefault("eps", {})[idx] = (e0, e1)
        cap = (f"<b>{esc(d['title'] or it['title'])}</b>\n"
               f"🎬 {d['total']} episode · <b>{d['free_n']} episode GRATIS</b> "
               f"· AI-generated 18+\n\n"
               f"pilih EP gratis di bawah — sisanya paywall Premium "
               f"(dilewati, jujur)\n⬇️ unduh = MP4 asli dari CDN (via proxy)")
        kb = d_eps_kb(qid, idx, 1, e0, e1, it["url"])
        sent = None
        try:
            sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                              reply_markup=kb)
        except TelegramError as e:
            log.warning("kirim detail candy gagal: %s", e)
            return
        _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
                  msg=getattr(sent, "message_id", None), site=it.get("url", ""))
        return
    if st.get("src") == "best":
        # jawab SEKALI dengan toast "memuat" (Telegram nolak answer kedua)
        await q.answer("⏳ memuat detail…")
        # dracin.best: cover + jumlah episode dari halaman detail (direct, cepat)
        try:
            d = st.setdefault("details", {}).get(it["url"])
            if not d:
                d = await asyncio.wait_for(scraper_drbest.detail(it["url"]), 40)
                st["details"][it["url"]] = d
        except Exception as e:
            log.exception("detail drbest gagal")
            try:
                await q.message.reply_text(
                    f"❌ gagal ambil detail: {esc(str(e))[:200]}",
                    parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        e0, e1 = 1, max(1, d["eps"])
        st.setdefault("eps", {})[idx] = (e0, e1)
        cap = (f"<b>{esc(d['title'] or it['title'])}</b>\n"
               f"🎬 {e1} episode · {esc(it.get('provider') or 'dracin.best')} "
               f"sub Indo\n\n"
               f"pilih episode di bawah — <b>semua episode gratis</b>, "
               f"tanpa login\n⬇️ unduh = full episode (ffmpeg, cepat)")
        kb = d_eps_kb(qid, idx, 1, e0, e1, it["url"])
        photo = await fetch_thumb(d.get("thumb") or "")
        sent = None
        try:
            if photo:
                sent = await q.message.reply_photo(photo=photo, caption=cap,
                                                   parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
        except TelegramError as e:
            log.warning("kirim detail drbest gagal: %s", e)
            try:
                sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML,
                                                  reply_markup=kb)
            except TelegramError:
                pass
        _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
                  msg=getattr(sent, "message_id", None), site=it.get("url", ""))
        return
    await q.answer()
    e0, e1 = scraper_dracin.eps_range(it.get("desc") or "")
    st.setdefault("eps", {})[idx] = (e0, e1)
    n_eps = e1 - e0 + 1
    cap = (f"<b>{esc(it['title'])}</b>\n"
           f"🎬 {n_eps} episode · dracinema sub Indo\n\n"
           f"pilih episode di bawah (EP 1-5 <b>gratis</b>, sisanya butuh "
           f"login akun dracinema)\n"
           "⬇️ unduh = MP4 langsung ke chat")
    kb = d_eps_kb(qid, idx, 1, e0, e1, it["url"])
    photo = await fetch_thumb(it.get("thumb") or "")
    sent = None
    try:
        if photo:
            sent = await q.message.reply_photo(photo=photo, caption=cap,
                                               parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError as e:
        log.warning("kirim detail dracin gagal: %s", e)
        try:
            sent = await q.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            pass
    _set_last(q.message.chat.id, "d", qid=qid, idx=idx,
              msg=getattr(sent, "message_id", None), site=it.get("url", ""))


async def _split_mp4(path: str, base_out: str, max_bytes: int) -> list[str]:
    """Potong mp4 jadi beberapa bagian ≤ max_bytes (stream copy, tanpa re-encode)."""
    def _run() -> list[str]:
        import subprocess
        dur = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30).stdout.strip()
        try:
            total_d = float(dur)
        except ValueError:
            total_d = 0.0
        size = os.path.getsize(path)
        parts = max(2, -(-size // (max_bytes - 256 * 1024)))
        seg_t = max(30, int(total_d / parts) + 10) if total_d else 600
        out = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy",
             "-map", "0", "-f", "segment", "-segment_time", str(seg_t),
             "-reset_timestamps", "1", base_out + ".part%02d.mp4"],
            capture_output=True, text=True, timeout=600)
        if out.returncode != 0:
            raise RuntimeError("ffmpeg split gagal: " + out.stderr[:200])
        import glob
        return sorted(glob.glob(base_out + ".part*.mp4"))
    return await asyncio.to_thread(_run)


async def d_download(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     qid: str, idx: int, ep: int):
    """Unduh episode dracin: playback → pilih quality yang muat → kirim."""
    q = update.callback_query
    st = _state_d(qid)
    if not st or not (1 <= idx <= len(st["items"])):
        await q.answer("hasil sudah basi — /dracin lagi", show_alert=True)
        return
    chat = q.message.chat.id
    if chat in BUSY and chat not in _WORKING:
        pos = len(_QUEUES.get(chat, ())) + 1
        await q.answer(f"⏳ masuk antrian #{pos} — nunggu yang sebelumnya")
        _QUEUES.setdefault(chat, _deq()).append(
            (f"drd {qid}|{idx}",
             lambda: h_cb_d(update, context)))
        return
    await q.answer()
    it = st["items"][idx - 1]
    BUSY.add(chat)
    files: list[str] = []
    status = None
    try:
        src = st.get("src", "drc")
        status = await q.message.reply_text(
            f"⏳ ambil info EP {ep} — {esc(it['title'][:60])}…",
            parse_mode=ParseMode.HTML)

        async def set_st(text: str):
            try:
                await status.edit_text(text, parse_mode=ParseMode.HTML)
            except TelegramError as e:
                log.info("edit status dracin dilewati: %s", e)

        if src == "best":
            # ── jalur dracin.best: detail → play → stream → ffmpeg (direct) ──
            dd = st.setdefault("details", {}).get(it["url"])
            if not dd:
                dd = await asyncio.wait_for(scraper_drbest.detail(it["url"]), 40)
                st["details"][it["url"]] = dd
            if ep not in dd.get("play", {}):
                raise RuntimeError(f"EP {ep} nggak ada di judul ini "
                                   f"(total {dd.get('eps', '?')} episode)")
            await set_st(f"⏳ ambil stream EP {ep}…")
            murl = await asyncio.wait_for(
                scraper_drbest.stream_url(dd["play"][ep]), 90)
            safe_base = re.sub(r"[^\w .&+-]", "_",
                               dd.get("title") or it["title"]).strip(" ._")[:60] \
                or "dracin"
            out = str(DL_DIR / f"drb_{safe_base}_ep{ep}.mp4")
            await set_st(f"⬇️ unduh EP {ep} — full episode (ffmpeg)…")
            async with SEM:
                await asyncio.wait_for(
                    scraper_drbest.download(murl, out), MEDIA_TIMEOUT)
            files.append(out)
            size = os.path.getsize(out)
            cap = (f"<b>{esc(dd.get('title') or it['title'])}</b>\n"
                   f"🎬 EP {ep} · full episode · {size / 1048576:.1f} MB · "
                   f"sub Indo · {DR_LABEL['best']}")
            await set_st("⬆️ upload ke Telegram…")
            if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
                parts = await _split_mp4(out, out[:-4], 44 * 1024 * 1024)
                files += parts
                for i, p in enumerate(parts, 1):
                    await set_st(f"⬆️ upload part {i}/{len(parts)}…")
                    await _send_retry(lambda p=p, i=i: context.bot.send_document(
                        chat_id=chat, document=p, filename=os.path.basename(p),
                        caption=f"{cap}\n📦 part {i}/{len(parts)}",
                        parse_mode=ParseMode.HTML, write_timeout=900,
                        read_timeout=180))
            else:
                await _send_retry(lambda: context.bot.send_video(
                    chat_id=chat, video=out, caption=cap, parse_mode=ParseMode.HTML,
                    supports_streaming=True, write_timeout=900, read_timeout=180))
            await set_st(f"✅ selesai — {esc((dd.get('title') or it['title'])[:60])} "
                         f"EP {ep} di atas ☝️")
            log.info("drbest terkirim: %s EP %s (%.1f MB)",
                     (dd.get("title") or it["title"])[:40], ep, size / 1048576)
            _bump("dracin2")
            return

        if src == "candy":
            # ── Candy AI Shorts: MP4 per EP, CDN geo-block → farm proxy ──
            dd = st.setdefault("details", {}).get(it["url"])
            if not dd:
                dd = await asyncio.wait_for(scraper_candy.detail(it["url"]), 40)
                st["details"][it["url"]] = dd
            entry = next((e for e in dd["eps"] if e["n"] == ep), None)
            if entry is None:
                raise RuntimeError(f"EP {ep} nggak ada di judul ini "
                                   f"(total {dd['total']} episode)")
            if not entry["free"] or not entry["url"]:
                gratis = ", ".join(str(e["n"]) for e in dd["eps"] if e["free"])
                await set_st(
                    f"🔒 <b>EP {ep} kena paywall Premium Candy</b>\n"
                    f"EP gratis di judul ini: {gratis} — sisanya premium "
                    f"(gak gua bypass). Coba judul lain: /ai")
                return
            safe_base = (re.sub(r"[^\w .&+-]", "_",
                                dd.get("title") or it["title"]).strip(" ._")[:60]
                         or "candy")
            out = str(DL_DIR / f"candy_{safe_base}_ep{ep}.mp4")
            await set_st(f"⬇️ unduh EP {ep} — CDN geo-block, lewat proxy…")
            async with SEM:
                await asyncio.wait_for(
                    scraper_candy.download(entry["url"], out), MEDIA_TIMEOUT)
            files.append(out)
            size = os.path.getsize(out)
            cap = (f"<b>{esc(dd.get('title') or it['title'])}</b>\n"
                   f"🎬 EP {ep} · {size / 1048576:.1f} MB · AI-generated 18+ · "
                   f"{DR_LABEL['candy']}")
            await set_st("⬆️ upload ke Telegram…")
            if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
                parts = await _split_mp4(out, out[:-4], 44 * 1024 * 1024)
                files += parts
                for i, p in enumerate(parts, 1):
                    await set_st(f"⬆️ upload part {i}/{len(parts)}…")
                    await _send_retry(lambda p=p, i=i: context.bot.send_document(
                        chat_id=chat, document=p, filename=os.path.basename(p),
                        caption=f"{cap}\n📦 part {i}/{len(parts)}",
                        parse_mode=ParseMode.HTML, write_timeout=900,
                        read_timeout=180))
            else:
                await _send_retry(lambda: context.bot.send_video(
                    chat_id=chat, video=out, caption=cap, parse_mode=ParseMode.HTML,
                    supports_streaming=True, write_timeout=900, read_timeout=180))
            await set_st(f"✅ selesai — {esc((dd.get('title') or it['title'])[:60])} "
                         f"EP {ep} di atas ☝️")
            log.info("candy terkirim: %s EP %s (%.1f MB)",
                     (dd.get("title") or it["title"])[:40], ep, size / 1048576)
            _bump("candy")
            return

        if src == "film":
            # ── LK21.dev: segmen HLS → remux → burn sub Indonesia ──
            dd = st.setdefault("details", {}).get(it["url"])
            if not dd:
                dd = await asyncio.wait_for(
                    asyncio.to_thread(scraper_lk21.detail, it["url"]), 40)
                st["details"][it["url"]] = dd
            if not dd.get("embed"):
                raise RuntimeError("film ini nggak punya server streaming")
            safe_base = (re.sub(r"[^\w .&+-]", "_",
                                dd.get("title") or it["title"]).strip(" ._")[:60]
                         or "film")
            out = str(DL_DIR / f"fl_{safe_base}.mp4")
            loop_f = asyncio.get_running_loop()

            def _fprog(done, total):
                # dipanggil dari thread download → lempar ke loop utama
                if total and total <= 1000:
                    if done == 1 or done % 10 == 0 or done == total:
                        txt = (f"⬇️ segmen {done}/{total} "
                               f"({done * 100 // total}%)…")
                        loop_f.call_soon_threadsafe(
                            lambda t=txt: asyncio.ensure_future(set_st(t)))
                elif total:
                    txt = f"⬆️ remux {done / 1048576:.0f} MB…"
                    loop_f.call_soon_threadsafe(
                        lambda t=txt: asyncio.ensure_future(set_st(t)))

            await set_st("⬇️ unduh film penuh — segmen demi segmen…")
            async with SEM:
                # burn sub = re-encode penuh (film 2 jam ± 25 menit di 2 core)
                out2, _dur, has_sub = await asyncio.wait_for(
                    asyncio.to_thread(
                        scraper_lk21.download, it["url"], out, True, _fprog),
                    timeout=7200)
                out = _faststart(out2)
            files.append(out)
            size = os.path.getsize(out)
            cap = (f"<b>{esc(dd.get('title') or it['title'])}</b>\n"
                   f"🎬 film penuh · {size / 1048576:.1f} MB · "
                   f"{DR_LABEL['film']}"
                   + ("\n🇮🇩 sub Indo (burn)" if has_sub
                      else "\n⚠️ sub Indo nggak tersedia"))
            await set_st("⬆️ upload ke Telegram…")
            if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
                parts = await _split_mp4(out, out[:-4], 44 * 1024 * 1024)
                files += parts
                for i, p in enumerate(parts, 1):
                    await set_st(f"⬆️ upload part {i}/{len(parts)}…")
                    await _send_retry(lambda p=p, i=i: context.bot.send_document(
                        chat_id=chat, document=p, filename=os.path.basename(p),
                        caption=f"{cap}\n📦 part {i}/{len(parts)}",
                        parse_mode=ParseMode.HTML, write_timeout=900,
                        read_timeout=180))
            else:
                await _send_retry(lambda: context.bot.send_video(
                    chat_id=chat, video=out, caption=cap,
                    parse_mode=ParseMode.HTML, write_timeout=900,
                    read_timeout=180))
            await set_st("✅ film terkirim")
            _bump("film")
            _lanjut_set(chat, "film", dd.get("title") or it["title"],
                        it["url"])
            return
        if src == "ai2":
            # ── Swaplse AI: mp4 direct di CDN (tanpa resolve) ──────────────
            dd = st.setdefault("details", {}).get(it["url"])
            if not dd:
                dd = await asyncio.wait_for(scraper_ai2.detail(it["url"]), 30)
                st["details"][it["url"]] = dd
            await set_st("⏳ ambil stream…")
            ep_url = dd.get("eps", {}).get(ep) or it["url"]
            murl = await asyncio.wait_for(scraper_ai2.stream_url(ep_url), 45)
            safe_base = (re.sub(r"[^\w .&+-]", "_",
                                dd.get("title") or it["title"]).strip(" ._")[:60]
                         or "ai2")
            out = str(DL_DIR / f"ai2_{safe_base}.mp4")
            await set_st("⬇️ unduh video AI…")
            async with SEM:
                await asyncio.wait_for(
                    scraper_ai2.download(murl, out), MEDIA_TIMEOUT)
            files.append(out)
            out = _faststart(out)
            size = os.path.getsize(out)
            cap = (f"<b>{esc(dd.get('title') or it['title'])}</b>\n"
                   f"🎬 {size / 1048576:.1f} MB · video hentai AI · "
                   f"{DR_LABEL['ai2']} · semua GRATIS")
            await set_st("⬆️ upload ke Telegram…")
            await _send_retry(lambda: context.bot.send_video(
                chat_id=chat, video=out, caption=cap, parse_mode=ParseMode.HTML,
                supports_streaming=True, write_timeout=900, read_timeout=180))
            await set_st(f"✅ selesai — {esc((dd.get('title') or it['title'])[:60])} "
                         f"di atas ☝️")
            log.info("ai2 terkirim: %s (%.1f MB)",
                     (dd.get('title') or it['title'])[:40], size / 1048576)
            _bump("ai2")
            return

        if src == "nh":
            # ── NontonHentai: ep → embed → m3u8 → ffmpeg (semua EP gratis) ──
            dd = st.setdefault("details", {}).get(it["url"])
            if not dd:
                dd = await asyncio.wait_for(scraper_nh.detail(it["url"]), 40)
                st["details"][it["url"]] = dd
            ep_url = dd.get("eps", {}).get(ep)
            if not ep_url:
                raise RuntimeError(f"EP {ep} nggak ada di judul ini "
                                   f"(total {dd.get('total', '?')} episode)")
            await set_st(f"⏳ ambil stream EP {ep}…")
            murl = await asyncio.wait_for(scraper_nh.stream_url(ep_url), 90)
            safe_base = (re.sub(r"[^\w .&+-]", "_",
                                dd.get("title") or it["title"]).strip(" ._")[:60]
                         or "nh")
            out = str(DL_DIR / f"nh_{safe_base}_ep{ep}.mp4")
            await set_st(f"⬇️ unduh EP {ep} — full episode (ffmpeg)…")
            async with SEM:
                await asyncio.wait_for(
                    scraper_nh.download(murl, out), MEDIA_TIMEOUT)
            files.append(out)
            out = _faststart(out)
            size = os.path.getsize(out)
            cap = (f"<b>{esc(dd.get('title') or it['title'])}</b>\n"
                   f"\U0001F3AC EP {ep} \u00b7 {size / 1048576:.1f} MB \u00b7 hentai sub Indo \u00b7 "
                   f"{DR_LABEL['nh']}")
            await set_st("⬆️ upload ke Telegram…")
            if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
                parts = await _split_mp4(out, out[:-4], 44 * 1024 * 1024)
                files += parts
                for i, p in enumerate(parts, 1):
                    await set_st(f"⬆️ upload part {i}/{len(parts)}…")
                    await _send_retry(lambda p=p, i=i: context.bot.send_document(
                        chat_id=chat, document=p, filename=os.path.basename(p),
                        caption=f"{cap}\n📦 part {i}/{len(parts)}",
                        parse_mode=ParseMode.HTML, write_timeout=900,
                        read_timeout=180))
            else:
                await _send_retry(lambda: context.bot.send_video(
                    chat_id=chat, video=out, caption=cap, parse_mode=ParseMode.HTML,
                    supports_streaming=True, write_timeout=900, read_timeout=180))
            await set_st(f"✅ selesai — {esc((dd.get('title') or it['title'])[:60])} "
                         f"EP {ep} di atas ☝️")
            log.info("nh terkirim: %s EP %s (%.1f MB)",
                     (dd.get("title") or it["title"])[:40], ep, size / 1048576)
            _bump("hvid")
            return

        key = scraper_dracin.movie_key(it["url"])
        d = await asyncio.wait_for(scraper_dracin.playback(key, ep), 45)
        if d.get("kind") != "ok":
            await set_st(
                f"🔒 <b>EP {ep} butuh login akun dracinema</b>\n"
                f"drasinema kasih EP 1-5 gratis; EP {ep} dibatesin akun "
                f"(daftarnya ada captcha — daftar manual dulu kalo mau).")
            return
        vurls = (d.get("data") or {}).get("detail", {}).get("videoUrls") or []
        if not vurls:
            raise RuntimeError("videoUrls kosong dari server")

        # ukuran tiap kualitas via HEAD (CDN direct, cepat)
        sizes: dict[str, int] = {}

        async def head(v: dict):
            try:
                async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                             verify=False) as c:
                    r = await c.head(v["url"])
                    sizes[v["url"]] = int(r.headers.get("content-length") or 0)
            except Exception:
                sizes[v["url"]] = 0
        await asyncio.gather(*(head(v) for v in vurls))

        # pilih: kualitas TERTINGGI yang muat limit upload; kalau nggak ada →
        # kualitas TERKECIL (nanti dipecah jadi part)
        muat = [v for v in vurls if 0 < sizes.get(v["url"], 0) <= TG_UPLOAD_LIMIT]
        if muat:
            pick = max(muat, key=lambda v: v.get("quality") or 0)
            split_mode = False
        else:
            pick = min(vurls, key=lambda v: sizes.get(v["url"]) or 1 << 62)
            split_mode = True
        quality = pick.get("quality") or "?"
        await set_st(f"⬇️ unduh {quality}p EP {ep}…")

        loop = asyncio.get_running_loop()
        state = {"last": 0.0, "pct": -1}
        sz0 = sizes.get(pick["url"]) or 0

        def progress(done: int, total: Optional[int]):
            total = total or sz0
            if total <= 0:
                return
            pct = int(done * 100 / total)
            now = time.monotonic()
            if pct == state["pct"]:
                return
            if pct < 100 and now - state["last"] < 2.5:
                return
            state["pct"] = pct
            state["last"] = now
            asyncio.run_coroutine_threadsafe(
                set_st(f"⬇️ unduh {quality}p EP {ep} — {pct}% "
                       f"({done / 1048576:.1f}/{total / 1048576:.1f} MB)"), loop)

        safe_base = re.sub(r"[^\w .&+-]", "_", it["title"]).strip(" ._")[:60] or "dracin"
        out = str(DL_DIR / f"dr_{safe_base}_ep{ep}.mp4")
        async with SEM:
            await asyncio.wait_for(
                scraper_dracin.download_mp4(pick["url"], out, progress,
                                            max_bytes=(TG_UPLOAD_LIMIT + 1024 * 1024)
                                            if split_mode else None),
                MEDIA_TIMEOUT)
        files.append(out)
        out = _faststart(out)
        if 48 * 1048576 < os.path.getsize(out) <= 200 * 1048576:
            out = _shrink(out, 46 * 1048576)
        size = os.path.getsize(out)
        cap = (f"<b>{esc(it['title'])}</b>\n🎬 EP {ep} · {quality}p · "
               f"{size / 1048576:.1f} MB · sub Indo")

        await set_st("⬆️ upload ke Telegram…")
        if size > TG_UPLOAD_LIMIT and not os.environ.get("TBAS_URL", "").strip():
            # pecah jadi part yang muat
            parts = await _split_mp4(out, str(DL_DIR / f"dr_{safe_base}_ep{ep}"),
                                     44 * 1024 * 1024)
            files += parts
            for i, p in enumerate(parts, 1):
                await set_st(f"⬆️ upload part {i}/{len(parts)}…")
                await _send_retry(lambda p=p, i=i: context.bot.send_document(
                    chat_id=chat, document=p,
                    filename=os.path.basename(p),
                    caption=f"{cap}\n📦 part {i}/{len(parts)}",
                    parse_mode=ParseMode.HTML, write_timeout=900, read_timeout=180))
        else:
            await _send_retry(lambda: context.bot.send_video(
                chat_id=chat, video=out, caption=cap, parse_mode=ParseMode.HTML,
                supports_streaming=True, write_timeout=900, read_timeout=180))
        await set_st(f"✅ selesai — {esc(it['title'][:60])} EP {ep} di atas ☝️")
        log.info("dracin terkirim: %s EP %s (%s, %.1f MB)",
                 it["title"][:40], ep, quality, size / 1048576)
        _bump("dracin")
        _lanjut_set(chat, "dracin", it["title"], it["url"], ep)
    except Exception as e:
        log.exception("dracin download gagal")
        try:
            await (status or q.message).edit_text(
                f"❌ gagal: {esc(str(e))[:300]}", parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
    finally:
        BUSY.discard(chat)
        for f in files:
            try:
                if f and os.path.isfile(f):
                    os.remove(f)
            except OSError:
                pass


async def h_cb_d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data or ""
    parts = data.split("|")
    kind = parts[0]
    qid = parts[1] if len(parts) > 1 else ""
    try:
        num = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        num = 0
    if kind == "drs":
        await d_goto_page(update, qid, num)
    elif kind == "mf":
        # ✅ selesai — satu callback dipakai 2 dunia: deteksi state-nya siapa
        st_m = _state_m(qid)
        if st_m is not None:
            await m_finish(update, context, qid, num, st=st_m,
                           msg="✅ selesai baca — mantap!")
        else:
            # kartu detail dracin: hapus kartu, rapi
            await m_finish(update, context, qid, num, st=_state_d(qid),
                           msg="✅ selesai ditonton — kartu ditutup!")
    elif kind == "drg":
        # toggle sumber: dracinema ⇄ dracin.best (re-search query sama)
        st = _state_d(qid)
        if not st:
            await update.callback_query.answer("hasil sudah basi — /dracin lagi",
                                               show_alert=True)
            return
        new_src = _dr_next(st.get("src", "drc"))
        await update.callback_query.answer(f"🔁 pindah ke {DR_LABEL[new_src]}…")
        try:
            items, total = await asyncio.to_thread(
                _dr_search, new_src, st["q"], 1)
        except Exception as e:
            log.exception("ganti sumber dracin gagal")
            try:
                await update.callback_query.message.reply_text(
                    f"❌ gagal: {esc(str(e))[:160]}", parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
            return
        st.update(src=new_src, page=1, items=items, total=total, details={},
                  eps={})
        text, kb = render_dlist(st, qid)
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError as e:
            log.warning("edit list (ganti sumber) gagal: %s", e)
    elif kind == "drk":
        await d_detail(update, qid, num)
    elif kind == "drp":
        st = _state_d(qid)
        if not st or not (1 <= num <= len(st["items"])):
            await update.callback_query.answer("hasil sudah basi — /dracin lagi",
                                               show_alert=True)
            return
        e0, e1 = st.get("eps", {}).get(num, scraper_dracin.eps_range(
            st["items"][num - 1].get("desc") or ""))
        ep_page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
        try:
            await update.callback_query.edit_message_reply_markup(
                d_eps_kb(qid, num, ep_page, e0, e1, st["items"][num - 1]["url"]))
            await update.callback_query.answer()
        except TelegramError as e:
            log.warning("edit keyboard episode gagal: %s", e)
            await update.callback_query.answer("❗ pesan basi — buka ulang dari daftar")
    elif kind == "drd":
        ep = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
        await d_download(update, context, qid, num, ep)
    else:
        await update.callback_query.answer()


_ERR_TS: "deque[float]" = __import__("collections").deque()


async def _notify_owner_err(context, text: str):
    """Kirim error ke owner (maks 5/menit biar gak spam)."""
    now = time.time()
    while _ERR_TS and now - _ERR_TS[0] > 60:
        _ERR_TS.popleft()
    if len(_ERR_TS) >= 5:
        return
    _ERR_TS.append(now)
    try:
        await context.bot.send_message(
            OWNER_ID, f"⚠️ <b>bot error</b>\n{esc(text[:400])}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


async def h_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("handler error", exc_info=context.error)
    if context.error is not None:
        await _notify_owner_err(context, str(context.error))


# ── PERSISTENSI STATE — sesi baca/nonton selamat dari restart/deploy ───────
# Penyebab "hasil sudah basi" nomor 1: bot di-restart (deploy) → semua state
# RAM hilang → tombol lama mati. State di-dump tiap 20 detik + saat shutdown,
# dipulihkan lagi waktu boot.
STATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "states.pkl")


def _dumpable(d: dict) -> dict:
    """Filter state yang nggak bisa di-pickle (objek lokal/singgahan) —
    satu state busuk nggak boleh bikin seluruh dump gagal."""
    out = {}
    for k, v in d.items():
        try:
            pickle.dumps(v)
            out[k] = v
        except Exception:
            log.debug("state %s nggak picklable — dilewati", k)
    return out


def _save_states() -> None:
    try:
        tmp = STATES_FILE + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump({"STATES": _dumpable(STATES),
                         "STATES_M": _dumpable(STATES_M),
                         "STATES_D": _dumpable(STATES_D),
                         "LAST": _dumpable(LAST)},
                        f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, STATES_FILE)
    except Exception as e:
        log.debug("simpan state gagal: %s", e)


def _load_states() -> None:
    try:
        with open(STATES_FILE, "rb") as f:
            d = pickle.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        # format lama / korup — mulai segar, jangan pernah gagal boot
        log.warning("state lama nggak bisa dibaca (mulai segar): %s", e)
        return
    try:
        STATES.update(d.get("STATES") or {})
        STATES_M.update(d.get("STATES_M") or {})
        STATES_D.update(d.get("STATES_D") or {})
        LAST.update(d.get("LAST") or {})
        if STATES or STATES_M or STATES_D:
            log.info("state lama dipulihkan: cari=%d manhwa=%d dracin=%d",
                     len(STATES), len(STATES_M), len(STATES_D))
    except Exception as e:
        log.warning("pulihkan state gagal (abaikan): %s", e)


async def _saver_loop(app: Application):
    """Dump state berkala — restart/deploy nggak bikin tombol basi lagi."""
    await asyncio.sleep(20)
    while True:
        _save_states()
        await asyncio.sleep(20)


async def post_shutdown(app: Application):
    _save_states()


async def post_init(app: Application):
    # NB: builder post_init cuma 1 slot — _cleanup_dl_startup dipanggil DI SINI
    # (dulu dipanggil via app_builder.post_init() kedua → menimpa post_init ini,
    #  jadi set_my_commands + login sukses + load states gak pernah jalan)
    await _cleanup_dl_startup(app)
    await app.bot.set_my_commands([
        ("start", "bantuan"),
        ("cari", "cari video: /cari judul"),
        ("hentai", "cari video hentai"),
        ("manhwa", "manhwa/doujin (semua bahasa)"),
        ("manhwaid", "doujin bahasa Indonesia"),
        ("dracin", "drama China sub Indo: /dracin judul"),
        ("dracin2", "dracin.best full episode: /dracin2 judul"),
        ("ai", "seri porno AI (Candy): /ai judul"),
        ("hvid", "hentai sub Indo: /hvid judul"),
        ("film", "film & series gratis (LK21): /film judul"),
        ("komik", "komik doujin Indonesia: /komik judul"),
        ("ai2", "video AI 18+ gratis tanpa login: /ai2 judul"),
        ("cn", "video amatir China 91porny: /cn [kata]"),
        ("china", "video China/Madou (JavDB): /china [kata]"),
    ])
    me = await app.bot.get_me()
    log.info("login sukses: @%s (id=%s)", me.username, me.id)
    # pulihkan sesi lama + mulai penyimpan berkala
    _load_states()
    app.create_task(_saver_loop(app))


async def _cleanup_dl_startup(app=None):
    """Bersihin sisa file download pas bot start (crash/restart sebelum
    finally jalan = file nyisa, disk melar). File < 6 jam dibiarkan."""
    import time as _t
    now = _t.time()
    n = sz = 0
    try:
        for name in os.listdir(DL_DIR):
            p = os.path.join(DL_DIR, name)
            if os.path.isfile(p) and now - os.path.getmtime(p) > 6 * 3600:
                sz += os.path.getsize(p)
                os.remove(p)
                n += 1
    except OSError:
        pass
    if n:
        log.info("startup cleanup: %d file sisa (%.1f MB) dihapus",
                 n, sz / 1048576)


def build_app() -> Application:
    """Susun Application + semua handler. Dipisah dari main() supaya test
    harness bisa validasi registrasi command SEBELUM bot jalan."""
    # timeout lebih longgar dari default PTB (5s) — upload foto/video suka lebih
    from telegram.request import HTTPXRequest
    req = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=300,
                       pool_timeout=30)
    app_builder = (Application.builder().token(TOKEN)
                   .request(req)
                   .concurrent_updates(4)
                   .post_init(post_init)
                   .post_shutdown(post_shutdown))
    # Local Bot API Server (limit upload 2GB) — aktif kalau TBAS_URL di-set, mis.
    # TBAS_URL=http://127.0.0.1:8081 di .env / unit systemd
    local_api = os.environ.get("TBAS_URL", "").strip()
    if local_api:
        app_builder = app_builder.base_url(f"{local_api.rstrip('/')}/bot{TOKEN}/")
        log.info("pakai Local Bot API: %s", local_api)
    # NB: JANGAN app_builder.post_init() lagi di sini — builder punya 1 slot,
    # panggilan kedua menimpa post_init (lihat catatan di post_init).
    app = app_builder.build()
    app.add_handler(CommandHandler(["start", "help"], h_start))
    app.add_handler(CommandHandler(["cari", "search"], h_search))
    app.add_handler(CommandHandler(["amatir", "china_amatir"], h_amatir))
    app.add_handler(CommandHandler(["hentai"], h_hentai))
    app.add_handler(CommandHandler(["manhwa"], h_manhwa))
    # NB: nama command Telegram hanya [a-zA-Z0-9_] — tanpa tanda hubung
    app.add_handler(CommandHandler(["manhwaid"], h_manhwa_id))
    app.add_handler(CommandHandler(["dracin"], h_dracin))
    app.add_handler(CommandHandler(["dracin2"], h_dracin2))
    app.add_handler(CommandHandler(["ai"], h_ai))
    app.add_handler(CommandHandler(["hvid"], h_hvid))
    app.add_handler(CommandHandler(["film"], h_film))
    app.add_handler(CommandHandler(["komik"], h_komik))
    app.add_handler(CommandHandler(["ai2"], h_ai2))
    app.add_handler(CommandHandler(["aiv"], h_aiv))
    app.add_handler(CommandHandler(["stat"], h_stat))
    app.add_handler(CommandHandler(["acak", "random"], h_acak))
    app.add_handler(CommandHandler(["hemat"], h_hemat))
    app.add_handler(CommandHandler(["koleksi", "fav"], h_koleksi))
    app.add_handler(CommandHandler(["lanjut"], h_lanjut))
    app.add_handler(CommandHandler("aiv", h_aiv))
    app.add_handler(CallbackQueryHandler(h_aiv_cb, pattern=r"^aiv\|"))
    app.add_handler(CommandHandler("series", h_series))
    app.add_handler(CallbackQueryHandler(h_series_cb, pattern=r"^srs\|"))
    app.add_handler(CommandHandler("gen", h_gen))
    app.add_handler(CommandHandler("mdx", h_mdx))
    app.add_handler(CallbackQueryHandler(h_mdx_cb, pattern=r"^mdx\|"))
    app.add_handler(CallbackQueryHandler(h_mdx_read, pattern=r"^mdx[rp]\|"))
    app.add_handler(CommandHandler("ptx", h_ptx))
    app.add_handler(CallbackQueryHandler(h_ptx_cb, pattern=r"^ptx[r]?\|"))
    app.add_handler(CommandHandler("anime", h_anime))
    app.add_handler(CommandHandler("meme", h_meme))
    app.add_handler(CommandHandler("wsg", h_wsg))
    app.add_handler(CommandHandler("jelajah", h_jelajah))
    app.add_handler(CommandHandler("browse", h_jelajah))
    app.add_handler(CallbackQueryHandler(h_jel_cb, pattern=r"^jel\|"))
    app.add_handler(CallbackQueryHandler(h_jelani_cb, pattern=r"^jelani\|"))
    app.add_handler(CommandHandler("jav", h_jav))
    app.add_handler(CommandHandler("china", h_china))
    app.add_handler(CommandHandler("cn", h_cn))
    app.add_handler(CallbackQueryHandler(h_cn_cb, pattern=r"^cn[a-z]*\|"))
    app.add_handler(CallbackQueryHandler(h_jav_cb, pattern=r"^jv[a-z]*\|"))
    app.add_handler(CommandHandler("r34", h_r34))
    app.add_handler(CallbackQueryHandler(h_r34_cb, pattern=r"^r34r\|"))
    app.add_handler(CallbackQueryHandler(h_koleksi_cb, pattern=r"^(kh|kdl)\|"))
    app.add_handler(CallbackQueryHandler(h_acak_cb, pattern=r"^acak_lagi\|"))
    app.add_handler(CallbackQueryHandler(h_aiv_cb, pattern=r"^aiv\|"))
    app.add_handler(CallbackQueryHandler(h_aiv_dl, pattern=r"^aivd\|"))
    app.add_handler(CallbackQueryHandler(h_aiv_nav, pattern=r"^aiv(n|b|r)"))
    app.add_handler(CommandHandler(["admin"], h_admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h_text))
    app.add_handler(CallbackQueryHandler(h_menu, pattern=r"^mn\|"))
    app.add_handler(CallbackQueryHandler(h_cb, pattern=r"^(v|n|d|b|p|k|s|noop)\|"))
    app.add_handler(CallbackQueryHandler(h_cb_m, pattern=r"^(mo|mv|mp|m10|mz|mb|mr|ms)\|"))
    app.add_handler(CallbackQueryHandler(h_cb_d, pattern=r"^(drs|drk|drp|drd|drg|mf)\|"))
    app.add_error_handler(h_error)
    # ── allowlist gate: semua handler dibungkus (kecuali sudah ke-wrap) ──
    for _grp in app.handlers.values():
        for _h in _grp:
            _cb = getattr(_h, "callback", None)
            if _cb is not None and not getattr(_cb, "_gate", False):
                _h.callback = _protect(_cb)
    return app


def main():
    DL_DIR.mkdir(exist_ok=True)
    for p in DL_DIR.iterdir():
        try:
            if p.is_file() and time.time() - p.stat().st_mtime > 7200:
                p.unlink()
        except OSError:
            pass
    app = build_app()
    log.info("bot mulai polling…")
    import asyncio as _aio

    _orig_init = app.post_init

    async def _init_with_loop(a):
        if _orig_init is not None:
            await _orig_init(a)
        _aio.get_event_loop().create_task(_sub_loop(a))

    app.post_init = _init_with_loop
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
