from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🤖 AI Chat", callback_data="menu_ai"),
            InlineKeyboardButton("🎬 Video Downloader", callback_data="menu_downloader"),
        ],
        [
            InlineKeyboardButton("🎵 Song Downloader", callback_data="menu_song"),
            InlineKeyboardButton("⏰ Reminders", callback_data="menu_reminders"),
        ],
        [
            InlineKeyboardButton("📈 Crypto Prices", callback_data="menu_crypto"),
            InlineKeyboardButton("📰 News Headlines", callback_data="menu_news"),
        ],
        [
            InlineKeyboardButton("📊 System Status", callback_data="menu_status"),
            InlineKeyboardButton("🛡️ Moderation", callback_data="menu_moderation"),
        ],
        [
            InlineKeyboardButton("📁 File Tools", callback_data="menu_files"),
            InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🤖 **Ultra Manager Bot Main Menu**\n\n"
        "Select a feature below to view details and commands:"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "menu_ai":
        response = (
            "🤖 **Gemini AI Assistant**\n\n"
            "• `/ai <question>` — Ask anything\n"
            "• Send a photo with `/ai <question>` in caption for visual analysis!"
        )
    elif data == "menu_downloader":
        response = (
            "🎬 **Video Downloader (yt-dlp)**\n\n"
            "• Just paste any video link in chat (YouTube, Shorts, TikTok, Instagram, X/Twitter)!\n"
            "• Shows thumbnail preview, resolution selection, audio extraction, sponsorblock & cut!"
        )
    elif data == "menu_song":
        response = (
            "🎵 **Song & Music Downloader**\n\n"
            "• Usage: `/song <song title or artist>`\n"
            "• Example: `/song Shape of You` or `/song Starboy`\n"
            "• Automatically finds the track and sends an MP3 with audio tags."
        )
    elif data == "menu_reminders":
        response = (
            "⏰ **Reminder System**\n\n"
            "• Usage: `/remind <time> <message>`\n"
            "• Examples:\n"
            "  - `/remind 30s Stretch arms`\n"
            "  - `/remind 15m Meeting starting`\n"
            "  - `/remind 2h Review documents`"
        )
    elif data == "menu_crypto":
        response = (
            "📈 **Crypto Price Tracker**\n\n"
            "• Usage: `/crypto [symbol]`\n"
            "• Examples: `/crypto btc`, `/crypto eth`, `/crypto sol`, `/crypto doge`\n"
            "• Real-time USD and INR prices with 24h change!"
        )
    elif data == "menu_news":
        response = (
            "📰 **Live News Headlines**\n\n"
            "• Usage: `/news [category]`\n"
            "• Categories: `/news tech`, `/news world`, `/news science`\n"
            "• Direct clickable headlines updated every few minutes."
        )
    elif data == "menu_status":
        response = (
            "📊 **System Resource Monitor**\n\n"
            "• Command: `/status`\n"
            "• Live metrics: CPU %, RAM usage, Disk space, and Bot uptime."
        )
    elif data == "menu_moderation":
        response = (
            "🛡️ **Group Moderation**\n\n"
            "• Add bot to your Telegram Group as Admin.\n"
            "• Auto-welcomes new members.\n"
            "• Admin commands: `/warn`, `/kick`, `/ban` (reply to user's message)."
        )
    elif data == "menu_files":
        response = (
            "📁 **File Converter & Tools**\n\n"
            "• Reply to any photo with `/convert png`, `/convert jpg`, or `/convert webp`."
        )
    elif data == "menu_help":
        response = (
            "ℹ️ **Ultra Manager Bot Command List**\n\n"
            "• `/menu` — Interactive menu\n"
            "• `<link>` or `/download <url>` — Video downloader\n"
            "• `/song <name>` — Download music\n"
            "• `/ai <text>` — Chat with Gemini 3.8 Flash\n"
            "• `/remind <time> <msg>` — Set reminders\n"
            "• `/crypto <coin>` — Live crypto prices\n"
            "• `/news <cat>` — News headlines\n"
            "• `/status` — System & bot health\n"
            "• `/convert <fmt>` — Image converter\n"
            "• `/warn` / `/kick` / `/ban` — Admin moderation"
        )
    else:
        response = "Unknown selection."

    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to Menu", callback_data="menu_back")]
    ])

    if data == "menu_back":
        await menu_command(update, context)
    else:
        await query.message.edit_text(response, reply_markup=back_keyboard, parse_mode="Markdown")
