import io
import os
import re
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

logger = logging.getLogger(__name__)

# Active Gemini 3 models (Primary: 3.8 Flash, Fallback: 3.6 Flash)
MODELS_TO_TRY = [
    "gemini-3.8-flash",
    "models/gemini-3.8-flash",
    "gemini-1.5-pro-latest",
    "gemini-1.5-pro",
    "gemini-2.5-flash",
]

def _get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY", "")

    # Auto-load from Kaggle secrets if running on Kaggle
    if not api_key or api_key == "your_gemini_api_key_here":
        try:
            from kaggle_secrets import UserSecretsClient
            api_key = UserSecretsClient().get_secret("GEMINI_API_KEY")
            if api_key:
                os.environ["GEMINI_API_KEY"] = str(api_key).strip()
        except Exception:
            pass

    if not api_key:
        return None

    api_key = str(api_key).strip("\"' \n\r\t")
    if not api_key or api_key == "your_gemini_api_key_here":
        return None

    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize GenAI client: {e}")
        return None

async def _send_long_response(status_msg, update: Update, text: str) -> None:
    """Splits long Gemini responses into Telegram safe chunks (< 4000 chars) and falls back to plain text if markdown fails."""
    max_len = 3900
    chunks = []
    while len(text) > max_len:
        split_idx = text.rfind("\n", 0, max_len)
        if split_idx == -1:
            split_idx = max_len
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    if text:
        chunks.append(text)

    # First chunk edits the status message
    first_chunk = chunks[0] if chunks else ""
    try:
        await status_msg.edit_text(first_chunk, parse_mode="Markdown")
    except Exception:
        try:
            await status_msg.edit_text(first_chunk)
        except Exception as e:
            logger.error(f"Failed to edit status message with AI response: {e}")

    # Subsequent chunks sent as replies
    for chunk in chunks[1:]:
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text(chunk)
            except Exception as e:
                logger.error(f"Failed to send AI response chunk: {e}")

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return

    message = update.effective_message
    client = _get_genai_client()
    if not client:
        await message.reply_text(
            "⚠️ **Gemini AI is not configured.**\n"
            "Please check that your `GEMINI_API_KEY` is added to `.env` or Render Environment Variables.\n\n"
            "Get a free API key at: https://aistudio.google.com/",
            parse_mode="Markdown"
        )
        return

    # Extract prompt text from context.args, caption, or message text
    prompt = " ".join(context.args) if context.args else None
    if not prompt:
        raw_text = message.caption or message.text or ""
        cleaned = re.sub(r"^/ai(?:@\w+)?(?:\s+|$)", "", raw_text, flags=re.IGNORECASE).strip()
        if cleaned:
            prompt = cleaned

    # Check for photo or image document in direct message or replied message
    target_photo = None
    target_doc = None

    if message.photo:
        target_photo = message.photo[-1]
    elif message.document and (
        (message.document.mime_type and message.document.mime_type.startswith("image/"))
        or (message.document.file_name and message.document.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    ):
        target_doc = message.document
    elif message.reply_to_message:
        reply = message.reply_to_message
        if reply.photo:
            target_photo = reply.photo[-1]
        elif reply.document and (
            (reply.document.mime_type and reply.document.mime_type.startswith("image/"))
            or (reply.document.file_name and reply.document.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
        ):
            target_doc = reply.document

    has_image = bool(target_photo or target_doc)

    if not prompt and not has_image:
        await message.reply_text(
            "🤖 **Gemini AI Usage**:\n\n"
            "• **Text Question**: `/ai What is the speed of light?`\n"
            "• **Image Analysis**: Send a photo with caption `/ai Describe this`\n"
            "• **Reply to Image**: Reply to any picture with `/ai What is this?`",
            parse_mode="Markdown"
        )
        return

    status_msg = await message.reply_text("Thinking... 🤔")

    image = None
    if has_image:
        try:
            file_id = target_photo.file_id if target_photo else target_doc.file_id
            file = await context.bot.get_file(file_id)
            img_bytes = await file.download_as_bytearray()
            image = Image.open(io.BytesIO(img_bytes))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
        except Exception as e:
            logger.error(f"Error processing image for Gemini: {e}")
            await status_msg.edit_text("❌ Failed to download or process the image.")
            return

    final_prompt = prompt or ("Describe this image in detail and answer any questions visible in it." if image else "")
    contents = [image, final_prompt] if image else final_prompt

    # Query Gemini with fallback models
    errors = []
    import time
    
    # 1. First, attempt predefined models with streaming
    for model_name in MODELS_TO_TRY:
        for attempt in range(1, 4):  # Try up to 3 times per model
            try:
                full_response = ""
                last_edit_time = time.time()
                
                response_stream = await client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents
                )
                
                async for chunk in response_stream:
                    if chunk.text:
                        full_response += chunk.text
                        # Update the message every 1.5s to avoid Telegram rate limits
                        if time.time() - last_edit_time > 1.5:
                            preview = full_response[:3900]
                            try:
                                await status_msg.edit_text(preview + " ⏳", parse_mode="Markdown")
                            except Exception:
                                try:
                                    await status_msg.edit_text(preview + " ⏳")
                                except Exception:
                                    pass
                            last_edit_time = time.time()
                
                if full_response:
                    await _send_long_response(status_msg, update, full_response)
                    return
            except Exception as e:
                err_str = str(e)
                errors.append(f"• `{model_name}` (Attempt {attempt}): {err_str}")
                logger.warning(f"Model {model_name} attempt {attempt} error: {e}")
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    # Exponential backoff: 2s, 4s, 8s...
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    break # Break attempt loop, try next model

    error_report = "\n".join(errors)
    await status_msg.edit_text(
        f"❌ **Error communicating with Google's Gemini API**:\n\n{error_report}",
        parse_mode="Markdown"
    )
