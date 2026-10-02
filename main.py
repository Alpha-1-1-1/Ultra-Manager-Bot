import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# Auto-load Kaggle secrets if running on Kaggle
try:
    from kaggle_secrets import UserSecretsClient
    _user_secrets = UserSecretsClient()
    for _key in ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"]:
        if not os.getenv(_key):
            try:
                _val = _user_secrets.get_secret(_key)
                if _val:
                    os.environ[_key] = str(_val).strip()
            except Exception:
                pass
except Exception:
    pass

# Load environment variables from .env if present
load_dotenv()

# Render / Cloud Web Service Health Check Server
class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Ultra Manager Bot is online and running healthy!")

    def log_message(self, format, *args):
        # Silence HTTP access logs to keep terminal clean
        pass

def start_render_health_server():
    """Binds to Render's $PORT to allow deploying on Render's 100% Free Web Service tier."""
    port_str = os.getenv("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
        logging.info(f"Render health-check server listening on port {port}...")
        server.serve_forever()
    except Exception as e:
        logging.error(f"Failed to start health server: {e}")

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context) -> None:
    user = update.effective_user
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
        print("Error: TELEGRAM_BOT_TOKEN environment variable not properly set in .env or Cloud Secrets.")
        return

    # Start health server in background thread for Render.com Free Tier support
    if os.getenv("PORT"):
        threading.Thread(target=start_render_health_server, daemon=True).start()

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
