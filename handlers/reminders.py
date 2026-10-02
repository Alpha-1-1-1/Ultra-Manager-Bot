import re
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def parse_time_string(time_str: str) -> int:
    """Parses time string like 10s, 5m, 2h into total seconds."""
    match = re.match(r"^(\d+)([smh])$", time_str.lower().strip())
    if not match:
        return None
    val, unit = match.groups()
    val = int(val)
    if unit == "s":
        return val
    elif unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    return None

async def reminder_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    text = job.data
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ **REMINDER ALERT**:\n\n{text}",
        parse_mode="Markdown"
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.job_queue:
        await update.message.reply_text("⚠️ JobQueue is not enabled in this bot installation.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "💡 **Usage**: `/remind <time> <message>`\n\n"
            "**Examples**:\n"
            "• `/remind 30s Take out trash`\n"
            "• `/remind 15m Meeting starting`\n"
            "• `/remind 1h Check emails`",
            parse_mode="Markdown"
        )
        return

    time_str = context.args[0]
    message_text = " ".join(context.args[1:])

    seconds = parse_time_string(time_str)
    if not seconds or seconds <= 0:
        await update.message.reply_text("❌ Invalid time format! Use format like `30s`, `15m`, `2h`.")
        return

    chat_id = update.effective_chat.id

    context.job_queue.run_once(
        reminder_callback,
        when=seconds,
        chat_id=chat_id,
        data=message_text,
        name=f"reminder_{chat_id}_{message_text[:10]}"
    )

    await update.message.reply_text(
        f"✅ Reminder set! I will remind you in **{time_str}** for:\n`{message_text}`",
        parse_mode="Markdown"
    )
