# main.py
import logging
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes

import requests

# إعدادات محلية
from config import BOT_TOKEN, OWNER_ID, TIMEZONE, LAT, LON, METHOD, RENDER_EXTERNAL_URL, PORT
import database as db
from utils import close_topic_or_lock, reopen_topic_or_unlock

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# الصلوات وأسماؤها العربية
PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
AR_PRAYER = {"Fajr": "الفجر", "Dhuhr": "الظهر", "Asr": "العصر", "Maghrib": "المغرب", "Isha": "العشاء"}
DURATIONS = {"Fajr": 15, "Dhuhr": 15, "Asr": 15, "Maghrib": 15, "Isha": 15}

DUA_NIGHT = "بِاسْمِكَ رَبِّي وَضَعْتُ جَنْبِي، وَبِكَ أَرْفَعُهُ، فَإِنْ أَمْسَكْتَ نَفْسِي فَارْحَمْهَا، وَإِنْ أَرْسَلْتَهَا فَاحْفَظْهَا، بِمَا تَحْفَظُ بِهِ عِبَادَكَ الصَّالِحِينَ"
DUA_MORNING = "اللَّهُمَّ إنِّي أصبَحتُ أنِّي أُشهِدُك، وأُشهِدُ حَمَلةَ عَرشِكَ، ومَلائِكَتَك، وجميعَ خَلقِكَ: بأنَّك أنتَ اللهُ لا إلهَ إلَّا أنتَ، وَحْدَك لا شريكَ لكَ، وأنَّ مُحمَّدًا عبدُكَ ورسولُكَ"

application = Application.builder().token(BOT_TOKEN).build()
tz = ZoneInfo(TIMEZONE)

def fetch_prayer_times(d: date):
    url = f"https://api.aladhan.com/v1/timings/{d.isoformat()}?latitude={LAT}&longitude={LON}&method={METHOD}&timezonestring={TIMEZONE}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()["data"]["timings"]
    out = {}
    for name in PRAYERS:
        hh, mm = data[name].split(":")[:2]
        out[name] = datetime.combine(d, time(int(hh), int(mm)), tzinfo=tz)
    return out

# job: تفتح الشات عند موعد معين (تُستدعى عبر job_queue.run_once)
async def open_job(ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = ctx.job.data.get("chat_id")
    if chat_id:
        groups = db.get_groups_db()
        thread_id = groups.get(str(chat_id), {}).get("thread_id")
        ok = await reopen_topic_or_unlock(chat_id, thread_id, ctx, "✅ تم فتح الموضوع / الدردشة")
        if ok:
            db.update_state_db(chat_id, False)

async def scheduler_job(ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(tz)
    today = now.date()

    groups = db.get_groups_db()
    try:
        prayer_times = fetch_prayer_times(today)
    except Exception as e:
        logging.exception("خطأ عند جلب أوقات الصلاة:")
        prayer_times = {}

    for chat_key, info in groups.items():
        try:
            chat_id = int(info["chat_id"])
        except Exception:
            continue
        thread_id = info.get("thread_id")
        st = db.get_state_db(chat_id)
        closed = st.get("closed", False)
        last_action = st.get("last_action", 0)

        # تجنّب التدخّل لو مستخدم غيّر الحالة يدويًا قبل قليل (10 ثواني)
        if int(__import__("time").time()) - last_action < 10:
            continue

        # 1) إغلاق أثناء الصلاة إذا دخلنا ضمن المدّة
        in_prayer = False
        for pname, start in prayer_times.items():
            end = start + timedelta(minutes=DURATIONS.get(pname, 20))
            if start <= now < end:
                in_prayer = True
                if not closed:
                    text = f"🔒 سيتم غلق الموضوع/الشات 🕌 لصلاة {AR_PRAYER.get(pname, pname)}"
                    ok = await close_topic_or_lock(chat_id, thread_id, ctx, text)
                    if ok:
                        db.update_state_db(chat_id, True)
                        # جدولة فتح عند نهاية الصلاة
                        delay = (end - now).total_seconds()
                        ctx.job_queue.run_once(open_job, when=delay, data={"chat_id": chat_id})
                break

        # 2) إغلاق ليلي عند منتصف الليل (00:00) + إرسال دعاء النوم
        if now.hour == 0 and now.minute == 0:
            if not closed:
                text = f"🌙 دعاء النوم: {DUA_NIGHT}"
                ok = await close_topic_or_lock(chat_id, thread_id, ctx, text)
                if ok:
                    db.update_state_db(chat_id, True)
                    # جدولة الفتح الساعة 05:00
                    open_time = datetime.combine(today, time(5,0), tzinfo=tz)
                    if now >= open_time:
                        open_time += timedelta(days=1)
                    delay = (open_time - now).total_seconds()
                    ctx.job_queue.run_once(open_job, when=delay, data={"chat_id": chat_id})

        # 3) فتح صباحي عند 05:00 (وإرسال دعاء الصباح)
        if now.hour == 5 and now.minute == 0:
            if closed and not in_prayer:
                text = f"☀️ دعاء الصباح: {DUA_MORNING}"
                ok = await reopen_topic_or_unlock(chat_id, thread_id, ctx, text)
                if ok:
                    db.update_state_db(chat_id, False)

        # 4) إذا ليس وقت صلاة ولا نافذة ليلية والشات مغلق -> افتح
        if not in_prayer and not (0 <= now.hour < 5):
            if closed:
                ok = await reopen_topic_or_unlock(chat_id, thread_id, ctx, "✅ سيتم فتح الموضوع — انتهت نافذة الإغلاق أو الصلاة")
                if ok:
                    db.update_state_db(chat_id, False)

# ===================== أوامر البوت =====================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 السلام عليكم\n\n"
        "الأوامر:\n"
        "/bind - ربط القروب (أدمن مصرح)\n"
        "/testclose - إغلاق تجريبي (أدمن)\n"
        "/testopen - فتح تجريبي (أدمن)\n"
        "/times - عرض أوقات الصلاة (مقيد للأدمن)\n"
        "/list_groups - عرض القروبات المرتبطة (للمالك)\n"
        "/add_admin <USER_ID> - إضافة أدمن (للمالك)\n"
        "/remove_admin <USER_ID> - إزالة أدمن (للمالك)\n"
    )

async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not (user_id == OWNER_ID or db.is_admin_db(user_id)):
        return await update.message.reply_text("⚠️ ليس لديك صلاحية استخدام هذا الأمر.")
    chat_id = update.effective_chat.id
    thread_id = getattr(update.effective_message, "message_thread_id", None)
    db.add_group_db(chat_id, thread_id)
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"✅ تم ربط القروب {chat_id} thread_id={thread_id}")
    except Exception:
        pass
    if thread_id:
        await update.message.reply_text(f"✅ تم ربط القروب وموضوع forum (thread_id={thread_id}). سيتم التحكم على هذا الموضوع.")
    else:
        await update.message.reply_text("✅ تم ربط القروب بدون topic. سيعمل fallback على صلاحيات الشات.")

async def testclose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not (user_id == OWNER_ID or db.is_admin_db(user_id)):
        return await update.message.reply_text("⚠️ هذا الأمر للأدمن المصرح فقط.")
    chat_id = update.effective_chat.id
    groups = db.get_groups_db()
    thread_id = groups.get(str(chat_id), {}).get("thread_id")
    db.update_state_db(chat_id, True)  # mark manual action
    text = "🔒 سيتم غلق الموضوع/الشات (تجريبي)"
    ok = await close_topic_or_lock(chat_id, thread_id, context, text)
    if ok:
        await update.message.reply_text("✅ تم تنفيذ إغلاق تجريبي.")
    else:
        await update.message.reply_text("❌ فشل تنفيذ إغلاق تجريبي. تأكد أن البوت مشرف وله الصلاحيات.")

async def testopen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not (user_id == OWNER_ID or db.is_admin_db(user_id)):
        return await update.message.reply_text("⚠️ هذا الأمر للأدمن المصرح فقط.")
    chat_id = update.effective_chat.id
    groups = db.get_groups_db()
    thread_id = groups.get(str(chat_id), {}).get("thread_id")
    db.update_state_db(chat_id, False)
    ok = await reopen_topic_or_unlock(chat_id, thread_id, context, "✅ سيتم فتح الموضوع/الشات (تجريبي)")
    if ok:
        await update.message.reply_text("✅ تم تنفيذ فتح تجريبي.")
    else:
        await update.message.reply_text("❌ فشل تنفيذ فتح تجريبي. تأكد أن البوت مشرف وله الصلاحيات.")

async def list_groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    groups = db.get_groups_db()
    if not groups:
        return await update.message.reply_text("⚠️ لا توجد قروبات مضافة.")
    keyboard = [[InlineKeyboardButton(f"قروب: {g} - thread:{groups[g].get('thread_id')}", callback_data=f"group_{g}")] for g in groups.keys()]
    await context.bot.send_message(chat_id=OWNER_ID, text="📋 القروبات/الموضوعات المرتبطة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) != 1:
        return await update.message.reply_text("⚠️ استعمل /add_admin <USER_ID>")
    new_admin = int(context.args[0])
    db.add_admin_db(new_admin)
    await update.message.reply_text(f"✅ تم إضافة {new_admin} كأدمن.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) != 1:
        return await update.message.reply_text("⚠️ استعمل /remove_admin <USER_ID>")
    rem_admin = int(context.args[0])
    db.remove_admin_db(rem_admin)
    await update.message.reply_text(f"✅ تم إزالة {rem_admin} من الأدمنية.")

async def times_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not (user_id == OWNER_ID or db.is_admin_db(user_id)):
        return await update.message.reply_text("⚠️ هذا الأمر للأدمن المصرح فقط.")
    today = datetime.now(tz).date()
    try:
        times = fetch_prayer_times(today)
    except Exception as e:
        logging.exception("خطأ عند جلب أوقات الصلاة:")
        return await update.message.reply_text(f"خطأ عند جلب أوقات الصلاة: {e}")
    msg = f"🕌 أوقات الصلاة ليوم {today.strftime('%d-%m-%Y')}:\n"
    for name, dt in times.items():
        msg += f"{AR_PRAYER.get(name, name)}: {dt.strftime('%H:%M')}\n"
    await update.message.reply_text(msg)

# new helper: copy a message (media or text) into a single group/topic
async def copy_to_group(context, from_chat_id, from_message_id, dest_chat_id, dest_thread_id=None):
    """
    Copy a message by message_id from from_chat_id into dest_chat_id.
    If dest_thread_id provided, will copy into that forum topic.
    Returns (True, None) on success, (False, error_str) on failure.
    """
    try:
        kwargs = {
            "chat_id": dest_chat_id,
            "from_chat_id": from_chat_id,
            "message_id": from_message_id,
        }
        if dest_thread_id is not None:
            kwargs["message_thread_id"] = dest_thread_id
        await context.bot.copy_message(**kwargs)
        return True, None
    except Exception as e:
        return False, str(e)

# replacement announce_all that supports media (reply-copy) and text
async def announce_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /announce <text>  OR reply to a message (any media) with /announce -> broadcast to all bound groups/topics
    Owner-only and works only in private chat (DM).
    """
    # Ensure DM and owner
    if update.effective_chat.type != "private":
        return await update.message.reply_text("هذا الأمر يعمل فقط في رسائل خاصة (DM) مع البوت.")
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⚠️ فقط صاحب البوت يمكنه استعمال هذا الأمر.")

    # If user replied to a message — we will copy that message (works for media)
    if update.message.reply_to_message:
        source_msg = update.message.reply_to_message
        from_chat_id = source_msg.chat_id
        from_message_id = source_msg.message_id

        groups = db.get_groups_db()
        if not groups:
            return await update.message.reply_text("⚠️ لا توجد قروبات مرتبطة لإرسال الإعلان.")

        sent = 0
        failed = 0
        errors = []
        for g_str, info in list(groups.items()):
            try:
                dest_chat_id = int(g_str)
            except Exception:
                failed += 1
                errors.append(f"bad chat id: {g_str}")
                continue
            dest_thread_id = info.get("thread_id")

            ok, err = await copy_to_group(context, from_chat_id, from_message_id, dest_chat_id, dest_thread_id)
            if ok:
                sent += 1
            else:
                failed += 1
                errors.append(f"{dest_chat_id}: {err}")
            # small delay to reduce rate-limit risks
            await asyncio.sleep(0.07)

        summary = f"📣 تم إرسال الإعلان إلى {sent} قروب(قروبات). فشل: {failed}."
        if errors and len(errors) <= 8:
            summary += "\n\nErrors:\n" + "\n".join(errors)
        elif errors:
            summary += f"\n\nErrors: {len(errors)} (use logs for details)."

        return await update.message.reply_text(summary)

    # Otherwise: use command text args (plain text announcement)
    text = " ".join(context.args).strip()
    if not text:
        return await update.message.reply_text("⚠️ الرجاء إرسال نص الإعلان أو الرد على رسالة (وسائط أو نص) ثم استخدام /announce")

    groups = db.get_groups_db()
    if not groups:
        return await update.message.reply_text("⚠️ لا توجد قروبات مرتبطة لإرسال الإعلان.")

    sent = 0
    failed = 0
    for g_str, info in list(groups.items()):
        try:
            chat_id = int(g_str)
        except Exception:
            failed += 1
            continue
        thread_id = info.get("thread_id")
        try:
            if thread_id:
                await context.bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
            else:
                await context.bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except Exception as e:
            print(f"announce_all(text): failed to send to {chat_id} (thread {thread_id}): {e}")
            failed += 1
        await asyncio.sleep(0.06)

    return await update.message.reply_text(f"📣 تم إرسال الإعلان إلى {sent} قروب(قروبات). فشل: {failed}.")

# asyn------------------------ close_all -------------------------

async def close_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/close_all  - owner DM only: close all topics or fallback to chat permissions"""
    if update.effective_chat.type != "private":
        return await update.message.reply_text("هذا الأمر يعمل فقط في رسائل خاصة (DM).")
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⚠️ فقط صاحب البوت يمكنه استعمال هذا الأمر.")

    groups = db.get_groups_db()
    if not groups:
        return await update.message.reply_text("⚠️ لا توجد قروبات مرتبطة.")

    closed = 0
    failed = 0
    for g_str, info in list(groups.items()):
        try:
            chat_id = int(g_str)
        except Exception:
            failed += 1
            continue
        thread_id = info.get("thread_id")
        try:
            if thread_id:
                # try to close forum topic async
                await context.bot.send_message(chat_id=chat_id, text="🔒 سيتم إغلاق الموضوع (إدارة مركزية).", message_thread_id=thread_id)
                await context.bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
                db.update_state_db(chat_id, True) 
            else:
                await context.bot.send_message(chat_id=chat_id, text="🔒 سيتم إغلاق الشات (إدارة مركزية).")
                await context.bot.set_chat_permissions(chat_id=chat_id, permissions=ChatPermissions(can_send_messages=False))
                db.update_state_db(chat_id, True) 
            closed += 1
        except Exception as e:
            print(f"close_all_cmd: failed for {chat_id}/{thread_id}: {e}")
            failed += 1
        await asyncio.sleep(0.06)

    return await update.message.reply_text(f"🔒 انتهى: تم إغلاق {closed}، فشل: {failed}.")

# asyn------------------------ open_all -------------------------

async def open_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/open_all - owner DM only: open all topics or restore permissions"""
    if update.effective_chat.type != "private":
        return await update.message.reply_text("هذا الأمر يعمل فقط في رسائل خاصة (DM).")
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⚠️ فقط صاحب البوت يمكنه استعمال هذا الأمر.")

    groups = db.get_groups_db()
    if not groups:
        return await update.message.reply_text("⚠️ لا توجد قروبات مرتبطة.")

    opened = 0
    failed = 0
    for g_str, info in list(groups.items()):
        try:
            chat_id = int(g_str)
        except Exception:
            failed += 1
            continue
        thread_id = info.get("thread_id")
        try:
            if thread_id:
                await context.bot.send_message(chat_id=chat_id, text="✅ سيتم فتح الموضوع (إدارة مركزية).", message_thread_id=thread_id)
                await context.bot.reopen_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
                db.update_state_db(chat_id, False)
            else:
                await context.bot.send_message(chat_id=chat_id, text="✅ سيتم فتح الشات (إدارة مركزية).")
                await context.bot.set_chat_permissions(chat_id=chat_id, permissions=ChatPermissions(
                    can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True))
                db.update_state_db(chat_id, False)
            opened += 1
        except Exception as e:
            print(f"open_all_cmd: failed for {chat_id}/{thread_id}: {e}")
            failed += 1
        await asyncio.sleep(0.06)

    return await update.message.reply_text(f"✅ انتهى: تم فتح {opened}، فشل: {failed}.")



# تسجيل handlers وتشغيل الـ job_queue
def main():
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(CommandHandler("testclose", testclose))
    application.add_handler(CommandHandler("testopen", testopen))
    application.add_handler(CommandHandler("list_groups", list_groups_cmd))
    application.add_handler(CommandHandler("add_admin", add_admin))
    application.add_handler(CommandHandler("remove_admin", remove_admin))
    application.add_handler(CommandHandler("times", times_cmd))
    application.add_handler(CommandHandler("announce", announce_all))
    application.add_handler(CommandHandler("close_all", close_all_cmd))
    application.add_handler(CommandHandler("open_all", open_all_cmd))


    # job_queue: شغّل scheduler_job كل 60 ثانية
    application.job_queue.run_repeating(scheduler_job, interval=60, first=5)

    # webhook
    if not RENDER_EXTERNAL_URL:
        logging.error("RENDER_EXTERNAL_URL not set")
        raise SystemExit(1)
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"
    logging.info("Setting webhook to: %s", webhook_url)
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=f"webhook/{BOT_TOKEN}",
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
