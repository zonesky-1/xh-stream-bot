"""Live E2E — semua command BARU dijalankan lewat handler asli + jaringan BENERAN.

FakeBot/FakeMsg nyimpen apa yang bakal dikirim ke Telegram tanpa nge-spam chat lu.
Network: TANPA mock — setiap scraper beneran manggil API/situsnya.
"""
import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bot  # noqa: E402  (import duluan, sebelum monkeypatch apapun)

CALLS = []
_mid = iter(range(90000, 99999)).__next__


class FakeMsg:
    def __init__(self, chat_id=7998819216):
        self.chat = types.SimpleNamespace(id=chat_id)
        self.message_id = _mid()
        self.text = ""
        self.reply_markup = None

    async def reply_text(self, text=None, **kw):
        CALLS.append(("reply_text", (text or "")[:120]))
        m = FakeMsg(self.chat.id); m.text = text or ""; return m

    async def reply_photo(self, photo=None, caption=None, **kw):
        CALLS.append(("reply_photo", str(photo)[:45], (caption or "")[:120]))
        m = FakeMsg(self.chat.id); m.text = caption or ""; return m

    async def edit_text(self, text=None, reply_markup=None, **kw):
        CALLS.append(("msg_edit_text", (text or "")[:120]))
        self.text = text or ""
        self.reply_markup = reply_markup

    async def reply_document(self, document=None, caption=None, **kw):
        CALLS.append(("reply_document", (caption or "")[:120]))
        m = FakeMsg(self.chat.id); m.text = caption or ""; return m


class FakeBot:
    async def send_photo(self, chat_id=None, photo=None, caption=None, **kw):
        CALLS.append(("send_photo", str(photo)[:45], (caption or "")[:120])); return FakeMsg()

    async def send_video(self, chat_id=None, video=None, caption=None, **kw):
        CALLS.append(("send_video", os.path.basename(str(video)), (caption or "")[:120])); return FakeMsg()

    async def send_media_group(self, chat_id=None, media=None, **kw):
        CALLS.append(("send_media_group", len(media))); return [FakeMsg()]

    async def send_message(self, chat_id=None, text=None, **kw):
        CALLS.append(("send_message", (text or "")[:120])); return FakeMsg()


class FakeCQ:
    def __init__(self, data, message):
        self.data = data
        self.message = message

    async def answer(self, text=None, show_alert=False):
        CALLS.append(("answer", (text or "")[:70]))

    async def edit_message_text(self, text=None, reply_markup=None, **kw):
        CALLS.append(("cq_edit_text", (text or "")[:120]))
        self.message.reply_markup = reply_markup
        self.message.text = text or ""


def mk_user(text, chat_id=7998819216):
    m = FakeMsg(chat_id)
    m.text = text
    u = types.SimpleNamespace(id=7998819216, full_name="Rapi", username="rapi")
    return types.SimpleNamespace(effective_user=u, effective_chat=m.chat,
                                 effective_message=m, message=m, callback_query=None)


def mk_ctx(args):
    return types.SimpleNamespace(bot=FakeBot(), args=args)


def last(tag, n=1):
    return [c for c in CALLS if c[0] == tag][-n:]


def has(tag, sub=""):
    return any(tag == c[0] and (not sub or sub in str(c[1:])) for c in CALLS)


def reset():
    CALLS.clear()


async def main():
    ok = fail = 0

    def check(cond, name, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✅ {name}")
        else:
            fail += 1
            print(f"  ❌ {name} {extra}")

    # ── /r34 (multi-sumber: rule34 + e621 + xbooru + e926) ──
    print("── /r34 multi-sumber ──")
    reset()
    try:
        await bot.h_r34(mk_user("/r34"), mk_ctx(["catgirl"]))
        check(has("reply_photo") or has("send_photo") or has("reply_text"),
              "r34 kirim hasil", str(CALLS[-2:]))
    except Exception as e:
        check(False, "r34", str(e)[:90])

    # ── /anime (Kitsu) ──
    print("── /anime ──")
    reset()
    try:
        await bot.h_anime(mk_user("/anime"), mk_ctx(["solo", "leveling"]))
        check(has("reply_photo") or has("reply_text"),
              "anime info terkirim", str(CALLS[-2:]))
    except Exception as e:
        check(False, "anime", str(e)[:90])

    # ── /meme ──
    print("── /meme ──")
    reset()
    try:
        await bot.h_meme(mk_user("/meme"), mk_ctx([]))
        check(has("reply_photo") or has("reply_text"), "meme terkirim", str(CALLS[-2:]))
    except Exception as e:
        check(False, "meme", str(e)[:90])

    # ── /wsg (4chan) ──
    print("── /wsg ──")
    reset()
    try:
        await bot.h_wsg(mk_user("/wsg"), mk_ctx([]))
        check(has("reply_photo") or has("reply_text"), "wsg terkirim", str(CALLS[-2:]))
    except Exception as e:
        check(False, "wsg", str(e)[:90])

    # ── /mdx (MangaDex) ──
    print("── /mdx ──")
    reset()
    try:
        await bot.h_mdx(mk_user("/mdx"), mk_ctx(["netorare"]))
        check(has("reply_text", "MangaDex") or has("msg_edit_text", "MangaDex"),
              "mdx daftar judul", str(CALLS[-2:]))
        qid = bot.STATE_MDX and list(bot.STATE_MDX)[-1]
        check(bool(qid), "mdx state tersimpan", str(bot.STATE_MDX)[:60])
    except Exception as e:
        check(False, "mdx", str(e)[:90])

    # ── /jav (JavDB) ──
    print("── /jav ──")
    reset()
    try:
        await bot.h_jav(mk_user("/jav"), mk_ctx(["SSIS-001"]))
        check(has("reply_text", "JavDB") or has("msg_edit_text", "JavDB"),
              "jav daftar judul", str(CALLS[-2:]))
    except Exception as e:
        check(False, "jav", str(e)[:90])

    # ── /ptx (PornTrex) ──
    print("── /ptx ──")
    reset()
    try:
        await bot.h_ptx(mk_user("/ptx"), mk_ctx(["teen"]))
        check(has("reply_text", "PornTrex") or has("msg_edit_text", "PornTrex"),
              "ptx daftar judul", str(CALLS[-2:]))
    except Exception as e:
        check(False, "ptx", str(e)[:90])

    print(f"\n═══ LIVE E2E: {ok} lolos, {fail} gagal ═══")
    return fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
