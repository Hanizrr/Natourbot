import os
import re
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ========= ENV =========
TOKEN = os.getenv("8324528568:AAENEljiKuxfPcPVHeB-pq9Nv_WJd3Ic0HU")
OWNER_ID = int(os.getenv("2118872778", "0"))
FRIEND_ID = int(os.getenv("7913521214D", "0"))
ALLOWED_USERS = [2118872778, 7913521214D]

logging.basicConfig(level=logging.INFO)

# ========= DATABASE =========
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS warns (
    user_id INTEGER,
    chat_id INTEGER,
    count INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS locks (
    chat_id INTEGER PRIMARY KEY,
    photo INTEGER DEFAULT 0,
    video INTEGER DEFAULT 0,
    voice INTEGER DEFAULT 0,
    text INTEGER DEFAULT 0,
    link INTEGER DEFAULT 0,
    full INTEGER DEFAULT 0
)
""")

conn.commit()

# ========= HELPERS =========

def is_allowed(user_id):
    return user_id in ALLOWED_USERS

def parse_time(time_str):
    match = re.match(r"(\\d+)([mhd])", time_str)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)

async def log_deleted(context, chat, user, text, reason):
    msg = f"""
🗑 پیام حذف شد
👤 {user.first_name} ({user.id})
👥 {chat.title}
📌 دلیل: {reason}
🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📩 متن:
{text}
"""
    for admin in ALLOWED_USERS:
        try:
            await context.bot.send_message(admin, msg)
        except:
            pass

# ========= COMMANDS =========

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text("روی پیام ریپلای کن.")
    user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text("کاربر بن شد ✅")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not context.args:
        return
    user_id = int(context.args[0])
    await context.bot.unban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("کاربر آنبن شد ✅")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        return

    user = update.message.reply_to_message.from_user
    cursor.execute(
        "SELECT count FROM warns WHERE user_id=? AND chat_id=?",
        (user.id, update.effective_chat.id)
    )
    row = cursor.fetchone()

    if row:
        count = row[0] + 1
        cursor.execute(
            "UPDATE warns SET count=? WHERE user_id=? AND chat_id=?",
            (count, user.id, update.effective_chat.id)
        )
    else:
        count = 1
        cursor.execute(
            "INSERT INTO warns VALUES (?, ?, ?)",
            (user.id, update.effective_chat.id, count)
        )

    conn.commit()

    if count >= 3:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text("کاربر به دلیل ۳ اخطار میوت شد 🚫")
    else:
        await update.message.reply_text(f"اخطار ثبت شد ({count}/3)")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        return

    user = update.message.reply_to_message.from_user

    if context.args:
        delta = parse_time(context.args[0])
        if delta:
            until = datetime.now() + delta
            await context.bot.restrict_chat_member(
                update.effective_chat.id,
                user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            return await update.message.reply_text("میوت زمان‌دار شد ⏳")

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text("میوت دائمی شد 🚫")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(f"خوش اومدی {member.first_name} 🌿")

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.type == "private":
        return

    cursor.execute(
        "SELECT photo, video, voice, text, link, full FROM locks WHERE chat_id=?",
        (update.effective_chat.id,)
    )
    row = cursor.fetchone()
    if not row:
        return

    photo, video, voice, text_lock, link, full = row
    msg = update.message

    if full and msg.from_user.id not in ALLOWED_USERS:
        await msg.delete()
        return

    reason = None
    if photo and msg.photo:
        reason = "عکس"
    elif video and msg.video:
        reason = "ویدیو"
    elif voice and msg.voice:
        reason = "ویس"
    elif text_lock and msg.text:
        reason = "متن"
    elif link and msg.text and ("http" in msg.text or "t.me" in msg.text):
        reason = "لینک"

    if reason:
        await log_deleted(context, update.effective_chat, msg.from_user, msg.text or "-", reason)
        await msg.delete()

# ========= RUN =========

if not TOKEN:
    raise ValueError("TOKEN تنظیم نشده! در Secrets قرار بده.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("ban", ban_user))
app.add_handler(CommandHandler("unban", unban_user))
app.add_handler(CommandHandler("warn", warn_user))
app.add_handler(CommandHandler("mute", mute_user))

app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
app.add_handler(MessageHandler(filters.ALL, check_message))

print("Bot Running...")
app.run_polling()

