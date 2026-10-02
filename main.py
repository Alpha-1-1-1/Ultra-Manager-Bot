import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from database.db import init_db, log_user
from handlers.menu import menu_command, menu_callback_handler
from handlers.ai_chat import ai_command
from handlers.reminders import remind_command
from handlers.moderation import welcome_new_member, warn_user, kick_user, ban_user
from handlers.file_utils import convert_image_command
from handlers.downloader import (
    download_video_command,
    cut_command,
    downloader_callback_handler,
    link_detector_handler,
)
from handlers.system_monitor import status_command
from handlers.music import song_command
from handlers.crypto import crypto_command
from handlers.news import news_command

# Load environment variables
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context) -> None:
    user = update.effective_user
    # Record user in SQLite database
    log_user(user.id, user.username, user.first_name)

    welcome_msg = (
        f"👋 **Hello {user.first_name}!**\n\n"
        "Welcome to **Ultra Manager Bot**! 🚀\n\n"
        "✨ **What I can do**:\n"
        "• 🎬 **Video Downloader**: Paste any link (YouTube, Shorts, TikTok, Instagram, X)!\n"
        "• 🎵 **Song Downloader**: `/song <name>` for MP3 tracks\n"
        "• 🤖 **Gemini AI**: `/ai <question>` or send photos with `/ai`\n"
        "• 📈 **Crypto Tracker**: `/crypto btc` (USD & INR prices)\n"
        "• 📰 **Live News**: `/news tech` for breaking headlines\n"
        "• 📊 **System Monitor**: `/status` for CPU/RAM/Disk stats\n"
        "• ⏰ **Reminders**: `/remind 10m Check updates`\n"
        "• 🛡️ **Group Moderation**: Auto-welcome, `/warn`, `/kick`, `/ban`\n"
        "• 📁 **Image Converter**: Reply to photo with `/convert png`\n\n"
        "Type `/menu` to open the interactive menu!"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        print("Error: TELEGRAM_BOT_TOKEN environment variable not properly set in .env")
        return

    # Initialize SQLite database
    init_db()

    # Build Application with JobQueue enabled
    app = ApplicationBuilder().token(token).build()

    # Base commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))

    # Downloader Callbacks & Handlers
    app.add_handler(CallbackQueryHandler(downloader_callback_handler, pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(menu_callback_handler))

    # AI Feature
    app.add_handler(CommandHandler("ai", ai_command))

    # Video Downloader (yt-dlp) Commands & Auto Link Detector
    app.add_handler(CommandHandler("download", download_video_command))
    app.add_handler(CommandHandler("cut", cut_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r"https?://[^\s]+"), link_detector_handler))

    # Music / Song Downloader
    app.add_handler(CommandHandler("song", song_command))

    # Crypto & News Feeds
    app.add_handler(CommandHandler("crypto", crypto_command))
    app.add_handler(CommandHandler("news", news_command))

    # System Monitor
    app.add_handler(CommandHandler("status", status_command))

    # Reminder Feature
    app.add_handler(CommandHandler("remind", remind_command))

    # Moderation Feature
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # File Tools Feature
    app.add_handler(CommandHandler("convert", convert_image_command))

    print("🚀 Ultra Manager Bot is running with all features active...")
    app.run_polling()

if __name__ == "__main__":
    main()
