import os
import re
import glob
import uuid
import logging
import asyncio
import tempfile
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
import yt_dlp

logger = logging.getLogger(__name__)

# In-memory storage for active download sessions
# Key: session_id (str), Value: dict of video info and settings
video_sessions: Dict[str, Dict[str, Any]] = {}

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
    for h in [1080, 720, 480, 360]:
        if heights and any(val and val >= h for val in heights):
            row.append(InlineKeyboardButton(f"🎥 {h}p", callback_data=f"dl:exec_v:{session_id}:{h}"))
            if len(row) == 2:
                quality_buttons.append(row)
                row = []
    if row:
        quality_buttons.append(row)

    # Always provide Best quality button
    quality_buttons.append([
        InlineKeyboardButton("⚡ Best Quality (<50MB)", callback_data=f"dl:exec_v:{session_id}:best")
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
    """Extracts video metadata and sends thumbnail preview with interactive options."""
    status_msg = await update.message.reply_text("🔍 Extracting video details... Please wait.")

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    loop = asyncio.get_event_loop()
    try:
        def _extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"Error fetching metadata: {e}")
        try:
            await status_msg.edit_text(f"❌ Could not retrieve video from link.\nError: `{str(e)[:150]}`", parse_mode="Markdown")
        except Exception:
            pass
        return

    # Delete status message safely
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
        f"🏷️ **Template**: `%(title)s.%(ext)s`\n\n"
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

    # Fallback to text message if photo fails
    await update.message.reply_text(
        text=caption,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def download_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /download <url> command."""
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
    """Automatically detects video links sent directly in chat."""
    text = update.message.text or ""
    # Extract first URL
    match = re.search(r"(https?://[^\s]+)", text)
    if not match:
        return

    url = match.group(1).strip()
    # Filter out non-video / common generic domains if desired, or let yt-dlp inspect
    await process_video_link(url, update, context)

async def downloader_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all downloader inline button clicks."""
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

    # 1. Navigation to Video Quality Menu
    if action == "menu_v":
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=get_quality_keyboard(session_id))
        return

    # 2. Back to Main Menu
    elif action == "back":
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        return

    # 3. Toggle SponsorBlock
    elif action == "toggle_sb":
        session["sponsorblock"] = not session.get("sponsorblock", False)
        status = "ENABLED" if session["sponsorblock"] else "DISABLED"
        await query.answer(f"SponsorBlock {status}!")
        # Refresh current keyboard
        try:
            if len(parts) > 3 and parts[3] == "q":
                await query.edit_message_reply_markup(reply_markup=get_quality_keyboard(session_id))
            else:
                await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        except Exception:
            pass
        return

    # 4. Toggle Split Chapters
    elif action == "toggle_sc":
        session["split_chapters"] = not session.get("split_chapters", False)
        status = "ENABLED" if session["split_chapters"] else "DISABLED"
        await query.answer(f"Split Chapters {status}!")
        try:
            await query.edit_message_reply_markup(reply_markup=get_main_options_keyboard(session_id))
        except Exception:
            pass
        return

    # 5. Toggle Filename Template
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

    # 6. Cut Video Info
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

    # 7. Download Thumbnail
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
            # Also send as uncompressed document
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=thumb_url,
                caption="High-resolution original thumbnail file"
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to send thumbnail: {e}")
        return

    # 8. Download Audio (MP3)
    elif action == "audio":
        await query.answer("Starting audio extraction...")
        await _execute_audio_download(query, context, session)
        return

    # 9. Download Video Execution
    elif action == "exec_v":
        quality = parts[3] if len(parts) > 3 else "best"
        await query.answer(f"Starting {quality} video download...")
        await _execute_video_download(query, context, session, quality)
        return

async def _execute_video_download(query, context: ContextTypes.DEFAULT_TYPE, session: dict, quality: str) -> None:
    chat_id = query.message.chat_id
    url = session["url"]
    sb = session.get("sponsorblock", False)
    sc = session.get("split_chapters", False)
    template = session.get("fn_template", "%(title)s.%(ext)s")

    progress_msg = await query.message.reply_text(f"⚡ Downloading video ({quality})... Please wait.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, template)

        format_str = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
            if quality != "best" else
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        )

        ydl_opts = {
            "format": format_str,
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 50 * 1024 * 1024,  # Telegram bot 50MB limit
        }

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
            await progress_msg.edit_text("📤 Uploading video to Telegram...")

            # Locate downloaded video files
            files = [f for f in glob.glob(os.path.join(tmp_dir, "*")) if not f.endswith(".temp") and not f.endswith(".part")]
            if not files:
                await progress_msg.edit_text("❌ Downloaded file exceeds 50MB Telegram limit or could not be found.")
                return

            for video_file in files:
                fname = os.path.basename(video_file)
                with open(video_file, "rb") as vf:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=vf,
                        caption=f"🎬 **{fname}**\n\nDownloaded via Ultra Manager Bot",
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

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

        if sb:
            ydl_opts["sponsorblock_remove"] = ["all"]

        loop = asyncio.get_event_loop()
        try:
            def _download_audio():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            info = await loop.run_in_executor(None, _download_audio)
            await progress_msg.edit_text("📤 Uploading audio to Telegram...")

            mp3_files = glob.glob(os.path.join(tmp_dir, "*.mp3"))
            if not mp3_files:
                await progress_msg.edit_text("❌ Failed to find converted MP3 file.")
                return

            audio_file = mp3_files[0]
            title = info.get("title", "Audio")
            uploader = info.get("uploader") or info.get("channel") or "Unknown"

            with open(audio_file, "rb") as af:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=af,
                    title=title,
                    performer=uploader,
                    caption=f"🎵 **{title}**\n\nExtracted via Ultra Manager Bot",
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
    """Cuts a video segment: /cut <session_id> <start_time> <end_time>."""
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

        # Use yt-dlp download_ranges to extract specific segment directly
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

        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": out_template,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(start_s, end_s)]),
            "force_keyframes_at_cuts": True,
            "quiet": True,
            "no_warnings": True,
        }

        loop = asyncio.get_event_loop()
        try:
            def _cut():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            await loop.run_in_executor(None, _cut)
            await progress_msg.edit_text("📤 Uploading cut segment...")

            files = glob.glob(os.path.join(tmp_dir, "*"))
            if not files:
                await progress_msg.edit_text("❌ Failed to cut video segment.")
                return

            with open(files[0], "rb") as vf:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=vf,
                    caption=f"✂️ **Cut Segment**: {start_time} - {end_time}\n\nVia Ultra Manager Bot",
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
