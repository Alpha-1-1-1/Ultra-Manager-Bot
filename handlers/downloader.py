import os
import re
import glob
import uuid
import logging
import asyncio
import tempfile
import shutil
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
import yt_dlp
from handlers.premium_uploader import upload_premium_file

logger = logging.getLogger(__name__)

# 4GB limit for Telegram Premium
MAX_PREMIUM_FILESIZE = 4000 * 1024 * 1024
BOT_API_LIMIT = 50 * 1024 * 1024

video_sessions: Dict[str, Dict[str, Any]] = {}

def get_speed_ydl_opts(extra_opts: dict = None) -> dict:
    """Builds optimized yt-dlp options for maximum parallel download speed."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        # Multi-threaded parallel segment downloads (DASH / HLS / YouTube)
        "concurrent_fragment_downloads": 8,
        "buffersize": 1024 * 1024,      # 1MB memory buffer
        "http_chunk_size": 10485760,     # 10MB chunk size
        "retries": 10,
        "fragment_retries": 10,
        # Fast YouTube clients to bypass server-side bitrate throttle
        "extractor_args": {
            "youtube": {
                "player_client": ["web_creator", "android", "mweb"]
            }
        },
    }

    # If aria2c is installed on the system (e.g. on Kaggle / Linux), use 16 multi-threaded connections
    if shutil.which("aria2c"):
        opts["external_downloader"] = {"default": "aria2c"}
        opts["external_downloader_args"] = {
            "default": ["-x", "16", "-s", "16", "-k", "1M", "--min-split-size=1M"]
        }

    if extra_opts:
        opts.update(extra_opts)
    return opts

def format_duration(seconds: Optional[int]) -> str:
    """Format duration seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "Unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def get_main_options_keyboard(session_id: str) -> InlineKeyboardMarkup:
    session = video_sessions.get(session_id, {})
    sb_status = "ON ✅" if session.get("sponsorblock") else "OFF ❌"
    sc_status = "ON ✅" if session.get("split_chapters") else "OFF ❌"

    keyboard = [
        # Line 1: Full width download video
        [InlineKeyboardButton("📥 Download Video", callback_data=f"dl:menu_v:{session_id}")],
        # Line 2: Half / Half
        [
            InlineKeyboardButton("🎵 Download Audio", callback_data=f"dl:audio:{session_id}"),
            InlineKeyboardButton("🖼️ Download Thumbnail", callback_data=f"dl:thumb:{session_id}"),
        ],
        # Line 3: Two options (Cut & Filename Template)
        [
            InlineKeyboardButton("✂️ Cut Video", callback_data=f"dl:cut_info:{session_id}"),
            InlineKeyboardButton("🏷️ Filename Template", callback_data=f"dl:fn_toggle:{session_id}"),
        ],
        # Line 4: SponsorBlock & Chapters
        [
            InlineKeyboardButton(f"🛡️ SponsorBlock: {sb_status}", callback_data=f"dl:toggle_sb:{session_id}"),
            InlineKeyboardButton(f"📑 Chapters: {sc_status}", callback_data=f"dl:toggle_sc:{session_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_quality_keyboard(session_id: str) -> InlineKeyboardMarkup:
    session = video_sessions.get(session_id, {})
    heights = session.get("heights", [])
    sb_status = "ON ✅" if session.get("sponsorblock") else "OFF ❌"
    sc_status = "ON ✅" if session.get("split_chapters") else "OFF ❌"

    quality_buttons = []
    row = []
    # Standard resolution choices
    standard_heights = [2160, 1440, 1080, 720, 480, 360]
    for h in standard_heights:
        if not heights or any(val and val >= h for val in heights):
            label = "🌟 4K" if h == 2160 else ("✨ 2K" if h == 1440 else f"🎥 {h}p")
            row.append(InlineKeyboardButton(label, callback_data=f"dl:exec_v:{session_id}:{h}"))
            if len(row) == 2:
                quality_buttons.append(row)
                row = []
    if row:
        quality_buttons.append(row)

    # Full 4GB Best Quality
    quality_buttons.append([
        InlineKeyboardButton("⚡ Best Quality (Up to 4GB Premium)", callback_data=f"dl:exec_v:{session_id}:best")
    ])

    # SponsorBlock and Chapters toggle row
    quality_buttons.append([
        InlineKeyboardButton(f"🛡️ SponsorBlock: {sb_status}", callback_data=f"dl:toggle_sb:{session_id}"),
        InlineKeyboardButton(f"📑 Chapters: {sc_status}", callback_data=f"dl:toggle_sc:{session_id}"),
    ])

    # Back to main options
    quality_buttons.append([
        InlineKeyboardButton("« Back", callback_data=f"dl:back:{session_id}")
    ])

    return InlineKeyboardMarkup(quality_buttons)

async def process_video_link(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instant preview card with optimized metadata extraction."""
    status_msg = await update.message.reply_text("⚡ Fetching video details...")

    # Fast metadata options (skip resolving deep streams to render UI immediately)
    fast_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    loop = asyncio.get_event_loop()
    try:
        def _extract():
            with yt_dlp.YoutubeDL(fast_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"Error fetching metadata: {e}")
        try:
            await status_msg.edit_text(f"❌ Could not retrieve video from link.\nError: `{str(e)[:150]}`", parse_mode="Markdown")
        except Exception:
            pass
        return

    try:
        await status_msg.delete()
    except Exception:
        pass

    session_id = uuid.uuid4().hex[:8]
    title = info.get("title", "Unknown Title")
    duration = format_duration(info.get("duration"))
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    thumbnail_url = info.get("thumbnail")
    extractor = info.get("extractor_key") or "Web"

    formats = info.get("formats", [])
    heights = sorted(list(set(f.get("height") for f in formats if f.get("height"))), reverse=True)

    video_sessions[session_id] = {
        "url": url,
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "thumbnail_url": thumbnail_url,
        "extractor": extractor,
        "heights": heights,
        "sponsorblock": False,
        "split_chapters": False,
        "fn_template": "%(title)s.%(ext)s",
    }

    caption = (
        f"🎬 **{title}**\n\n"
        f"👤 **Channel**: {uploader}\n"
        f"⏱️ **Duration**: {duration}\n"
        f"🌐 **Platform**: {extractor}\n"
        f"👑 **Premium 4GB Mode**: Active\n\n"
        "Choose an option below:"
    )

    keyboard = get_main_options_keyboard(session_id)

    if thumbnail_url:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=thumbnail_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            logger.warning(f"Could not send thumbnail by URL: {e}")

    await update.message.reply_text(
        text=caption,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def download_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "💡 **Usage**: `/download <video_url>`\n\n"
            "**Supported Platforms**:\n"
            "• YouTube, Shorts, Twitter/X, Instagram, TikTok, Reddit & more!",
            parse_mode="Markdown"
        )
        return

    url = context.args[0].strip()
    await process_video_link(url, update, context)

async def link_detector_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = re.search(r"(https?://[^\s]+)", text)
    if not match:
        return

    url = match.group(1).strip()
    await process_video_link(url, update, context)

async def downloader_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    if not data.startswith("dl:"):
        return

    parts = data.split(":")
    action = parts[1]
    session_id = parts[2]

    session = video_sessions.get(session_id)
    if not session:
        await query.answer("⚠️ Session expired or invalid. Please re-send the link.", show_alert=True)
        return

    if action == "menu_v":
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=get_quality_keyboard(session_id))
        return

    elif action == "back":
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        return

    elif action == "toggle_sb":
        session["sponsorblock"] = not session.get("sponsorblock", False)
        status = "ENABLED" if session["sponsorblock"] else "DISABLED"
        await query.answer(f"SponsorBlock {status}!")
        try:
            await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        except Exception:
            pass
        return

    elif action == "toggle_sc":
        session["split_chapters"] = not session.get("split_chapters", False)
        status = "ENABLED" if session["split_chapters"] else "DISABLED"
        await query.answer(f"Split Chapters {status}!")
        try:
            await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        except Exception:
            pass
        return

    elif action == "fn_toggle":
        templates = [
            "%(title)s.%(ext)s",
            "%(uploader)s - %(title)s.%(ext)s",
            "%(id)s.%(ext)s"
        ]
        current = session.get("fn_template", templates[0])
        next_idx = (templates.index(current) + 1) % len(templates) if current in templates else 0
        session["fn_template"] = templates[next_idx]
        await query.answer(f"Template set to:\n{templates[next_idx]}", show_alert=True)
        return

    elif action == "cut_info":
        await query.answer()
        msg_text = (
            f"✂️ **How to Cut This Video**:\n\n"
            f"Reply to this message with:\n"
            f"`/cut {session_id} <start_time> <end_time>`\n\n"
            f"**Example**:\n"
            f"`/cut {session_id} 00:15 01:30` (cuts from 15s to 1m 30s)"
        )
        await query.message.reply_text(msg_text, parse_mode="Markdown")
        return

    elif action == "dl:thumb" or action == "thumb":
        await query.answer("Fetching thumbnail...")
        thumb_url = session.get("thumbnail_url")
        if not thumb_url:
            await query.message.reply_text("❌ No thumbnail available for this video.")
            return

        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=thumb_url,
                caption=f"🖼️ Thumbnail for: **{session.get('title')}**",
                parse_mode="Markdown"
            )
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=thumb_url,
                caption="High-resolution original thumbnail file"
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to send thumbnail: {e}")
        return

    elif action == "audio":
        await query.answer("Starting high-speed audio extraction...")
        await _execute_audio_download(query, context, session)
        return

    elif action == "exec_v":
        quality = parts[3] if len(parts) > 3 else "best"
        await query.answer(f"Starting parallel {quality} download...")
        await _execute_video_download(query, context, session, quality)
        return

async def _execute_video_download(query, context: ContextTypes.DEFAULT_TYPE, session: dict, quality: str) -> None:
    chat_id = query.message.chat_id
    url = session["url"]
    sb = session.get("sponsorblock", False)
    sc = session.get("split_chapters", False)
    template = session.get("fn_template", "%(title)s.%(ext)s")

    progress_msg = await query.message.reply_text(f"🚀 Downloading {quality} via parallel threads... Up to 4GB.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, template)

        format_str = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
            if quality != "best" else
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        )

        ydl_opts = get_speed_ydl_opts({
            "format": format_str,
            "outtmpl": out_template,
            "max_filesize": MAX_PREMIUM_FILESIZE,
        })

        if sb:
            ydl_opts["sponsorblock_remove"] = ["all"]
        if sc:
            ydl_opts["split_chapters"] = True

        loop = asyncio.get_event_loop()
        try:
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            info = await loop.run_in_executor(None, _download)

            files = [f for f in glob.glob(os.path.join(tmp_dir, "*")) if not f.endswith(".temp") and not f.endswith(".part")]
            if not files:
                await progress_msg.edit_text("❌ Downloaded file exceeds 4GB limit or could not be found.")
                return

            for video_file in files:
                file_size = os.path.getsize(video_file)
                file_size_mb = round(file_size / (1024 * 1024), 2)
                fname = os.path.basename(video_file)

                caption = f"🎬 **{fname}**\n📦 Size: `{file_size_mb} MB`\n\nDownloaded via Ultra Manager Bot"

                if file_size > BOT_API_LIMIT:
                    await progress_msg.edit_text(f"👑 Uploading via Telegram Premium session ({file_size_mb} MB)...")
                    try:
                        success = await upload_premium_file(chat_id, video_file, caption, media_type="video")
                        if not success:
                            await progress_msg.edit_text(
                                f"⚠️ Video is **{file_size_mb} MB** (exceeds the 50MB Bot API cap).\n\n"
                                "Please make sure `TELEGRAM_SESSION_STRING` is set in your secrets to allow 4GB uploads!",
                                parse_mode="Markdown"
                            )
                            return
                    except Exception as pe:
                        logger.error(f"Premium upload failed: {pe}")
                        await progress_msg.edit_text(f"❌ Premium upload failed: `{str(pe)[:150]}`")
                        return
                else:
                    await progress_msg.edit_text(f"📤 Uploading video to Telegram ({file_size_mb} MB)...")
                    with open(video_file, "rb") as vf:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=vf,
                            caption=caption,
                            parse_mode="Markdown"
                        )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Download execution error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Download failed: `{str(e)[:150]}`", parse_mode="Markdown")
            except Exception:
                pass

async def _execute_audio_download(query, context: ContextTypes.DEFAULT_TYPE, session: dict) -> None:
    chat_id = query.message.chat_id
    url = session["url"]
    sb = session.get("sponsorblock", False)

    progress_msg = await query.message.reply_text("🎵 Extracting high quality MP3... Please wait.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

        ydl_opts = get_speed_ydl_opts({
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "max_filesize": MAX_PREMIUM_FILESIZE,
        })

        if sb:
            ydl_opts["sponsorblock_remove"] = ["all"]

        loop = asyncio.get_event_loop()
        try:
            def _download_audio():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            info = await loop.run_in_executor(None, _download_audio)

            mp3_files = glob.glob(os.path.join(tmp_dir, "*.mp3"))
            if not mp3_files:
                await progress_msg.edit_text("❌ Failed to find converted MP3 file.")
                return

            audio_file = mp3_files[0]
            file_size = os.path.getsize(audio_file)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            title = info.get("title", "Audio")
            uploader = info.get("uploader") or info.get("channel") or "Unknown"

            caption = f"🎵 **{title}**\n👤 {uploader}\n📦 Size: `{file_size_mb} MB`\n\nExtracted via Ultra Manager Bot"

            if file_size > BOT_API_LIMIT:
                await progress_msg.edit_text(f"👑 Uploading audio via Telegram Premium ({file_size_mb} MB)...")
                await upload_premium_file(chat_id, audio_file, caption, media_type="audio")
            else:
                await progress_msg.edit_text("📤 Uploading audio to Telegram...")
                with open(audio_file, "rb") as af:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=af,
                        title=title,
                        performer=uploader,
                        caption=caption,
                        parse_mode="Markdown"
                    )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Audio extraction failed: `{str(e)[:150]}`", parse_mode="Markdown")
            except Exception:
                pass

async def cut_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text(
            "💡 **Usage**: `/cut <session_id> <start_time> <end_time>`\n\n"
            "**Example**:\n"
            "`/cut a1b2c3d4 00:10 01:20` (cuts from 10 seconds to 1 min 20s)",
            parse_mode="Markdown"
        )
        return

    session_id = context.args[0]
    start_time = context.args[1]
    end_time = context.args[2]

    session = video_sessions.get(session_id)
    if not session:
        await update.message.reply_text("❌ Session not found or expired. Please re-send the video link.")
        return

    url = session["url"]
    progress_msg = await update.message.reply_text(f"✂️ Cutting video ({start_time} to {end_time})...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "cut_%(title)s.%(ext)s")

        def parse_to_seconds(ts: str) -> float:
            parts = [float(x) for x in ts.split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return float(parts[0])

        try:
            start_s = parse_to_seconds(start_time)
            end_s = parse_to_seconds(end_time)
        except Exception:
            await progress_msg.edit_text("❌ Invalid time format. Use `MM:SS` or `HH:MM:SS`.")
            return

        ydl_opts = get_speed_ydl_opts({
            "format": "best[ext=mp4]/best",
            "outtmpl": out_template,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(start_s, end_s)]),
            "force_keyframes_at_cuts": True,
            "max_filesize": MAX_PREMIUM_FILESIZE,
        })

        loop = asyncio.get_event_loop()
        try:
            def _cut():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            await loop.run_in_executor(None, _cut)
            files = glob.glob(os.path.join(tmp_dir, "*"))
            if not files:
                await progress_msg.edit_text("❌ Failed to cut video segment.")
                return

            video_file = files[0]
            file_size = os.path.getsize(video_file)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            caption = f"✂️ **Cut Segment**: {start_time} - {end_time}\n📦 Size: `{file_size_mb} MB`\n\nVia Ultra Manager Bot"

            if file_size > BOT_API_LIMIT:
                await progress_msg.edit_text(f"👑 Uploading cut video via Telegram Premium ({file_size_mb} MB)...")
                await upload_premium_file(update.effective_chat.id, video_file, caption, media_type="video")
            else:
                await progress_msg.edit_text("📤 Uploading cut segment...")
                with open(video_file, "rb") as vf:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=vf,
                        caption=caption,
                        parse_mode="Markdown"
                    )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Cut error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Failed to cut: `{str(e)[:150]}`", parse_mode="Markdown")
            except Exception:
                pass
