import os
import glob
import logging
import asyncio
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
import yt_dlp
from database.db import log_download

logger = logging.getLogger(__name__)

async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Searches YouTube and downloads audio MP3 by song name: /song <title>."""
    if not context.args:
        await update.message.reply_text(
            "🎵 **Usage**: `/song <song name or artist>`\n\n"
            "**Examples**:\n"
            "• `/song Shape of You`\n"
            "• `/song Starboy The Weeknd`\n"
            "• `/song Arijit Singh Tum Hi Ho`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🔍 Searching YouTube for: `{query}`...", parse_mode="Markdown")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "default_search": "ytsearch1",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            # Bypasses cloud datacenter IP blocks
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "mweb"]
                }
            },
        }

        loop = asyncio.get_event_loop()
        try:
            def _search_and_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(query, download=True)

            info = await loop.run_in_executor(None, _search_and_download)

            if "entries" in info and info["entries"]:
                entry = info["entries"][0]
            else:
                entry = info

            title = entry.get("title", query)
            artist = entry.get("uploader") or entry.get("channel") or "Unknown"

            await status_msg.edit_text(f"📤 Uploading **{title}** to Telegram...", parse_mode="Markdown")

            mp3_files = glob.glob(os.path.join(tmp_dir, "*.mp3"))
            if not mp3_files:
                await status_msg.edit_text("❌ Could not convert song to MP3.")
                return

            song_file = mp3_files[0]
            with open(song_file, "rb") as af:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=af,
                    title=title,
                    performer=artist,
                    caption=f"🎵 {title}\n👤 {artist}\n\nDownloaded via Ultra Manager Bot",
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60
                )

            log_download(update.effective_user.id, "music", title)

            try:
                await status_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Song download error: {e}")
            try:
                await status_msg.edit_text(f"❌ Failed to find or download song: {str(e)[:150]}")
            except Exception:
                pass
