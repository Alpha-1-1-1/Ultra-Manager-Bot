import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcomes new users joining a group."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        welcome_text = (
            f"👋 Welcome to the group, [{member.first_name}](tg://user?id={member.id})!\n\n"
            "Please be respectful and follow group guidelines."
        )
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message sent by the user you want to warn.")
        return

    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "No reason provided."

    await update.message.reply_text(
        f"⚠️ **WARNING ISSUED**\n"
        f"User: [{target_user.first_name}](tg://user?id={target_user.id})\n"
        f"Reason: {reason}",
        parse_mode="Markdown"
    )

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message sent by the user you want to kick.")
        return

    target_user = update.message.reply_to_message.from_user
    chat = update.effective_chat

    try:
        await chat.ban_member(user_id=target_user.id)
        await chat.unban_member(user_id=target_user.id)  # Unban so they can re-join via invite link
        await update.message.reply_text(f"👢 Kicked [{target_user.first_name}](tg://user?id={target_user.id}) from the chat.", parse_mode="Markdown")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Failed to kick user: {e.message}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message sent by the user you want to ban.")
        return

    target_user = update.message.reply_to_message.from_user
    chat = update.effective_chat

    try:
        await chat.ban_member(user_id=target_user.id)
        await update.message.reply_text(f"🚫 Banned [{target_user.first_name}](tg://user?id={target_user.id}) permanently.", parse_mode="Markdown")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Failed to ban user: {e.message}")
