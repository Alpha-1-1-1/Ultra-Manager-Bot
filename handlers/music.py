import os
import glob
import logging
import asyncio
import tempfile
import shutil
from telegram import Update
from telegram.ext import ContextTypes
import yt_dlp
from database.db import log_download

logger = logging.getLogger(__name__)

from handlers.downloader import get_speed_ydl_opts

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
    search_target = f"ytsearch1:{query}"
    status_msg = await update.message.reply_text(f"🔍 Searching YouTube for: `{query}`...", parse_mode="Markdown")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")
        
        loop = asyncio.get_event_loop()
        info = None
        last_err = None
        
        for attempt in range(3):
            ydl_opts = get_speed_ydl_opts(search_target, {
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
                "max_filesize": 100 * 1024 * 1024, # 100MB limit
            })
            
            try:
                def _search_and_download(opts):
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(search_target, download=True)
                info = await loop.run_in_executor(None, _search_and_download, ydl_opts)
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                logger.warning(f"Music download attempt {attempt+1} failed: {e}")
                
                if "proxy" in err_str or "socks" in err_str or "timeout" in err_str or "connection" in err_str:
                    continue
                
                try:
                    fallback_opts = dict(ydl_opts)
                    fallback_opts.pop("extractor_args", None)
                    def _search_fallback(opts):
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            return ydl.extract_info(search_target, download=True)
                    info = await loop.run_in_executor(None, _search_fallback, fallback_opts)
                    break
                except Exception as e2:
                    last_err = e2
                    break
                    
        if not info:
            logger.error(f"Fallback music download failed: {last_err}")
            try:
                await status_msg.edit_text(f"❌ Failed to find or download song: {str(last_err)[:150]}")
            except Exception:
                pass
            return

        if info and "entries" in info and info["entries"]:
            entry = info["entries"][0]
        else:
            entry = info or {}

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
