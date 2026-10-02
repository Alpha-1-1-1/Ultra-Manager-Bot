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

def _get_music_ydl_opts(out_template: str) -> dict:
    """Builds optimized yt-dlp options for YouTube music search and MP3 download."""
    opts = {
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
        "retries": 10,
        "fragment_retries": 10,
        "js_runtimes": {"node": {}, "deno": {}},
        "remote_components": ["ejs:github"],
        "extractor_args": {
            "youtube": {
                "player_client": ["default", "web_embedded", "mweb", "android"]
            }
        },
    }

    # Automatically load YouTube cookies if present
    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "cookies.txt")
    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
        opts["cookiefile"] = cookie_file
    elif os.getenv("YOUTUBE_COOKIES"):
        try:
            temp_cookie_path = os.path.join(tempfile.gettempdir(), "render_yt_cookies.txt")
            with open(temp_cookie_path, "w", encoding="utf-8") as f:
                f.write(os.getenv("YOUTUBE_COOKIES"))
            opts["cookiefile"] = temp_cookie_path
        except Exception:
            pass

    if shutil.which("aria2c"):
        opts["external_downloader"] = {"default": "aria2c"}
        opts["external_downloader_args"] = {
            "default": ["-x", "16", "-s", "16", "-k", "1M", "--min-split-size=1M"]
        }

    return opts

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
        ydl_opts = _get_music_ydl_opts(out_template)

        loop = asyncio.get_event_loop()
        info = None
        try:
            def _search_and_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(search_target, download=True)

            info = await loop.run_in_executor(None, _search_and_download)
        except Exception as e:
            logger.warning(f"Primary music download failed: {e}. Trying fallback options...")
            try:
                fallback_opts = dict(ydl_opts)
                fallback_opts.pop("extractor_args", None)
                def _search_fallback():
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        return ydl.extract_info(search_target, download=True)
                info = await loop.run_in_executor(None, _search_fallback)
            except Exception as e2:
                logger.error(f"Fallback music download failed: {e2}")
                try:
                    await status_msg.edit_text(f"❌ Failed to find or download song: {str(e2)[:150]}")
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
