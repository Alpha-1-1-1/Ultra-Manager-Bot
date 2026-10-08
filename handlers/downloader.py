import os
import re
import glob
import math
import uuid
import html
import logging
import asyncio
import tempfile
import shutil
import subprocess
from typing import Dict, Any, Optional, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
import yt_dlp

logger = logging.getLogger(__name__)

# Strict safety limits for Telegram Bot API (Telegram strictly rejects anything >= 50MB)
TARGET_CHUNK_MB = 35                  # Safe target size for each part
MAX_ALLOWED_BYTES = 46 * 1024 * 1024  # 46 MB hard ceiling
MAX_DOWNLOAD_LIMIT = 4000 * 1024 * 1024  # 4 GB download ceiling

video_sessions: Dict[str, Dict[str, Any]] = {}

def get_speed_ydl_opts(url: str = None, extra_opts: dict = None) -> dict:
    """Builds optimized yt-dlp options for maximum speed, JS challenge solving, and cloud datacenter bypass."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 8,
        "buffersize": 1024 * 1024,
        "http_chunk_size": 10485760,
        "retries": 10,
        "fragment_retries": 10,
        "merge_output_format": "mp4",
        # Enable JS runtimes (Node / Deno) and remote challenge solver to defeat YouTube obfuscation
        "js_runtimes": {"node": {}, "deno": {}},
        "remote_components": ["ejs:github"],
        # Resilient player clients: default (visionos/web), web_embedded, mweb, and android
        "extractor_args": {
            "youtube": {
                "player_client": ["default", "web_embedded", "mweb", "android"]
            }
        },
    }

    is_youtube = False
    if url and ("youtube.com" in url or "youtu.be" in url):
        is_youtube = True

    # Automatically load YouTube cookies if present (bypasses datacenter bot checks)
    if is_youtube:
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

        # Randomly select a working proxy if the file exists
        try:
            import random
            proxy_file = "working_proxies.txt"
            if os.path.exists(proxy_file):
                with open(proxy_file, "r", encoding="utf-8") as f:
                    proxies = [line.strip() for line in f if line.strip()]
                if proxies:
                    opts["proxy"] = random.choice(proxies)
                    logger.info(f"Using proxy: {opts['proxy']}")
        except Exception as e:
            logger.error(f"Error loading proxy: {e}")


    if shutil.which("aria2c"):
        opts["external_downloader"] = {"default": "aria2c"}
        opts["external_downloader_args"] = {
            "default": ["-x", "16", "-s", "16", "-k", "1M", "--min-split-size=1M"]
        }

    if extra_opts:
        opts.update(extra_opts)
    return opts

def split_video_into_parts(video_file: str, duration: Optional[float] = None) -> List[str]:
    """Splits large videos into playable parts strictly under 46MB using predictable naming."""
    file_size = os.path.getsize(video_file)

    if file_size <= MAX_ALLOWED_BYTES:
        return [video_file]

    # Resolve video duration
    if not duration or duration <= 0:
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_file
            ]
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            duration = float(out)
        except Exception:
            duration = 180.0

    target_bytes = TARGET_CHUNK_MB * 1024 * 1024
    num_parts = math.ceil(file_size / target_bytes)
    segment_duration = max(3, int(duration / num_parts))

    out_dir = os.path.dirname(video_file)
    split_subdir = os.path.join(out_dir, f"split_{uuid.uuid4().hex[:6]}")
    os.makedirs(split_subdir, exist_ok=True)

    output_pattern = os.path.join(split_subdir, "chunk_%03d.mp4")

    attempt = 1
    while attempt <= 5:
        split_cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-c", "copy",
            "-map", "0",
            "-segment_time", str(segment_duration),
            "-f", "segment",
            "-reset_timestamps", "1",
            output_pattern
        ]
        try:
            subprocess.run(split_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            parts = sorted(glob.glob(os.path.join(split_subdir, "chunk_*.mp4")))

            # Check if all parts strictly meet the 46MB safety limit
            if parts and all(os.path.getsize(p) <= MAX_ALLOWED_BYTES for p in parts):
                return parts

            # If any chunk exceeded limit, decrease duration and retry
            segment_duration = max(3, int(segment_duration * 0.65))
            for p in parts:
                try:
                    os.remove(p)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"FFmpeg split attempt {attempt} error: {e}")

        attempt += 1

    parts = sorted(glob.glob(os.path.join(split_subdir, "chunk_*.mp4")))
    valid_parts = [p for p in parts if os.path.exists(p) and os.path.getsize(p) <= MAX_ALLOWED_BYTES]
    return valid_parts if valid_parts else [video_file]

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

    quality_buttons.append([
        InlineKeyboardButton("⚡ Best Quality (Auto-Split Enabled)", callback_data=f"dl:exec_v:{session_id}:best")
    ])

    quality_buttons.append([
        InlineKeyboardButton(f"🛡️ SponsorBlock: {sb_status}", callback_data=f"dl:toggle_sb:{session_id}"),
        InlineKeyboardButton(f"📑 Chapters: {sc_status}", callback_data=f"dl:toggle_sc:{session_id}"),
    ])

    quality_buttons.append([
        InlineKeyboardButton("« Back", callback_data=f"dl:back:{session_id}")
    ])

    return InlineKeyboardMarkup(quality_buttons)

async def process_video_link(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("⚡ Fetching video details...")

    # Use datacenter-compatible android/ios clients
    loop = asyncio.get_event_loop()
    info = None
    last_err = None
    
    for attempt in range(3):
        fast_opts = get_speed_ydl_opts(url, {
            "skip_download": True,
            "extract_flat": False,
        })
        
        try:
            def _extract(opts):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            info = await loop.run_in_executor(None, _extract, fast_opts)
            break
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            logger.warning(f"Primary extraction attempt {attempt+1} failed: {e}")
            
            # If it's a proxy/connection error, retry with a new random proxy
            if "proxy" in err_str or "socks" in err_str or "timeout" in err_str or "connection" in err_str:
                continue
                
            # If it's a bot block, try fallback player clients
            try:
                fallback_opts = dict(fast_opts)
                fallback_opts.pop("extractor_args", None)
                def _extract_fallback(opts):
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)
                info = await loop.run_in_executor(None, _extract_fallback, fallback_opts)
                break
            except Exception as e2:
                last_err = e2
                break

    if not info:
        logger.error(f"Fallback extraction also failed: {last_err}")
        err_str = str(last_err)
        help_tip = ""
        if "Sign in" in err_str or "bot" in err_str.lower() or "player response" in err_str.lower():
            help_tip = "\n\n💡 Tip: YouTube may be restricting datacenter requests. You can add a `cookies.txt` or set `YOUTUBE_COOKIES` in Render settings to bypass this."
        try:
            await status_msg.edit_text(f"❌ Could not retrieve video from link: {err_str[:120]}{help_tip}")
        except Exception:
            pass
        return

    try:
        await status_msg.delete()
    except Exception:
        pass

    session_id = uuid.uuid4().hex[:8]
    title = info.get("title", "Unknown Title")
    raw_duration = info.get("duration")
    duration = format_duration(raw_duration)
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    thumbnail_url = info.get("thumbnail")
    extractor = info.get("extractor_key") or "Web"

    formats = info.get("formats", [])
    heights = sorted(list(set(f.get("height") for f in formats if f.get("height"))), reverse=True)

    video_sessions[session_id] = {
        "url": url,
        "title": title,
        "raw_duration": raw_duration,
        "duration": duration,
        "uploader": uploader,
        "thumbnail_url": thumbnail_url,
        "extractor": extractor,
        "heights": heights,
        "sponsorblock": False,
        "split_chapters": False,
        "fn_template": "%(title)s.%(ext)s",
    }

    escaped_title = html.escape(title)
    escaped_uploader = html.escape(uploader)
    escaped_extractor = html.escape(extractor)

    caption = (
        f"🎬 <b>{escaped_title}</b>\n\n"
        f"👤 <b>Channel</b>: {escaped_uploader}\n"
        f"⏱️ <b>Duration</b>: {duration}\n"
        f"🌐 <b>Platform</b>: {escaped_extractor}\n"
        "✂️ <b>Auto-Split Engine</b>: Active (Parts strictly &lt; 46MB)\n\n"
        "Choose an option below:"
    )

    keyboard = get_main_options_keyboard(session_id)

    sent_thumbnail = False
    if thumbnail_url:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=thumbnail_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            sent_thumbnail = True
        except Exception as e:
            logger.warning(f"send_photo with URL failed ({e}), falling back to text message...")

    if not sent_thumbnail:
        try:
            await update.message.reply_text(
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            plain_caption = f"🎬 {title}\n\n👤 Channel: {uploader}\n⏱️ Duration: {duration}\n🌐 Platform: {extractor}\n\nChoose an option below:"
            await update.message.reply_text(
                text=plain_caption,
                reply_markup=keyboard
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
                caption=f"🖼️ Thumbnail for: {session.get('title')}"
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
        await query.answer("Starting audio extraction...")
        await _execute_audio_download(query, context, session)
        return

    elif action == "exec_v":
        quality = parts[3] if len(parts) > 3 else "best"
        await query.answer(f"Starting {quality} video download...")
        await _execute_video_download(query, context, session, quality)
        return

async def _execute_video_download(query, context: ContextTypes.DEFAULT_TYPE, session: dict, quality: str) -> None:
    chat_id = query.message.chat_id
    url = session["url"]
    title = session.get("title", "Video")
    sb = session.get("sponsorblock", False)
    sc = session.get("split_chapters", False)
    raw_duration = session.get("raw_duration")

    progress_msg = await query.message.reply_text(f"⚡ Downloading video ({quality})...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "video.%(ext)s")

        format_str = (
            f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
            if quality != "best" else
            "bestvideo+bestaudio/best"
        )

        loop = asyncio.get_event_loop()
        info = None
        last_err = None
        
        for attempt in range(3):
            ydl_opts = get_speed_ydl_opts(url, {
                "format": format_str,
                "outtmpl": out_template,
                "max_filesize": MAX_DOWNLOAD_LIMIT,
            })

            if sb:
                ydl_opts["sponsorblock_remove"] = ["all"]
            if sc:
                ydl_opts["split_chapters"] = True

            try:
                def _download(opts):
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=True)

                info = await loop.run_in_executor(None, _download, ydl_opts)
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                logger.warning(f"Primary download attempt {attempt+1} failed: {e}")
                
                # If proxy error, continue to next loop iteration for a fresh proxy
                if "proxy" in err_str or "socks" in err_str or "timeout" in err_str or "connection" in err_str:
                    continue
                    
                # If bot block, try fallback opts
                try:
                    fallback_opts = dict(ydl_opts)
                    fallback_opts.pop("extractor_args", None)
                    def _download_fallback(opts):
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            return ydl.extract_info(url, download=True)
                    info = await loop.run_in_executor(None, _download_fallback, fallback_opts)
                    break
                except Exception as e2:
                    last_err = e2
                    break

        if not info:
            logger.error(f"Fallback download also failed: {last_err}")
            await progress_msg.edit_text(f"❌ Download failed: {str(last_err)[:120]}")
            return

        # --- File finding, splitting, and uploading (runs after ANY successful download) ---
        try:
            files = [f for f in glob.glob(os.path.join(tmp_dir, "video.*")) if not f.endswith(".temp") and not f.endswith(".part")]
            if not files:
                await progress_msg.edit_text("❌ Downloaded file exceeds limit or could not be found.")
                return

            original_file = files[0]
            total_size_mb = round(os.path.getsize(original_file) / (1024 * 1024), 2)
            video_duration = raw_duration or info.get("duration")

            # Guaranteed split strictly < 46MB using clean chunk naming
            parts_to_upload = split_video_into_parts(original_file, duration=video_duration)
            total_parts = len(parts_to_upload)

            if total_parts > 1:
                await progress_msg.edit_text(f"✂️ File is {total_size_mb} MB. Sliced into {total_parts} parts for 100% upload delivery...")
            else:
                await progress_msg.edit_text(f"📤 Uploading video to Telegram ({total_size_mb} MB)...")

            for idx, part_file in enumerate(parts_to_upload, 1):
                part_size_mb = round(os.path.getsize(part_file) / (1024 * 1024), 2)

                if total_parts > 1:
                    caption = f"🎬 {title} (Part {idx}/{total_parts})\n📦 Size: {part_size_mb} MB\n\nDownloaded via Ultra Manager Bot"
                else:
                    caption = f"🎬 {title}\n📦 Size: {part_size_mb} MB\n\nDownloaded via Ultra Manager Bot"

                with open(part_file, "rb") as vf:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=vf,
                        caption=caption,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60
                    )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Download execution error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Download failed: {str(e)[:150]}")
            except Exception:
                pass

async def _execute_audio_download(query, context: ContextTypes.DEFAULT_TYPE, session: dict) -> None:
    chat_id = query.message.chat_id
    url = session["url"]
    sb = session.get("sponsorblock", False)

    progress_msg = await query.message.reply_text("🎵 Extracting high quality MP3... Please wait.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

        loop = asyncio.get_event_loop()
        info = None
        last_err = None
        
        for attempt in range(3):
            ydl_opts = get_speed_ydl_opts(url, {
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "max_filesize": MAX_DOWNLOAD_LIMIT,
            })

            if sb:
                ydl_opts["sponsorblock_remove"] = ["all"]

            try:
                def _download_audio(opts):
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=True)

                info = await loop.run_in_executor(None, _download_audio, ydl_opts)
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                logger.warning(f"Audio download attempt {attempt+1} failed: {e}")
                
                if "proxy" in err_str or "socks" in err_str or "timeout" in err_str or "connection" in err_str:
                    continue
                
                try:
                    fallback_opts = dict(ydl_opts)
                    fallback_opts.pop("extractor_args", None)
                    def _download_audio_fallback(opts):
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            return ydl.extract_info(url, download=True)
                    info = await loop.run_in_executor(None, _download_audio_fallback, fallback_opts)
                    break
                except Exception as e2:
                    last_err = e2
                    break
                    
        if not info:
            logger.error(f"Audio fallback download also failed: {last_err}")
            await progress_msg.edit_text(f"❌ Audio extraction failed: {str(last_err)[:120]}")
            return

        # --- File finding and uploading (runs after ANY successful download) ---
        try:
            mp3_files = glob.glob(os.path.join(tmp_dir, "*.mp3"))
            if not mp3_files:
                await progress_msg.edit_text("❌ Failed to find converted MP3 file.")
                return

            audio_file = mp3_files[0]
            file_size = os.path.getsize(audio_file)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            title = info.get("title", "Audio")
            uploader = info.get("uploader") or info.get("channel") or "Unknown"

            caption = f"🎵 {title}\n👤 {uploader}\n📦 Size: {file_size_mb} MB\n\nExtracted via Ultra Manager Bot"

            await progress_msg.edit_text("📤 Uploading audio to Telegram...")
            with open(audio_file, "rb") as af:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=af,
                    title=title,
                    performer=uploader,
                    caption=caption,
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60
                )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Audio extraction failed: {str(e)[:150]}")
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
        out_template = os.path.join(tmp_dir, "cut_video.%(ext)s")

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

        ydl_opts = get_speed_ydl_opts(url, {
            "format": "best[ext=mp4]/best",
            "outtmpl": out_template,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(start_s, end_s)]),
            "force_keyframes_at_cuts": True,
            "max_filesize": MAX_DOWNLOAD_LIMIT,
        })

        loop = asyncio.get_event_loop()
        try:
            def _cut():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            await loop.run_in_executor(None, _cut)
            files = [f for f in glob.glob(os.path.join(tmp_dir, "cut_video.*")) if not f.endswith(".part")]
            if not files:
                await progress_msg.edit_text("❌ Failed to cut video segment.")
                return

            video_file = files[0]
            file_size = os.path.getsize(video_file)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            caption = f"✂️ Cut Segment: {start_time} - {end_time}\n📦 Size: {file_size_mb} MB\n\nVia Ultra Manager Bot"

            parts_to_upload = split_video_into_parts(video_file, duration=abs(end_s - start_s))
            for part in parts_to_upload:
                with open(part, "rb") as vf:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=vf,
                        caption=caption,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60
                    )

            try:
                await progress_msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Cut error: {e}")
            try:
                await progress_msg.edit_text(f"❌ Failed to cut: {str(e)[:150]}")
            except Exception:
                pass
