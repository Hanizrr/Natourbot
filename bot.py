import os
import re
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

# ========= ENV =========
TOKEN = "8324528568:AAENEljiKuxfPcPVHeB-pq9Nv_WJd3Ic0HU"
OWNER_ID = int(os.getenv("2118872778", "0"))

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
link INTEGER DEFAULT 0,
full INTEGER DEFAULT 0,
photo INTEGER DEFAULT 0,
video INTEGER DEFAULT 0,
voice INTEGER DEFAULT 0,
file INTEGER DEFAULT 0,
sticker INTEGER DEFAULT 0,
text INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_admins (
chat_id INTEGER,
user_id INTEGER
)
""")

conn.commit()

# ========= HELPERS =========

def is_admin(user_id, chat_id):
    if user_id == OWNER_ID:
        return True

    cursor.execute(
        "SELECT 1 FROM bot_admins WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    return cursor.fetchone() is not None


async def get_target_user(update: Update, context):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id

    parts = update.message.text.split()
    if len(parts) < 2:
        return None

    arg = parts[1]

    if arg.isdigit():
        return int(arg)

    if arg.startswith("@"):
        try:
            user = await context.bot.get_chat(arg)
            return user.id
        except:
            return None

    return None


def parse_time(text):
    match = re.search(r"(\d+)([mhd])", text)
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


# ========= MAIN HANDLER =========

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.lower().strip()
    parts = text.split()
    cmd = parts[0]

    # ===== Locks Check =====
    cursor.execute("""
    SELECT link, full, photo, video, voice, file, sticker, text
    FROM locks WHERE chat_id=?
    """, (chat_id,))
    row = cursor.fetchone()

    if row:
        link_lock, full_lock, photo_lock, video_lock, voice_lock, file_lock, sticker_lock, text_lock = row
        msg = update.message

        if full_lock and not is_admin(user_id, chat_id):
            await msg.delete()
            return

        if link_lock and msg.text and ("http" in msg.text or "t.me" in msg.text):
            await msg.delete()
            return

        if photo_lock and msg.photo:
            await msg.delete()
            return

        if video_lock and msg.video:
            await msg.delete()
            return

        if voice_lock and msg.voice:
            await msg.delete()
            return

        if file_lock and msg.document:
            await msg.delete()
            return

        if sticker_lock and msg.sticker:
            await msg.delete()
            return

        if text_lock and msg.text and not is_admin(user_id, chat_id):
            await msg.delete()
            return

    # ===== OWNER COMMANDS =====

    if cmd == "promote" and user_id == OWNER_ID:
        target = await get_target_user(update, context)
        if target:
            cursor.execute("INSERT INTO bot_admins VALUES (?, ?)", (chat_id, target))
            conn.commit()
            await update.message.reply_text("Bot admin added")
        return

    if cmd == "demote" and user_id == OWNER_ID:
        target = await get_target_user(update, context)
        if target:
            cursor.execute("DELETE FROM bot_admins WHERE chat_id=? AND user_id=?", (chat_id, target))
            conn.commit()
            await update.message.reply_text("Bot admin removed")
        return

    if cmd == "admins":
        if not is_admin(user_id, chat_id):
            return

        cursor.execute("SELECT user_id FROM bot_admins WHERE chat_id=?", (chat_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No bot admins")
            return

        text_list = "Bot Admins:\n"
        for r in rows:
            text_list += f"- {r[0]}\n"

        await update.message.reply_text(text_list)
        return

    # ===== ADMIN REQUIRED =====
    if not is_admin(user_id, chat_id):
        return

    # ========= USER MANAGEMENT =========

    if cmd == "ban":
        target = await get_target_user(update, context)
        if target:
            await context.bot.ban_chat_member(chat_id, target)
            await update.message.reply_text("User banned")

    elif cmd == "unban":
        target = await get_target_user(update, context)
        if target:
            await context.bot.unban_chat_member(chat_id, target)
            await update.message.reply_text("User unbanned")

    elif cmd == "mute":
        target = await get_target_user(update, context)
        if not target:
            return

        delta = parse_time(text)
        until = datetime.now() + delta if delta else None

        await context.bot.restrict_chat_member(
            chat_id,
            target,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )

        await update.message.reply_text("User muted")

    elif cmd == "unmute":
        target = await get_target_user(update, context)
        if target:
            await context.bot.restrict_chat_member(
                chat_id,
                target,
                permissions=ChatPermissions(can_send_messages=True)
            )
            await update.message.reply_text("User unmuted")

    elif cmd == "warn":
        target = await get_target_user(update, context)
        if not target:
            return

        cursor.execute("SELECT count FROM warns WHERE user_id=? AND chat_id=?", (target, chat_id))
        row = cursor.fetchone()
        count = row[0] + 1 if row else 1

        if row:
            cursor.execute("UPDATE warns SET count=? WHERE user_id=? AND chat_id=?", (count, target, chat_id))
        else:
            cursor.execute("INSERT INTO warns VALUES (?, ?, ?)", (target, chat_id, count))

        conn.commit()

        if count >= 3:
            await context.bot.restrict_chat_member(
                chat_id,
                target,
                permissions=ChatPermissions(can_send_messages=False)
            )
            await update.message.reply_text("3 warns → user muted")
        else:
            await update.message.reply_text(f"Warn {count}/3")

    # ========= MEDIA LOCK COMMANDS =========

    elif text.startswith("lock "):
        lock_type = text.split()[1]
        valid = ["photo", "video", "voice", "file", "sticker", "text", "link", "chat"]

        if lock_type in valid:
            cursor.execute("INSERT OR IGNORE INTO locks (chat_id) VALUES (?)", (chat_id,))
            if lock_type == "chat":
                cursor.execute("UPDATE locks SET full=1 WHERE chat_id=?", (chat_id,))
            else:
                cursor.execute(f"UPDATE locks SET {lock_type}=1 WHERE chat_id=?", (chat_id,))
            conn.commit()
            await update.message.reply_text(f"{lock_type} locked")

    elif text.startswith("unlock "):
        lock_type = text.split()[1]
        valid = ["photo", "video", "voice", "file", "sticker", "text", "link", "chat"]

        if lock_type in valid:
            if lock_type == "chat":
                cursor.execute("UPDATE locks SET full=0 WHERE chat_id=?", (chat_id,))
            else:
                cursor.execute(f"UPDATE locks SET {lock_type}=0 WHERE chat_id=?", (chat_id,))
            conn.commit()
            await update.message.reply_text(f"{lock_type} unlocked")


# ========= WELCOME =========

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(f"Welcome {member.first_name}")


# ========= RUN =========

if not TOKEN:
    raise ValueError("Set TOKEN in Secrets")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

print("NatorBot Running...")
app.run_polling()
