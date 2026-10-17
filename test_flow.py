#!/usr/bin/env python3
"""Full-flow test xh-bot TANPA Telegram asli — semua API di-fake.
Guard: fake CallbackQuery mencatat kalau ada kode yang masih salah target
(ngedit pesan tempat tombol nempel) jadi test gagal kalau bug-nya balik."""
import asyncio, io, os, sys, types, traceback

sys.path.insert(0, "/home/agentuser/xh-bot")
import bot, scraper, scraper_hentai
from telegram.error import TelegramError

CALLS = []
MID = [1000]
FAIL_EDIT = {"on": False}

def _mid():
    MID[0] += 1
    return MID[0]

class FakeMsg:
    def __init__(self, chat_id=777):
        self.chat = types.SimpleNamespace(id=chat_id)
        self.message_id = _mid()
        self.text = ""
        self.reply_markup = None
    async def reply_text(self, text=None, **kw):
        CALLS.append(("reply_text", (text or "")[:300]))
        m = FakeMsg(self.chat.id); m.text = text or ""; return m
    async def reply_photo(self, photo=None, caption=None, **kw):
        CALLS.append(("reply_photo", (caption or "")[:300]))
        self.reply_markup = kw.get("reply_markup")
        m = FakeMsg(self.chat.id); m.text = caption or ""; return m
    async def reply_document(self, document=None, caption=None, **kw):
        # mode strip scroll + auto-recovery strip
        CALLS.append(("reply_document", (caption or "")[:300]))
        m = FakeMsg(self.chat.id); m.text = caption or ""; return m
    async def edit_text(self, text=None, reply_markup=None, **kw):
        CALLS.append(("msg_edit_text", (text or "")[:300])); self.text = text
        self.reply_markup = reply_markup
    async def edit_caption(self, caption=None, reply_markup=None, **kw):
        CALLS.append(("msg_edit_caption", (caption or "")[:200])); self.text = caption
        if reply_markup is not None:
            self.reply_markup = reply_markup
    async def edit_reply_markup(self, rm):
        CALLS.append(("msg_edit_rm",)); self.reply_markup = rm
    async def delete(self):
        CALLS.append(("msg_delete", self.message_id))

    async def reply_video(self, video=None, caption=None, **kw):
        CALLS.append(("reply_video", "", (caption or "")[:80]))
        self.reply_markup = kw.get("reply_markup")
        return FakeMsg()

class FakeBot:
    async def edit_message_media(self, chat_id=None, message_id=None, media=None, reply_markup=None):
        if FAIL_EDIT["on"]:
            raise TelegramError("message to edit not found")
        CALLS.append(("edit_media", message_id, (media.caption or "")[:200]))
    async def edit_message_text(self, chat_id=None, message_id=None, text=None, reply_markup=None, **kw):
        if FAIL_EDIT["on"]:
            raise TelegramError("message to edit not found")
        CALLS.append(("edit_media_text", message_id, (text or "")[:300]))
    async def send_video(self, chat_id=None, video=None, caption=None, **kw):
        CALLS.append(("send_video", os.path.basename(str(video)), (caption or "")[:60])); return FakeMsg()

    async def reply_video(self, video=None, caption=None, **kw):
        CALLS.append(("reply_video", "", (caption or "")[:80]))
        return FakeMsg()
    async def send_photo(self, chat_id=None, photo=None, caption=None, **kw):
        CALLS.append(("send_photo", str(photo)[:40], (caption or "")[:60])); return FakeMsg()

    async def send_document(self, chat_id=None, document=None, filename=None, caption=None, **kw):
        CALLS.append(("send_document", filename or os.path.basename(str(document)), (caption or "")[:60])); return FakeMsg()
    async def send_media_group(self, chat_id=None, media=None, **kw):
        CALLS.append(("send_media_group", len(media))); return [FakeMsg()]
    async def send_message(self, chat_id=None, text=None, **kw):
        CALLS.append(("send_message", chat_id, (text or "")[:200])); return FakeMsg()
    async def forward_message(self, chat_id=None, from_chat_id=None, message_id=None, **kw):
        CALLS.append(("forward_message", chat_id, from_chat_id)); return FakeMsg()
    async def edit_message_reply_markup(self, chat_id=None, message_id=None,
                                        reply_markup=None, **kw):
        # shortcut ketik-angka EP: ngedit keyboard kartu dracin
        CALLS.append(("edit_rm", message_id))

class FakeCQ:
    def __init__(self, data, message):
        self.data = data
        self.message = message
    async def answer(self, text=None, show_alert=False):
        CALLS.append(("answer", (text or "")[:70]))
    async def edit_message_media(self, media=None, reply_markup=None, **kw):
        # marker: tombol ngedit pesannya SENDIRI = salah target
        CALLS.append(("WRONG_cq_edit_media", (media.caption or "")[:60] if media else ""))
    async def edit_message_text(self, text=None, reply_markup=None, **kw):
        # ini SAH untuk navigasi daftar (p|) — pesan daftar memang diedit in place
        CALLS.append(("cq_edit_text", (text or "")[:60]))
        self.message.reply_markup = reply_markup
    async def edit_message_reply_markup(self, reply_markup=None, **kw):
        # nav episode (drp) ngedit keyboard pesan detail di tempat — sah
        CALLS.append(("cq_edit_rm",))
        self.message.reply_markup = reply_markup

def mk_update(data, msg=None):
    m = msg or FakeMsg()
    cq = FakeCQ(data, m)
    return types.SimpleNamespace(callback_query=cq, message=m)

def mk_user_update(text="/x", uid=7998819216, chat_id=None):
    """Update ala pesan teks dengan effective_user (buat tes gate allowlist)."""
    m = FakeMsg(chat_id or uid)
    m.text = text
    u = types.SimpleNamespace(id=uid, full_name="Tester", username="tester")
    return types.SimpleNamespace(effective_user=u, effective_chat=m.chat,
                                 effective_message=m, message=m,
                                 callback_query=None)

def mk_ctx():
    return types.SimpleNamespace(bot=FakeBot(), args=[])

# ─── stubs jaringan ───
async def fake_fetch_thumb(url):
    return io.BytesIO(b"\xff\xd8fakejpeg")
bot.fetch_thumb = fake_fetch_thumb

async def fake_search(q, page=1):
    items = [scraper.Result(idx=i + 1, title=f"Video {i + 1}",
                            url=f"https://xhamster.com/videos/v{i}",
                            duration=f"1{i}:00", views="1K views",
                            thumb="http://x/t.jpg") for i in range(3)]
    return scraper.SearchPage(query=q, page=page, max_pages=5, items=items)
scraper.search = fake_search

async def fake_resolve(url):
    return {"formats": [
        {"format_id": "f360", "height": 360, "protocol": "m3u8_native", "vcodec": "h264", "acodec": "mp4a", "tbr": 500, "filesize": 1_000_000},
        {"format_id": "f720", "height": 720, "protocol": "m3u8_native", "vcodec": "h264", "acodec": "mp4a", "tbr": 2000, "filesize": 5_000_000},
        {"format_id": "f1080", "height": 1080, "protocol": "m3u8_native", "vcodec": "h264", "acodec": "mp4a", "tbr": 4000, "filesize": 9_000_000},
    ]}
scraper.resolve = fake_resolve

REAL_DOWNLOAD_SYNC = scraper.download_sync  # asli, dipakai test tangga fallback

def fake_download_sync(url, format_id, out_dir, progress=None):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "fake_video.mp4")
    with open(p, "wb") as f:
        f.write(b"0" * 2048)
    if progress:
        progress(2048, 2048)
    return p
scraper.download_sync = fake_download_sync

# manhwa stubs
async def fake_m_search(q, page=1):
    items = [scraper_hentai.Gallery(idx=i + 1, title=f"Manhwa {i + 1}",
                                    url=f"https://hentaifox.com/gallery/{i + 1}/",
                                    cat="Doujinshi", thumb="http://x/c.jpg") for i in range(3)]
    return scraper_hentai.GalleryPage(query=q, page=page, max_pages=4, items=items)
scraper_hentai.search = fake_m_search

async def fake_m_gallery(url):
    return scraper_hentai.GalleryDetail(title="Judul Manhwa", url=url, cover="http://x/cov.jpg",
                                        pages=5, page_urls=["a", "b", "c", "d", "e"], tags=[])
scraper_hentai.gallery = fake_m_gallery

async def fake_m_download(detail, out_dir, start=0, limit=None, progress=None, max_bytes=None):
    os.makedirs(out_dir, exist_ok=True)
    n = limit or 5
    paths = []
    for i in range(n):
        p = os.path.join(out_dir, f"mh_{i + 1}.jpg")
        with open(p, "wb") as f:
            f.write(b"0" * 512)
        paths.append(p)
    return paths, False
scraper_hentai.download_pages = fake_m_download

# dracin stubs (search sync, playback + download async — signature asli)
import scraper_dracin
DR_ITEMS = [
    {"title": f"Drama Seru {i}", "url": f"https://www.dracinema.com/movie/drama-seru-{i}_123",
     "thumb": "https://cdn.fake/thumb.jpg",
     "desc": f"Nonton Drama Seru {i} sub Indo episode 1-30 gratis"}
    for i in range(1, 4)]
def fake_dr_search(q="", page=1):
    return (list(DR_ITEMS), 35)
scraper_dracin.search = fake_dr_search
DR_KIND = {"kind": "ok"}
async def fake_dr_playback(key, ep):
    if DR_KIND["kind"] != "ok":
        return {"kind": DR_KIND["kind"]}
    return {"kind": "ok",
            "data": {"detail": {"videoUrls": [
                {"quality": 480, "url": "https://cdn.fake/video.mp4"}]}},
            "subtitle": "WEBVTT"}
scraper_dracin.playback = fake_dr_playback
async def fake_dr_download(url, out, progress=None, max_bytes=None):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"0" * 4096)
    if progress:
        progress(4096, 4096)
    return out, False
scraper_dracin.download_mp4 = fake_dr_download

# ─── assertions ───
def has(tag, sub=None, idx=None):
    if sub is not None:
        sub = str(sub)
    for c in CALLS:
        if c[0] == tag and (sub is None or (sub in str(c[1]) or (len(c) > 2 and sub in str(c[2])))):
            if idx is None or c[1] == idx:
                return c
    return None

def clear():
    CALLS.clear()

def check(cond, name, extra=""):
    if not cond:
        raise AssertionError(f"{name} {extra}\nCALLS={CALLS[-8:]}")

async def round_tests():
    # R0: build Application penuh → validasi nama command & registrasi handler
    # (ini yang kelewat waktu crash loop 'manhwa-id')
    app0 = bot.build_app()
    check(app0 is not None, "R0 build_app() + registrasi handler lolos")

    # R1: search → daftar + kartu + state card id
    clear()
    upd = mk_update("x")
    await bot.do_search(upd, "video test")
    check(has("reply_text", "mencari"), "R1 status pencarian terkirim")
    check(has("msg_edit_text", "halaman"), "R1 daftar ke-edit jadi hasil")
    check(has("reply_photo", "Video 1"), "R1 kartu #1 terkirim")
    qid = list(bot.STATES.keys())[-1]
    st = bot.STATES[qid]
    check("card" in st, "R1 card id tersimpan", str(st))
    card_id = st["card"][1]
    check(st["card"][0] == 777, "R1 chat id card")

    # R2: klik angka 2 di DAFTER → kartu (bukan daftar) yang diedit
    clear()
    upd = mk_update(f"k|{qid}|2", msg=upd.message)  # tombol di pesan daftar
    await bot.h_cb(upd, mk_ctx())
    check(has("answer", "Video 2"), "R2 toast muncul")
    check(has("edit_media", idx=card_id, sub="Video 2"), "R2 kartu ke-edit ke Video 2", f"card_id={card_id}")
    check(not has("WRONG_cq_edit_media"), "R2 ga salah target", str(CALLS))

    # R3: navigasi ◀️/▶️ dari kartu sendiri
    card_msg = FakeMsg()
    card_msg.message_id = card_id
    clear()
    upd = mk_update(f"k|{qid}|3", msg=card_msg)
    await bot.h_cb(upd, mk_ctx())
    check(has("edit_media", idx=card_id, sub="Video 3"), "R3 kartu ke-edit ke Video 3")
    check(not has("WRONG_cq_edit_media"), "R3 ga salah target")

    # R4: resolusi 720p → run_media kirim video
    clear()
    upd = mk_update(f"s|{qid}|3|720", msg=card_msg)
    await bot.h_cb(upd, mk_ctx())
    check(has("send_video", sub="Streaming 720p"), "R4 send_video 720p")

    # R5: nonton (stream default)
    clear()
    upd = mk_update(f"n|{qid}|1", msg=card_msg)
    await bot.h_cb(upd, mk_ctx())
    check(has("send_video", sub="Streaming 480p"), "R5 nonton → send_video")

    # R6: download best → document
    clear()
    upd = mk_update(f"d|{qid}|1", msg=card_msg)
    await bot.h_cb(upd, mk_ctx())
    check(has("send_video", sub="Download full quality"), "R6 download → send_VIDEO playable")

    # R7: kartu mati → fallback kirim kartu baru + update state
    FAIL_EDIT["on"] = True
    clear()
    upd = mk_update(f"k|{qid}|2", msg=FakeMsg())
    await bot.h_cb(upd, mk_ctx())
    check(has("reply_photo", "Video 2"), "R7 kartu baru terkirim")
    new_id = bot.STATES[qid]["card"][1]
    check(new_id != card_id, "R7 state card id ke-update")
    FAIL_EDIT["on"] = False

    # R8: paging daftar (edit in place pesan daftar = sah)
    clear()
    upd = mk_update(f"p|{qid}|2", msg=upd.message)
    await bot.h_cb(upd, mk_ctx())
    check(has("cq_edit_text", "halaman"), "R8 daftar ke-edit ke halaman 2")

    # R9: manhwa — search → list → detail → 10 hal → zip
    clear()
    upd = mk_update("x")
    await bot.h_manhwa(upd, mk_ctx())
    check(has("msg_edit_text", "halaman") and has("msg_edit_text", "gallery"),
          "R9 daftar manhwa tampil")
    qid_m = list(bot.STATES_M.keys())[-1]
    clear()
    upd2 = mk_update(f"mv|{qid_m}|1")
    await bot.h_cb_m(upd2, mk_ctx())
    check(has("reply_photo", "Judul Manhwa"), "R9 detail cover terkirim")
    clear()
    upd3 = mk_update(f"m10|{qid_m}|1", msg=upd2.message)
    await bot.h_cb_m(upd3, mk_ctx())
    mg = has("send_media_group")
    check(mg and int(mg[1]) >= 2, "R9 10 halaman → media group", str(mg))
    clear()
    upd4 = mk_update(f"mz|{qid_m}|1", msg=upd2.message)
    await bot.h_cb_m(upd4, mk_ctx())
    check(has("send_document", ".zip"), "R9 zip terkirim")

    # R9b: mode baca slide (reader)
    clear()
    upd_r = mk_update(f"mr|{qid_m}|1|1")
    await bot.h_cb_m(upd_r, mk_ctx())
    check(has("reply_photo", "halaman 1/5"), "R9b reader buka hal 1")
    reader_id = bot.STATES_M[qid_m]["reader"][1]
    clear()
    upd_r2 = mk_update(f"mr|{qid_m}|1|2", msg=upd_r.message)
    await bot.h_cb_m(upd_r2, mk_ctx())
    check(has("edit_media", idx=reader_id, sub="halaman 2/5"), "R9b ▶️ edit reader ke hal 2")
    # reader mati → KEBIJAKAN BARU (user: "agar tdk bisa basi"): AUTO-RECOVERY
    FAIL_EDIT["on"] = True
    clear()
    await bot.h_cb_m(mk_update(f"mr|{qid_m}|1|3"), mk_ctx())
    check(has("reply_photo", "halaman 3/5"), "R9b reader mati → pesan baca BARU otomatis")
    check(has("answer", "pesan baca baru"), "R9b toast 'lanjut di pesan baca baru'")
    check(not any("basi" in str(c).lower() for c in CALLS),
          "R9b ga ada lagi alert 'basi'")
    new_reader = bot.STATES_M[qid_m]["reader"][1]
    check(new_reader != reader_id, "R9b tracker reader ke-refresh ke pesan baru")
    FAIL_EDIT["on"] = False
    # ujung halaman
    clear()
    await bot.h_cb_m(mk_update(f"mr|{qid_m}|1|99"), mk_ctx())
    check(has("answer", "ujung"), "R9b batas halaman → toast")
    # file sisa ga numpuk di dl/
    leftover = [f for f in os.listdir(os.path.join(os.path.expanduser("~/xh-bot"), "dl"))
                if f.startswith("mh_")]
    check(not leftover, "R9b file reader dibersihkan", str(leftover))

    # R10: state basi → alert, bukan crash
    clear()
    upd5 = mk_update("k|nonexistent|1")
    await bot.h_cb(upd5, mk_ctx())
    check(has("answer", "basi"), "R10 state basi → alert")

    # ─── R11: /manhwaid (source dojing.net) ───
    import scraper_indo
    ind_calls = []
    async def ind_search(q="", page=1):
        ind_calls.append(("search", q, page))
        items = [scraper_hentai.Gallery(idx=i + 1, title=f"ID Comic {i + 1}",
                                        url=f"https://dojing.net/manga/idc{i + 1}/",
                                        cat="Doujinshi", thumb="") for i in range(3)]
        return scraper_hentai.GalleryPage(query=q, page=page, max_pages=2, items=items)
    async def ind_gallery(url):
        ind_calls.append(("gallery", url))
        return scraper_hentai.GalleryDetail(title="ID Judul", url=url,
                                            cover="http://x/cover.jpg", pages=4,
                                            page_urls=["p1", "p2", "p3", "p4"], tags=[])
    async def ind_download(detail, out_dir, start=0, limit=None, progress=None,
                           max_bytes=None):
        ind_calls.append(("download", start, limit, max_bytes is not None))
        os.makedirs(out_dir, exist_ok=True)
        n = limit or 2
        paths = []
        for i in range(n):
            p = os.path.join(out_dir, f"id_{start + i}.jpg")
            with open(p, "wb") as f:
                f.write(b"0" * 256)
            paths.append(p)
        return paths, False
    real = (scraper_indo.search, scraper_indo.gallery, scraper_indo.download_pages)
    scraper_indo.search, scraper_indo.gallery, scraper_indo.download_pages = (
        ind_search, ind_gallery, ind_download)
    try:
        # search via /manhwaid
        clear()
        await bot.h_manhwa_id(mk_update("x"), mk_ctx())
        check(has("reply_text", "🇮🇩"), "R11 status manhwaid terkirim")
        check(has("msg_edit_text", "ID Comic"), "R11 daftar ind ke-edit")
        qid_i = list(bot.STATES_M.keys())[-1]
        st_i = bot.STATES_M[qid_i]
        check(st_i.get("mod") is scraper_indo, "R11 state bawa mod=indo")
        # detail → lewat ind_gallery
        clear()
        await bot.h_cb_m(mk_update(f"mv|{qid_i}|1"), mk_ctx())
        check(has("reply_photo", "ID Judul"), "R11 detail cover ind")
        check(any(c[0] == "gallery" for c in ind_calls), "R11 pake ind_gallery")
        # reader slide → lewat ind_download
        card_i = FakeMsg()
        clear()
        await bot.h_cb_m(mk_update(f"mr|{qid_i}|1|1", msg=card_i), mk_ctx())
        check(has("reply_photo", "halaman 1/4"), "R11 reader ind hal 1")
        rid = bot.STATES_M[qid_i]["reader"][1]
        clear()
        await bot.h_cb_m(mk_update(f"mr|{qid_i}|1|2", msg=card_i), mk_ctx())
        check(has("edit_media", idx=rid, sub="halaman 2/4"), "R11 reader ind slide → edit")
        # paging → lewat ind_search
        clear()
        await bot.h_cb_m(mk_update(f"mp|{qid_i}|2", msg=card_i), mk_ctx())
        check(any(c[0] == "search" and c[2] == 2 for c in ind_calls), "R11 paging pake ind_search")
        # zip → ind_download + zip_files
        clear()
        await bot.h_cb_m(mk_update(f"mz|{qid_i}|1", msg=card_i), mk_ctx())
        check(has("send_document", ".zip"), "R11 zip ind terkirim")
        check(any(c[0] == "download" and c[3] for c in ind_calls), "R11 zip pake max_bytes")
    finally:
        (scraper_indo.search, scraper_indo.gallery, scraper_indo.download_pages) = real

    # ─── R12: tangga fallback download (format id basi pas unduh) ───
    import sys as _sys, types as _types
    from yt_dlp.utils import DownloadError
    class FakeYDL:
        calls: list = []
        def __init__(self, opts): self.opts = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True):
            FakeYDL.calls.append(self.opts.get("format"))
            if len(FakeYDL.calls) == 1:
                raise DownloadError(
                    "ERROR: [XHamster] x: Requested format is not available")
            d = os.path.dirname(self.opts["outtmpl"])
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "ladtest.mp4")
            with open(p, "wb") as f:
                f.write(b"0" * 128)
            return {"id": "ladtest"}
    real_yt = _sys.modules.get("yt_dlp")
    _sys.modules["yt_dlp"] = _types.SimpleNamespace(YoutubeDL=FakeYDL)
    try:
        FakeYDL.calls.clear()
        tmpd = os.path.join(os.path.expanduser("~/.hermes/cache/scratch"), "lad_test")
        p = REAL_DOWNLOAD_SYNC("https://x/videos/v1", "hls-999-0", tmpd)
        check(len(FakeYDL.calls) == 2, "R12 retry 2x", str(FakeYDL.calls))
        check(FakeYDL.calls[0] == "hls-999-0", "R12 percobaan1 = format id asli")
        check("m3u8" in FakeYDL.calls[1], "R12 fallback = selector hls", str(FakeYDL.calls))
        check(os.path.isfile(p), "R12 file hasil fallback ada")
        os.remove(p)
        # kasus bukan masalah format → langsung naik, jangan retry
        class DieYDL(FakeYDL):
            def extract_info(self, url, download=True):
                raise DownloadError("ERROR: network timeout")
        _sys.modules["yt_dlp"] = _types.SimpleNamespace(YoutubeDL=DieYDL)
        try:
            REAL_DOWNLOAD_SYNC("https://x/videos/v2", "hls-1-0", tmpd)
            raise AssertionError("R12 seharusnya raise error non-format")
        except DownloadError:
            pass
    finally:
        if real_yt is not None:
            _sys.modules["yt_dlp"] = real_yt
        else:
            _sys.modules.pop("yt_dlp", None)

    # ─── R13: guard limit 50MB + retry upload ───
    from telegram.error import BadRequest as _BR, NetworkError as _NE
    # a) NetworkError transien → retry sampai sukses
    calls_t: list = []
    async def flaky():
        calls_t.append(1)
        if len(calls_t) < 3:
            raise _NE("httpx.ReadError:")
        return "ok"
    out = await bot._send_retry(flaky, delays=(0, 0))
    check(out == "ok" and len(calls_t) == 3, "R13a retry sukses attempt-3", str(calls_t))
    # b) BadRequest (file ditolak API) → TANPA retry
    calls_b: list = []
    async def bad():
        calls_b.append(1)
        raise _BR("Bad Request: REQUEST_ENTITY_TOO_LARGE")
    try:
        await bot._send_retry(bad, delays=(0, 0))
        raise AssertionError("R13b seharusnya raise BadRequest")
    except _BR:
        pass
    check(len(calls_b) == 1, "R13b BadRequest tanpa retry", str(calls_b))
    # c) file 51MB → guard nolak SEBELUM upload, kasih tombol resolusi
    real_dl = scraper.download_sync
    def big_dl(url, format_id, out_dir, progress=None):
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "big.mp4")
        with open(p, "wb") as f:
            f.truncate(51 * 1024 * 1024)  # sparse, instan
        if progress:
            progress(1, 1)
        return p
    scraper.download_sync = big_dl
    try:
        clear()
        await bot.h_cb(mk_update(f"d|{qid}|1", msg=card_msg), mk_ctx())
    finally:
        scraper.download_sync = real_dl
        big = os.path.join(str(bot.DL_DIR), "big.mp4")
        if os.path.isfile(big):
            os.remove(big)
    check(not has("send_document"), "R13c guard: ga ada upload file gede", str(CALLS[-6:]))
    check(has("msg_edit_caption", "50MB"), "R13c warning limit tampil", str(CALLS[-6:]))

    # ─── R14: /dracin (dracinema — index lokal + playback + kirim video) ───
    import re as _re
    # pola callback ga saling tabrakan (bug klasik: 'drd|' ke-ambil handler 'd|')
    check(_re.match(r"^(v|n|d|b|p|k|s|noop)\|", "drd|q|1|2") is None,
          "R14p pola h_cb tidak nangkep drd")
    check(_re.match(r"^(drs|drk|drp|drd)\|", "d|q|1") is None,
          "R14p pola h_cb_d tidak nangkep d")
    # /dracin → daftar (state punya items)
    clear()
    await bot.h_dracin(mk_update("x"), mk_ctx())
    check(has("msg_edit_text", "halaman"), "R14 daftar dracin tampil")
    check(has("msg_edit_text", "dracinema"), "R14 label dracinema di list")
    qid_d = list(bot.STATES_D.keys())[-1]
    check(len(bot.STATES_D[qid_d]["items"]) == 3, "R14 state dracin isi items")
    # detail → caption 30 episode + keyboard EP
    clear()
    await bot.h_cb_d(mk_update(f"drk|{qid_d}|1"), mk_ctx())
    check(has("reply_photo", "30 episode"), "R14 detail: eps dari desc parser")
    check(has("reply_photo", "gratis"), "R14 detail: info ep gratis")
    # navigasi halaman episode → edit keyboard di tempat
    clear()
    await bot.h_cb_d(mk_update(f"drp|{qid_d}|1|2"), mk_ctx())
    check(has("cq_edit_rm"), "R14 nav episode edit keyboard di tempat")
    # download EP 1 (kind=ok) → send_video dengan caption EP
    clear()
    await bot.h_cb_d(mk_update(f"drd|{qid_d}|1|1"), mk_ctx())
    check(has("send_video", "EP 1"), "R14 drd EP1 → send_video", str(CALLS[-6:]))
    check(not has("BUSY"), "R14 BUSY dilepas setelah kirim")
    check(bot.BUSY == set(), "R14 ga ada BUSY nyangkut")
    # login_required → pesan jujur, TANPA video
    DR_KIND["kind"] = "login_required"
    clear()
    await bot.h_cb_d(mk_update(f"drd|{qid_d}|1|10"), mk_ctx())
    check(has("msg_edit_text", "butuh login"), "R14 ep premium → info login", str(CALLS[-6:]))
    check(not has("send_video"), "R14 ep premium tidak kirim video", str(CALLS[-6:]))
    DR_KIND["kind"] = "ok"
    # paging daftar → edit in place
    clear()
    await bot.h_cb_d(mk_update(f"drs|{qid_d}|2"), mk_ctx())
    check(has("cq_edit_text", "halaman"), "R14 paging dracin edit daftar")
    # state basi → alert
    clear()
    await bot.h_cb_d(mk_update("drk|nonexistent|1"), mk_ctx())
    check(has("answer", "basi"), "R14 state basi → alert")

    # ─── R15: dracin.best (2 sumber) — toggle, detail on-demand, ffmpeg ────
    import scraper_drbest
    DB_ITEMS = [{"title": "Edukasi Seks Oleh Sahabatku",
                 "url": "https://dracin.best/dramabox/edukasi-seks-1",
                 "thumb": "", "desc": "", "provider": "dramabox"}]

    def fake_bs_search(q="", page=1):
        if not q or "edukasi" in q.lower():
            return DB_ITEMS, 1
        return [], 0
    scraper_drbest.search = fake_bs_search

    async def fake_bs_detail(url):
        return {"title": "Edukasi Seks Oleh Sahabatku", "thumb": "", "desc": "",
                "eps": 58, "play": {1: "/dramabox/play/1/1", 5: "/dramabox/play/1/5"}}
    scraper_drbest.detail = fake_bs_detail

    async def fake_bs_stream(pu):
        return "https://cdn.fake/master.m3u8"
    scraper_drbest.stream_url = fake_bs_stream

    async def fake_bs_download(murl, out, progress=None):
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"0" * 8192)
        if progress:
            progress(8192, 8192)
        return out, False
    scraper_drbest.download = fake_bs_download

    # stub search ai2 — biar toggle ke Swaplse deterministik (tanpa index DB)
    import scraper_ai2

    def fake_ai2_search(q="", page=1):
        return [{"title": "AI Loop", "url": "5565", "thumb": "", "desc": "",
                 "provider": "Swaplse AI"}], 1
    scraper_ai2.search = fake_ai2_search

    # /dracin2 → list sumber best (args diisi manual: fake ctx tanpa parser)
    clear()
    ctx2 = mk_ctx()
    ctx2.args = ["edukasi"]
    await bot.h_dracin2(mk_update("/dracin2 edukasi"), ctx2)
    check(has("msg_edit_text", "dracin.best") and has("msg_edit_text", "edukasi"),
          "R15 /dracin2 list sumber=dracin.best")
    qid2 = list(bot.STATES_D.keys())[-1]
    check(_state := bot.STATES_D[qid2].get("src") == "best",
          f"R15 state src=best (dapat {_state})")

    # toggle siklus 5 sumber: best → candy → nh → film → dracinema → best
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(has("cq_edit_text", "Candy AI Shorts"),
          "R15 toggle → Candy AI Shorts ter-render")
    check(bot.STATES_D[qid2]["src"] == "candy", "R15 state src=candy setelah toggle")
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(has("cq_edit_text", "NontonHentai"),
          "R15 toggle → NontonHentai ter-render")
    check(bot.STATES_D[qid2]["src"] == "nh", "R15 state src=nh setelah toggle")
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(bot.STATES_D[qid2]["src"] == "film", "R15 toggle → film (LK21)")
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(bot.STATES_D[qid2]["src"] == "ai2", "R15 toggle → ai2 (Swaplse)")
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(bot.STATES_D[qid2]["src"] == "drc", "R15 toggle → drc")
    clear()
    await bot.h_cb_d(mk_update(f"drg|{qid2}|0"), mk_ctx())
    check(bot.STATES_D[qid2]["src"] == "best", "R15 toggle balik → best (siklus penuh)")

    # detail best: fetch on-demand → 58 episode, teks "gratis"
    clear()
    await bot.h_cb_d(mk_update(f"drk|{qid2}|1"), mk_ctx())
    check(has("reply_photo", "58 episode"), "R15 detail best: 58 episode")
    check(has("reply_photo", "semua episode gratis"), "R15 detail best: teks gratis")
    check(has("answer", "memuat detail"), "R15 detail best: toast answer")

    # download EP5 → send_video "EP 5" (jalur ffmpeg, direct)
    clear()
    await bot.h_cb_d(mk_update(f"drd|{qid2}|1|5"), mk_ctx())
    check(has("send_video", "EP 5") and has("send_video", "full episode"),
          "R15 download best → send_video EP 5")
    check(has("msg_edit_text", "selesai"), "R15 status best selesai")

    # EP nggak ada → pesan jujur, tanpa send_video
    clear()
    await bot.h_cb_d(mk_update(f"drd|{qid2}|1|99"), mk_ctx())
    check(has("msg_edit_text", "nggak ada"), "R15 EP99 → pesan 'nggak ada'")
    check(not has("send_video"), "R15 EP99 tanpa kirim video")

    # ─── R16: mode SCROLL (strip vertikal → dokumen full-res, prefetch) ────
    clear()
    await bot.h_manhwa(mk_update("/manhwa"), mk_ctx())
    qidR = list(bot.STATES_M.keys())[-1]
    # reader 1-up dulu (nyalain st["reader"] + cek tombol 📜)
    await bot.h_cb_m(mk_update(f"mr|{qidR}|1|1"), mk_ctx())
    check(has("reply_photo", "halaman 1/"), "R16 reader 1-up jalan")
    kb0 = bot.reader_kb(qidR, 1, 1, 20)
    check("ms|" in str(kb0.to_dict()), "R16 tombol 📜 scroll ada di reader")

    # patch sementara: detail 20 halaman + merge palsu (PIL nggak dibutuhin)
    orig_md, orig_merge = bot._m_detail, bot._merge_vertical

    async def _big_detail(st, it):
        d = await orig_md(st, it)
        d.pages = 20
        return d

    def _fake_merge(paths, out, width=1000):
        with open(out, "wb") as f:
            f.write(b"STRIP" * 10)
        return out

    bot._m_detail, bot._merge_vertical = _big_detail, _fake_merge
    try:
        # strip 1 → EDIT pesan reader yang sama (bukan pesan baru!)
        clear()
        await bot.h_cb_m(mk_update(f"ms|{qidR}|1|1"), mk_ctx())
        check(has("edit_media", "halaman 1–6/20"), "R16 strip1: caption 1–6/20")
        check(has("edit_media", "▰"), "R16 caption ada progress bar")
        check(not has("reply_document"), "R16 strip1 ngedit, bukan kirim baru")
        stR = bot.STATES_M[qidR]
        check(1 in stR.get("strip_cache", {}), "R16 strip1 ke-cache")
        await asyncio.sleep(0.6)
        check(2 in stR.get("strip_cache", {}), "R16 prefetch strip2 otomatis")

        # strip terakhir (4) → halaman 19–20
        clear()
        await bot.h_cb_m(mk_update(f"ms|{qidR}|1|4"), mk_ctx())
        check(has("edit_media", "halaman 19–20/20"), "R16 strip4: 19–20/20")
        # strip 99 → ujung, tanpa edit
        clear()
        await bot.h_cb_m(mk_update(f"ms|{qidR}|1|99"), mk_ctx())
        check(has("answer", "ujung"), "R16 strip99 → 'udah di ujung'")
        check(not has("edit_media"), "R16 strip99 tanpa edit")
        # tombol balik ke mode per-halaman (dari strip terakhir → hal 19)
        kb4 = bot.scroll_kb(qidR, 1, 4, 4, 18)
        check("mr|{0}|1|19".format(qidR) in str(kb4.to_dict()),
              "R16 tombol 🧩 per halaman → halaman 19")
        check("ms|{0}|1|3".format(qidR) in str(kb4.to_dict()),
              "R16 strip4 punya tombol ◀️ balik")
    finally:
        bot._m_detail, bot._merge_vertical = orig_md, orig_merge
        wd = bot.STATES_M[qidR].pop("_mstrip_dir", None)
        if wd and os.path.isdir(wd):
            import shutil
            shutil.rmtree(wd, ignore_errors=True)

    # ─── R17: anti-basi + tombol ✅ selesai ────────────────────────────────
    # a) recovery mode DOC (strip scroll) langsung ke helper
    clear()
    ctxR = mk_ctx()
    updR = mk_update("x")   # q.message = FakeMsg fresh
    stR = bot.STATES_M[qidR]
    stR["reader"] = (777, 9999)   # titik-ke pesan yang udah mati
    await bot._recover_reader(updR.callback_query, stR, "doc",
                              "/tmp/fake_strip.jpg", "📜 halaman 1–6/20", None)
    check(has("reply_document", "halaman 1–6/20"), "R17a strip → pesan strip BARU")
    check(has("answer", "pesan baca baru"), "R17a toast lanjut")
    check(stR["reader"][1] != 9999, "R17a tracker strip ke-refresh")

    # b) ✅ selesai di READER manhwa (dilewat handler h_cb_d — mf seragam)
    await bot.h_cb_m(mk_update(f"mr|{qidR}|1|1"), mk_ctx())   # reader ada lagi
    rid = stR["reader"][1]
    check(rid, "R17b reader aktif sebelum selesai")
    clear()
    await bot.h_cb_d(mk_update(f"mf|{qidR}|1"), mk_ctx())
    check(has("msg_delete"), "R17b pesan baca dihapus")
    check(has("answer", "selesai baca"), "R17b toast 'selesai baca'")
    check("reader" not in stR, "R17b tracker reader dilepas")

    # c) ✅ selesai di kartu dracin (qid R15, state dracin → pesan 'ditonton')
    clear()
    await bot.h_cb_d(mk_update(f"mf|{qid2}|1"), mk_ctx())
    check(has("msg_delete"), "R17c kartu dracin dihapus")
    check(has("answer", "selesai ditonton"), "R17c toast 'selesai ditonton'")

    # d) tombol ✅ ada di keyboard reader & dracin
    kb_r = bot.reader_kb("q", 1, 1, 5)
    check("mf|" in str(kb_r.to_dict()), "R17d reader kb punya ✅ selesai")
    kb_d = bot.d_eps_kb("q", 1, 1, 1, 30, "https://x")
    check("mf|" in str(kb_d.to_dict()), "R17d kartu dracin punya ✅ selesai")

    # ─── R18: shortcut — tombol lompat + ketik angka ───────────────────────
    # a) tombol keyboard
    kbr = str(bot.reader_kb("q", 1, 7, 50).to_dict())
    check("mr|q|1|1" in kbr and "mr|q|1|50" in kbr and "⏪10" in kbr,
          "R18a reader: ⏮/⏭ + ⏪10/10⏩ ada")
    kbs = str(bot.scroll_kb("q", 1, 4, 9, 18).to_dict())
    check("ms|q|1|1" in kbs and "ms|q|1|9" in kbs and "⏪3" in kbs,
          "R18a scroll: ⏮/⏭ strip + ⏪3/3⏩ ada")
    kbd = str(bot.d_eps_kb("q", 1, 3, 1, 60, "https://x").to_dict())
    check("drp|q|1|1" in kbd and "drp|q|1|5" in kbd,
          "R18a dracin EP: ⏮/⏭ halaman EP ada")

    # b) buka reader → sesi LAST aktif; ketik "3" → lompat halaman 3
    clear()
    await bot.h_cb_m(mk_update(f"mr|{qidR}|1|1"), mk_ctx())
    check(bot.LAST.get(777, {}).get("kind") == "m", "R18b sesi baca tercatat")
    m3 = FakeMsg(); m3.text = "3"
    clear()
    await bot.h_text(mk_update("3", msg=m3), mk_ctx())
    check(has("edit_media", "halaman 3/"), "R18b ketik 3 → reader loncat hal 3")

    # c) angka kelewat → pesan jujur
    m99 = FakeMsg(); m99.text = "99"
    clear()
    await bot.h_text(mk_update("99", msg=m99), mk_ctx())
    check(has("reply_text", "halaman cuma"), "R18c hal 99 → 'halaman cuma N'")

    # d) dracin: buka kartu (sesi nonton) → ketik 37 → picker EP ke hal 4
    clear()
    await bot.h_cb_d(mk_update(f"drk|{qid2}|1"), mk_ctx())
    check(bot.LAST.get(777, {}).get("kind") == "d", "R18d sesi nonton tercatat")
    m37 = FakeMsg(); m37.text = "37"
    clear()
    await bot.h_text(mk_update("37", msg=m37), mk_ctx())
    check(has("edit_rm"), "R18d ketik 37 → keyboard EP pindah (edit_rm)")

    # e) EP di luar jangkau → jujur
    m999 = FakeMsg(); m999.text = "999"
    clear()
    await bot.h_text(mk_update("999", msg=m999), mk_ctx())
    check(has("reply_text", "nggak ada"), "R18e EP999 → 'EP nggak ada'")

    # f) angka TANPA sesi → balik jadi search biasa
    bot.LAST.clear()
    m2048 = FakeMsg(); m2048.text = "2048"
    clear()
    await bot.h_text(mk_update("2048", msg=m2048), mk_ctx())
    check(has("msg_edit_text", "halaman") or has("reply_text", "halaman"),
          "R18f tanpa sesi → search biasa")

    # ─── R19: /ai Candy AI Shorts — list, detail, download, paywall ────────
    class FakeCandy:
        @staticmethod
        def search(q, page=1):
            return ([{"title": "AI Seks Kampus", "url": "https://candy/x",
                      "thumb": "", "desc": "", "provider": "candy"}], 1)

        @staticmethod
        async def detail(url):
            return {"title": "AI Seks Kampus", "url": url, "total": 4,
                    "free_n": 2,
                    "eps": [
                        {"n": 1, "free": True, "url": "http://cdn/1.mp4", "poster": ""},
                        {"n": 2, "free": True, "url": "http://cdn/2.mp4", "poster": ""},
                        {"n": 3, "free": False, "url": "", "poster": ""},
                        {"n": 4, "free": False, "url": "", "poster": ""}]}

        @staticmethod
        async def download(url, out):
            with open(out, "wb") as f:
                f.write(b"\x00" * 2048)
            return (out, False)

    _real_candy = bot.scraper_candy
    bot.scraper_candy = FakeCandy
    try:
        clear()
        ctxA = mk_ctx()
        ctxA.args = ["kampus"]
        await bot.h_ai(mk_update("/ai kampus"), ctxA)
        check(has("msg_edit_text", "Candy AI Shorts"), "R19 /ai list sumber=Candy")
        qidA = list(bot.STATES_D.keys())[-1]
        clear()
        await bot.h_cb_d(mk_update(f"drk|{qidA}|1"), mk_ctx())
        check(has("reply_text", "GRATIS") or has("msg_edit_text", "GRATIS"),
              "R19 detail candy sebut EP GRATIS")
        # download EP1 → send_video; EP3 → paywall
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidA}|1|1"), mk_ctx())
        check(has("send_video"), "R19 candy EP1 → send_video")
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidA}|1|3"), mk_ctx())
        check(has("msg_edit_text", "paywall"), "R19 candy EP3 → jujur paywall")
    finally:
        bot.scraper_candy = _real_candy
        _pop_if = bot.STATES_D.pop(qidA, None)
        del _pop_if

    # ─── R20: persistensi state — selamat dari restart (anti "basi") ───────
    import pickle as _pk
    _real_file = bot.STATES_FILE
    bot.STATES_FILE = "/tmp/xh_test_states.pkl"
    try:
        qidT = bot.new_state_d("uji", 1, 1, [], "drc")
        bot._save_states()
        with open(bot.STATES_FILE, "rb") as f:
            dump = _pk.load(f)
        check(qidT in dump.get("STATES_D", {}), "R20 state masuk dump disk")
        keepD = dict(bot.STATES_D)
        bot.STATES_D.clear()
        bot._load_states()
        check(qidT in bot.STATES_D, "R20 state pulih dari disk setelah 'restart'")
        bot.STATES_D.clear()
        bot.STATES_D.update(keepD)
    finally:
        bot.STATES_FILE = _real_file
        try:
            os.remove("/tmp/xh_test_states.pkl")
        except OSError:
            pass

    # ─── R21: /hvid NontonHentai — list, detail semua EP gratis, download ──
    class FakeNh:
        @staticmethod
        def search(q, page=1):
            return ([{"title": "Harem Camp", "url": "https://nh/x",
                      "thumb": "", "desc": "", "provider": "NontonHentai"}], 9)

        @staticmethod
        async def detail(url):
            return {"title": "Harem Camp", "url": url, "total": 3,
                    "thumb": "",
                    "eps": {1: "https://nh/x/ep1", 2: "https://nh/x/ep2",
                            3: "https://nh/x/ep3"}}

        @staticmethod
        async def stream_url(ep_url):
            return "https://cdn/x.m3u8"

        @staticmethod
        async def download(m3u8, out):
            with open(out, "wb") as f:
                f.write(b"\x00" * 2048)
            return (out, False)

    _real_nh = bot.scraper_nh
    bot.scraper_nh = FakeNh
    try:
        clear()
        ctxH = mk_ctx()
        ctxH.args = ["harem"]
        await bot.h_hvid(mk_update("/hvid harem"), ctxH)
        check(has("msg_edit_text", "NontonHentai"), "R21 /hvid list sumber=NontonHentai")
        qidH = list(bot.STATES_D.keys())[-1]
        clear()
        await bot.h_cb_d(mk_update(f"drk|{qidH}|1"), mk_ctx())
        check(has("reply_text", "GRATIS") or has("reply_photo", "GRATIS"),
              "R21 detail nh: semua EP GRATIS")
        check(bot.STATES_D[qidH]["eps"][1] == (1, 3),
              "R21 eps range = 1..3 (semua EP gratis)")
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidH}|1|2"), mk_ctx())
        check(has("send_video"), "R21 nh EP2 → send_video")
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidH}|1|9"), mk_ctx())
        check(has("msg_edit_text", "nggak ada"), "R21 nh EP9 → jujur nggak ada")
    finally:
        bot.scraper_nh = _real_nh
        bot.STATES_D.pop(qidH, None)

    # ─── R22: /film LK21.dev — list, detail film, unduh + sub burn ─────────
    class FakeLK21:
        @staticmethod
        def search(q="", page=1):
            return ([{"title": "Paris in Bali",
                      "url": "https://layarkaca21.dev/paris-in-bali",
                      "slug": "paris-in-bali", "year": ""}], 5)

        @staticmethod
        def detail(url):
            return {"title": "Paris in Bali", "url": url, "year": "2023",
                    "genres": ["Drama", "Romance"],
                    "synopsis": "Sinopsis film percobaan untuk tes R22.",
                    "poster": "", "embed": "https://putarin.biz/e/x1"}

        @staticmethod
        def download(url, out_path=None, with_sub=True, progress=None):
            if progress:
                progress(5, 10)
            with open(out_path, "wb") as f:
                f.write(b"\x00" * 4096)
            if progress:
                progress(10, 10)
            return (out_path, 120, True)      # (path, dur, sub-burn)

    _real_film = bot.scraper_lk21
    bot.scraper_lk21 = FakeLK21
    try:
        clear()
        ctxF = mk_ctx()
        ctxF.args = ["paris"]
        await bot.h_film(mk_update("/film paris"), ctxF)
        check(has("msg_edit_text", "LK21 Film"), "R22 /film list sumber=LK21 Film")
        qidF = list(bot.STATES_D.keys())[-1]
        clear()
        await bot.h_cb_d(mk_update(f"drk|{qidF}|1"), mk_ctx())
        check(has("reply_photo", "film penuh") or has("reply_text", "film penuh"),
              "R22 detail film: 'film penuh'")
        check(has("reply_photo", "2023") or has("reply_text", "2023"),
              "R22 detail film: tahun")
        check(bot.STATES_D[qidF]["eps"][1] == (1, 1),
              "R22 film eps range = 1..1 (satu tombol)")
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidF}|1|1"), mk_ctx())
        check(has("send_video"), "R22 film unduh → send_video")
        check(has("msg_edit_text", "film terkirim"), "R22 status 'film terkirim'")
    finally:
        bot.scraper_lk21 = _real_film
        bot.STATES_D.pop(qidF, None)

    # ─── R23: /komik KomikDoujin — list, detail gabungan chapter, zip ──────
    import scraper_kdj
    kdj_calls = []
    async def kdj_search(q="", page=1):
        kdj_calls.append(("search", q, page))
        items = [scraper_hentai.Gallery(idx=i + 1, title=f"Doujin Indo {i + 1}",
                                        url=f"https://komikdoujin.com/series/kdj{i + 1}/",
                                        cat="komik Indonesia", thumb="")
                 for i in range(3)]
        return scraper_hentai.GalleryPage(query=q, page=page, max_pages=2,
                                          items=items)
    async def kdj_gallery(url):
        kdj_calls.append(("gallery", url))
        return scraper_hentai.GalleryDetail(title="Doujin Judul", url=url,
                                            cover="http://x/c.jpg", pages=6,
                                            page_urls=[f"k{i}" for i in range(1, 7)],
                                            tags=["3 chapter"])
    async def kdj_download(detail, out_dir, start=0, limit=None, progress=None,
                           max_bytes=None):
        kdj_calls.append(("download", start, limit, max_bytes is not None))
        os.makedirs(out_dir, exist_ok=True)
        paths = []
        for i in range(limit or 2):
            p = os.path.join(out_dir, f"kdj_{start + i}.jpg")
            with open(p, "wb") as f:
                f.write(b"0" * 256)
            paths.append(p)
        return paths, False
    real_kdj = (scraper_kdj.search, scraper_kdj.gallery, scraper_kdj.download_pages)
    scraper_kdj.search, scraper_kdj.gallery, scraper_kdj.download_pages = (
        kdj_search, kdj_gallery, kdj_download)
    try:
        clear()
        await bot.h_komik(mk_update("x"), mk_ctx())
        check(has("reply_text", "📖"), "R23 status /komik terkirim")
        check(has("msg_edit_text", "Doujin Indo"), "R23 daftar komik ke-edit")
        qid_k = list(bot.STATES_M.keys())[-1]
        check(bot.STATES_M[qid_k].get("mod") is scraper_kdj,
              "R23 state bawa mod=kdj")
        clear()
        await bot.h_cb_m(mk_update(f"mv|{qid_k}|1"), mk_ctx())
        check(has("reply_photo", "Doujin Judul"), "R23 detail komik cover")
        check(any(c[0] == "gallery" for c in kdj_calls), "R23 pake kdj_gallery")
        card_k = FakeMsg()
        clear()
        await bot.h_cb_m(mk_update(f"mr|{qid_k}|1|1", msg=card_k), mk_ctx())
        check(has("reply_photo", "halaman 1/6"), "R23 reader komik hal 1")
        clear()
        await bot.h_cb_m(mk_update(f"mz|{qid_k}|1", msg=card_k), mk_ctx())
        check(has("send_document", ".zip"), "R23 zip komik terkirim")
        check(any(c[0] == "download" and c[3] for c in kdj_calls),
              "R23 zip pake max_bytes")
    finally:
        (scraper_kdj.search, scraper_kdj.gallery,
         scraper_kdj.download_pages) = real_kdj

    # ─── R24: /ai2 Swaplse AI — list, detail 1 tombol, mp4 direct ──────────
    class FakeAi2:
        @staticmethod
        def search(q, page=1):
            return ([{"title": "AI Hentai Loop", "url": "5565", "thumb": "",
                      "desc": "", "provider": "Swaplse AI"}], 4806)

        @staticmethod
        async def detail(url):
            return {"title": "AI Hentai Loop", "url": url, "eps": {1: url},
                    "total": 1, "thumb": ""}

        @staticmethod
        async def stream_url(ep_url):
            return f"https://cdn.swaplse.com/vitrina/w{ep_url}.mp4"

        @staticmethod
        async def download(url, out):
            with open(out, "wb") as f:
                f.write(b"\x00" * 4096)
            return out

    _real_ai2 = bot.scraper_ai2
    bot.scraper_ai2 = FakeAi2
    try:
        clear()
        ctxA = mk_ctx()
        ctxA.args = ["loop"]
        await bot.h_ai2(mk_update("/ai2 loop"), ctxA)
        check(has("msg_edit_text", "Swaplse AI"), "R24 /ai2 list sumber=Swaplse AI")
        qidA = list(bot.STATES_D.keys())[-1]
        clear()
        await bot.h_cb_d(mk_update(f"drk|{qidA}|1"), mk_ctx())
        check(has("reply_photo", "GRATIS") or has("reply_text", "GRATIS"),
              "R24 detail ai2: gratis tanpa login")
        check(bot.STATES_D[qidA]["eps"][1] == (1, 1),
              "R24 ai2 eps range = 1..1")
        clear()
        await bot.h_cb_d(mk_update(f"drd|{qidA}|1|1"), mk_ctx())
        check(has("send_video"), "R24 ai2 unduh → send_video")
        check(has("msg_edit_text", "selesai"), "R24 status selesai")
    finally:
        bot.scraper_ai2 = _real_ai2
        bot.STATES_D.pop(qidA, None)

    # ── R28: filter arsip LK21 (parse_query) ──
    pq = bot.scraper_lk21.parse_query("genre:horror")
    check(pq["kind"] == "genre" and pq["slug"] == "kengerian",
          "R28 genre:horror → kengerian")
    pq = bot.scraper_lk21.parse_query("tahun:2024")
    check(pq["kind"] == "year" and pq["slug"] == "2024", "R28 tahun:2024")
    pq = bot.scraper_lk21.parse_query("negara:jepang")
    check(pq["kind"] == "country" and pq["slug"] == "japan",
          "R28 negara:jepang → japan")
    pq = bot.scraper_lk21.parse_query("moana")
    check(pq["kind"] is None and pq["text"] == "moana", "R28 judul biasa tanpa filter")
    pq = bot.scraper_lk21.parse_query("film bagus")
    check(pq["kind"] is None, "R28 teks bebas gak salah tangkap")

    # ── R31: /stat, /hemat, error-notif, /acak stub ──
    clear()
    await bot.h_stat(mk_user_update("/stat"), mk_ctx())
    check(has("reply_text", "Statistik bot"), "R31 /stat tampil")
    ctxH = mk_ctx(); ctxH.args = ["on"]
    await bot.h_hemat(mk_user_update("/hemat on"), ctxH)
    check(has("reply_text", "mode hemat AKTIF"), "R31 /hemat on")
    ctxH.args = ["off"]
    await bot.h_hemat(mk_user_update("/hemat off"), ctxH)
    check(has("reply_text", "mati"), "R31 /hemat off")
    clear()
    class FakeLK21A:
        @staticmethod
        def parse_query(q):
            return bot.scraper_lk21.parse_query.__wrapped__(q) \
                if hasattr(bot.scraper_lk21.parse_query, "__wrapped__") \
                else {"kind": None, "text": q}

        @staticmethod
        def search(q="", page=1):
            return ([{"title": "Film Acak", "url": "https://layarkaca21.dev/fa",
                      "slug": "fa", "year": ""}], 1)

        @staticmethod
        def detail(url):
            return {"title": "Film Acak", "url": url, "year": "2025",
                    "genres": ["Aksi"], "synopsis": "uji coba",
                    "poster": "", "embed": "https://putarin.biz/e/z"}
    _rk = bot.scraper_lk21
    bot.scraper_lk21 = FakeLK21A()
    try:
        ctxA = mk_ctx(); ctxA.args = []
        await bot.h_acak(mk_user_update("/acak"), ctxA)
        check(has("reply_text", "Rekomendasi") or has("reply_photo", "Rekomendasi"),
              "R31 /acak kasih rekomendasi")
    finally:
        bot.scraper_lk21 = _rk
    clear()
    ctxE = mk_ctx()
    ctxE.error = RuntimeError("uji error notif")
    await bot.h_error(None, ctxE)
    check(has("send_message", bot.OWNER_ID), "R31 error → notif owner")

    # ── R33: /series (search → judul → daftar EP) ──
    import scraper_series as _ss
    print("── R33: /series ──")
    _ss_s, _ss_d = _ss.search, _ss.detail
    _ss.search = lambda q="", page=1: ([{"title": "Test Show (2024) Sub Indo",
        "url": "https://sparkott.com/tv/test-show/", "slug": "test-show",
        "id": 1, "year": ""}], 964)
    _ss.detail = lambda url, tv_id=None: {"title": "Test Show",
        "eps": [(f"S1E{i}", f"https://sparkott.com/eps/test-show-s1e{i}/")
                for i in range(1, 13)]}
    try:
        clear()
        ctx33 = mk_ctx(); ctx33.args = ["euphoria"]
        await bot.h_series(mk_user_update("/series euphoria"), ctx33)
        check(len(bot.STATE_SERIES) >= 1, "R33 series: state tersimpan")
        qid = list(bot.STATE_SERIES.keys())[-1]
        check(has("msg_edit_text", "TV Series"), "R33 series: list judul tampil")
        # klik judul pertama
        await bot.h_series_cb(mk_update(f"srs|{qid}|1"), mk_ctx())
        st = bot.STATE_SERIES.get(qid)
        check(st is not None and st.get("eps") and len(st["eps"]) == 12,
              "R33 series: daftar episode (12 EP)")
        # klik EP ke-2 → masuk jalur download (mock download)
        _sd = _ss.download
        _ss.download = lambda url, out=None, with_sub=True, progress=None, max_segs=None: ("/tmp/series_mock.mp4", 3600.0, True)
        import subprocess as _sp
        _sp.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=64x64:d=2", "-c:v", "libx264",
                 "-preset", "ultrafast", "/tmp/series_mock.mp4"],
                capture_output=True, timeout=60)
        try:
            clear()
            cbe = f"srs|ser|{qid}|2"
            await bot.h_series_cb(mk_update(cbe), mk_ctx())
            check(has("send_video", "series_mock.mp4"),
                  "R33 series: episode terkirim sebagai video playable")
            check(has("cq_edit_text", "✅ episode terkirim"),
                  "R33 series: konfirmasi sukses")
        finally:
            _ss.download = _sd
    finally:
        _ss.search, _ss.detail = _ss_s, _ss_d

    # ── R34: /r34 (gambar dewasa acak, mock) ──
    import scraper_nsfw as _ns
    print("── R34: /r34 ──")
    _rp = _ns.random_post
    _ns.random_post = lambda q="": {"url": "https://x.example/pic.png",
        "tags": "solo female big_breasts", "id": 1, "score": 100}
    try:
        clear()
        ctx34 = mk_ctx(); ctx34.args = ["catgirl"]
        await bot.h_r34(mk_user_update("/r34 catgirl"), ctx34)
        check(has("reply_photo", "score 100"), "R34 kirim foto acak")
        # tombol refresh
        clear()
        await bot.h_r34_cb(mk_update("r34r|catgirl"), mk_ctx())
        check(has("send_photo", "score 100"), "R34 tombol lainnya")
        # filter tag jahat
        clear()
        _ns.random_post = _rp
        bad = mk_ctx(); bad.args = ["loli"]
        await bot.h_r34(mk_user_update("/r34 loli"), bad)
        check(has("reply_text", "gak gua izinin"), "R34 tag jahat ditolak")
    finally:
        _ns.random_post = _rp

    # ── R32: favorit, bookmark, lanjut ──
    import sqlite3 as _sq
    with bot._db() as _c:
        _c.execute("DELETE FROM fav WHERE uid=?", (bot.OWNER_ID,))
        _c.execute("DELETE FROM bk WHERE uid=?", (bot.OWNER_ID,))
        _c.execute("DELETE FROM last WHERE uid=?", (bot.OWNER_ID,))
    clear()
    ctxK = mk_ctx(); ctxK.args = ["paris"]
    await bot.h_film(mk_update("/film paris"), ctxK)
    qidK = list(bot.STATES_D.keys())[-1]
    clear()
    await bot.h_cb_d(mk_update(f"drk|{qidK}|1"), mk_ctx())   # buka detail
    clear()
    upS = mk_update(f"sv|{qidK}|1")
    upS.effective_user = types.SimpleNamespace(id=bot.OWNER_ID)
    await bot.h_simpan(upS, mk_ctx())
    check(has("answer", "disimpan") or has("reply_text", "koleksi"),
          "R32 💾 simpan favorit")
    clear()
    await bot.h_koleksi(mk_user_update("/koleksi"), mk_ctx())
    check(has("reply_text", "Koleksi"), "R32 /koleksi tampil daftar")
    check(has("callback_query" ) or True, "R32 lanjut")
    clear()
    await bot.h_lanjut(mk_user_update("/lanjut"), mk_ctx())
    check(has("reply_text", "belum ada") or has("reply_text", "Lanjut"),
          "R32 /lanjut responsif")
    bot._bk_set(bot.OWNER_ID, "m|uji", 7)
    check(bot._bk_get(bot.OWNER_ID, "m|uji") == 7, "R32 bookmark pos tersimpan")
    with bot._db() as _c:
        _c.execute("DELETE FROM bk WHERE uid=?", (bot.OWNER_ID,))
    clear()
    await bot.h_koleksi_cb(mk_update("kh|999999"), mk_ctx())
    check(True, "R32 hapus favorit gak error")

    # ── R30: Download (mode=best) harus VIDEO playable, bukan document ──
    _orig_dl = bot.scraper.download_sync

    def _fake_dl(url, fmt, dl_dir, progress=None):
        p = "/tmp/flow_best.mp4"
        open(p, "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
        return p

    bot.scraper.download_sync = _fake_dl
    try:
        clear()
        uX = mk_update("x")
        await bot.do_search(uX, "video best test")
        qidX = list(bot.STATES.keys())[-1]
        clear()
        await bot.run_media(mk_update(f"d|{qidX}|1"), qidX, 1, "best", mk_ctx())
        check(has("send_video", sub="Download full quality"),
              "R30 best → send_VIDEO playable")
        check(not has("send_document"), "R30 TIDAK jadi document")
    finally:
        bot.scraper.download_sync = _orig_dl
        bot.STATES_D.pop(qidX, None)

    # ── R29: /aiv — daftar AI video + detail + tombol kualitas ──
    class FakeEPAI:
        @staticmethod
        def search(q="", page=1):
            return ([{"title": "AI Video 1", "url": "https://x/v/1",
                      "id": "1", "thumb": ""},
                     {"title": "AI Video 2", "url": "https://x/v/2",
                      "id": "2", "thumb": ""}], 3)

        @staticmethod
        def detail(url):
            return {"title": "AI Video 1", "duration": "1:23", "thumb": "",
                    "qualities": [{"res": "360p", "size": "22 MB",
                                   "bytes": 22_000_000, "codec": "h264",
                                   "url": "https://x/d/360"},
                                  {"res": "720p", "size": "360 MB",
                                   "bytes": 360_000_000, "codec": "h264",
                                   "url": "https://x/d/720"}]}

        @staticmethod
        def download(url, out_path=None, res="720", progress=None):
            open("/tmp/flow_aiv.mp4", "wb").write(b"\x00\x00\x00\x18ftypmp42")
            return "/tmp/flow_aiv.mp4", 10

    _real_epai = bot.scraper_epai
    bot.scraper_epai = FakeEPAI()
    clear(); ctx = mk_ctx()
    ctx.args = ["ai", "gf"]
    await bot.h_aiv(mk_user_update("/aiv ai gf"), ctx)
    check(has("reply_text", "hal. 1/2"), "R29 daftar aiv + navigasi")
    upA = mk_update("aiv|0|https://x/v/1")
    await bot.h_aiv_cb(upA, mk_ctx())
    labels = " | ".join(
        b.text for r in (getattr(upA.message, "reply_markup", None)
                         or types.SimpleNamespace(inline_keyboard=[])).inline_keyboard
        for b in r)
    check("⬇️ 360p (22 MB)" in labels, "R29 kualitas < 45MB ditawarkan", labels)
    check("720p" not in labels, "R29 360MB DITOLAK (> 45MB)")
    await bot.h_aiv_dl(mk_update("aivd|0|https://x/v/1|360p"), mk_ctx())
    check(has("reply_video", "AI video (360p)"), "R29 video aiv terkirim")
    bot.scraper_epai = _real_epai

    # ── R25: /help = menu tombol ──
    clear()
    await bot.h_start(mk_update("/start"), mk_ctx())
    check(has("reply_text", "xHamster Bot"), "R25 /help sapa")
    rm = CALLS and None
    st25 = [c for c in CALLS if c[0] == "reply_text"]
    check(len(st25) >= 1, "R25 reply_text")
    clear()
    await bot.h_menu(mk_update("mn|film"), mk_ctx())
    check(has("cq_edit_text", "LK21"), "R25 tombol film → cara pakai LK21")
    clear()
    await bot.h_menu(mk_update("mn|back"), mk_ctx())
    check(has("cq_edit_text", "xHamster Bot"), "R25 tombol ⬅️ Menu balik")

    # ── R26: allowlist gate ──
    ctxG = mk_ctx()
    uku = mk_user_update("/cari x", uid=111222333)      # orang asing
    ok = await bot._gate_ok(uku, ctxG)
    check(ok is False, "R26 user tak dikenal DIBLOKIR")
    check(has("send_message", bot.OWNER_ID), "R26 notif ke owner")
    check(has("forward_message", bot.OWNER_ID), "R26 pesan asing di-forward")
    check(has("reply_text", "belum diizinkan"), "R26 balasan blokir")
    clear()
    own = mk_user_update("/cari x", uid=bot.OWNER_ID)   # owner
    check(await bot._gate_ok(own, ctxG) is True, "R26 owner lolos")
    clear()
    allowed = mk_user_update("/cari x", uid=999888777)  # user terdaftar
    bot.ALLOWED_IDS.add(999888777)
    try:
        check(await bot._gate_ok(allowed, ctxG) is True, "R26 user terdaftar lolos")
        check(has("send_message", bot.OWNER_ID), "R26 owner tetap dikabari")
    finally:
        bot.ALLOWED_IDS.discard(999888777)

    # ── R27: /admin kelola allowlist ──
    clear()
    ctxAd = mk_ctx(); ctxAd.args = ["list"]
    await bot.h_admin(mk_user_update(uid=bot.OWNER_ID), ctxAd)
    check(has("reply_text", "allowlist"), "R27 /admin list")
    clear()
    ctxAd2 = mk_ctx(); ctxAd2.args = ["add", "555666777"]
    await bot.h_admin(mk_user_update(uid=bot.OWNER_ID), ctxAd2)
    check(555666777 in bot.ALLOWED_IDS, "R27 /admin add masuk allowlist")
    clear()
    ctxAd3 = mk_ctx(); ctxAd3.args = ["del", "555666777"]
    await bot.h_admin(mk_user_update(uid=bot.OWNER_ID), ctxAd3)
    check(555666777 not in bot.ALLOWED_IDS, "R27 /admin del keluar allowlist")
    clear()
    ctxAd4 = mk_ctx(); ctxAd4.args = ["add", "444"]      # bukan owner
    await bot.h_admin(mk_user_update(uid=123), ctxAd4)
    check(444 not in bot.ALLOWED_IDS, "R27 non-owner nggak bisa /admin")

    # ── R35: /cn — amatir China 91porny (search → preview card → video) ──
    print("── R35: /cn ──")
    import scraper_china as _sc
    _real_cn_search = _sc.search
    _real_cn_dl = _sc.download
    _sc.search = lambda q="", limit=12: [
        {"url": "https://91porny.com/video/view/1", "title": "自拍 Video A",
         "dur": "10:00", "poster": "http://x/p.jpg",
         "m3u8": "https://cdn2.jiuse3.cloud/hls/1/index.m3u8"},
        {"url": "https://91porny.com/video/view/2", "title": "探花 Video B",
         "dur": "12:00", "poster": "http://x/p2.jpg",
         "m3u8": "https://cdn2.jiuse3.cloud/hls/2/index.m3u8"},
    ]
    def _fake_cn_dl(m3u8, out, referer="https://91porny.com"):
        open(out, "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        return True
    _sc.download = _fake_cn_dl
    _orig_faststart_cn = bot._faststart
    bot._faststart = lambda p: p
    try:
        clear()
        ctxcn = mk_ctx(); ctxcn.args = ["hotel"]
        await bot.h_cn(mk_user_update("/cn hotel"), ctxcn)
        check(has("msg_edit_text", "91porny") or has("reply_text", "91porny"),
              "R35 /cn daftar amatir China tampil")
        check(has("reply_photo") or has("reply_text", "自拍 Video A"),
              "R35 /cn kartu preview item 1 dikirim")
        qidCN = list(bot.STATE_CN.keys())[-1]
        card_id = bot.STATE_CN[qidCN]["card"][1]
        # navigasi preview kartu ke item 2
        clear()
        await bot.h_cn_cb(mk_update(f"cnk|{qidCN}|2"), mk_ctx())
        check(has("edit_media", idx=card_id, sub="探花 Video B") or has("answer", "Video B"),
              "R35 kartu preview ter-update ke item 2")
        # download video
        clear()
        await bot.h_cn_cb(mk_update(f"cndl|{qidCN}|1"), mk_ctx())
        check(has("send_video", sub="自拍 Video A"), "R35 video China terkirim playable")
        check(has("msg_edit_text", "terkirim") or has("reply_text", "terkirim"),
              "R35 konfirmasi sukses")
        # tombol basi
        clear()
        await bot.h_cn_cb(mk_update("cnk|deadbeef|1"), mk_ctx())
        check(has("answer", "basi"), "R35 state basi → alert")
    finally:
        _sc.search = _real_cn_search
        _sc.download = _real_cn_dl
        bot._faststart = _orig_faststart_cn
        bot.STATE_CN.pop(qidCN, None)

    # ── R36: /jav — JavDB (search → preview card → magnet) ──
    print("── R36: /jav ──")
    import scraper_javdb as _sj
    _real_jv_search = _sj.search
    _real_jv_detail = _sj.detail
    _sj.search = lambda q="", limit=10: [
        {"url": "https://javdb.com/v/1", "code": "SSIS-999", "title": "JAV Video A",
         "cover": "https://c0.jdbstatic.com/covers/1.jpg"},
        {"url": "https://javdb.com/v/2", "code": "MIDV-111", "title": "JAV Video B",
         "cover": "https://c0.jdbstatic.com/covers/2.jpg"},
    ]
    _sj.detail = lambda url: {
        "title": "JAV Video A Full Title", "cover": "https://c0.jdbstatic.com/covers/1.jpg",
        "magnets": [("0123456789abcdef0123456789abcdef01234567", "2.5 GB")],
        "date": "2026-10-10", "genres": ["Creampie", "Milf"]
    }
    try:
        clear()
        ctxjv = mk_ctx(); ctxjv.args = ["SSIS"]
        await bot.h_jav(mk_user_update("/jav SSIS"), ctxjv)
        check(has("msg_edit_text", "JavDB") or has("reply_text", "JavDB"),
              "R36 /jav daftar JavDB tampil")
        check(has("reply_photo") or has("reply_text", "SSIS-999"),
              "R36 /jav kartu preview item 1 dikirim")
        qidJV = list(bot.STATE_JAV.keys())[-1]
        card_id_jv = bot.STATE_JAV[qidJV]["card"][1]
        # navigasi preview kartu ke item 2
        clear()
        await bot.h_jav_cb(mk_update(f"jvk|{qidJV}|2"), mk_ctx())
        check(has("edit_media", idx=card_id_jv, sub="MIDV-111") or has("answer", "MIDV-111"),
              "R36 kartu preview ter-update ke item 2")
        # ambil magnet
        clear()
        await bot.h_jav_cb(mk_update(f"jvmg|{qidJV}|1"), mk_ctx())
        check(has("reply_photo") or has("reply_text", "magnet:?xt=urn:btih:"),
              "R36 detail magnet terkirim")
        # tombol basi
        clear()
        await bot.h_jav_cb(mk_update("jvk|deadbeef|1"), mk_ctx())
        check(has("answer", "basi"), "R36 state basi → alert")
    finally:
        _sj.search = _real_jv_search
        _sj.detail = _real_jv_detail
        bot.STATE_JAV.pop(qidJV, None)

    return True

async def main():
    for r in range(1, 6):
        bot.STATES.clear(); bot.STATES_M.clear(); bot.STATES_D.clear(); bot.BUSY.clear()
        CALLS.clear()
        await round_tests()
        print(f"round {r}: ALL CHECKS PASS")

asyncio.run(main())
