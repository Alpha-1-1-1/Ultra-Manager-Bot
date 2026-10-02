import io
import os
import time
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

logger = logging.getLogger(__name__)

# Exclusively use modern Gemini 3.8 Flash (no deprecated 2.0 or 2.5 models)
PRIMARY_MODEL = "gemini-3.8-flash"

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

    # Clean any accidental quotes or whitespace
    api_key = str(api_key).strip("\"' \n\r\t")
    if not api_key or api_key == "your_gemini_api_key_here":
        return None

    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize GenAI client: {e}")
        return None

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = _get_genai_client()
    if not client:
        await update.message.reply_text(
            "⚠️ **Gemini AI is not configured.**\n"
            "Please check that your `GEMINI_API_KEY` is added to `.env` or **Kaggle Secrets**.\n\n"
            "Get a free API key at: https://aistudio.google.com/",
            parse_mode="Markdown"
        )
        return

    prompt = " ".join(context.args) if context.args else None

    # Check for photos
    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not prompt and not photo:
        await update.message.reply_text(
            "💡 **Usage**:\n"
            "• `/ai <your question>`\n"
            "• Send a photo with `/ai <question>` in the caption",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("Thinking... 🤔")

    image = None
    if photo:
        try:
            file = await context.bot.get_file(photo.file_id)
            img_bytes = await file.download_as_bytearray()
            image = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            await status_msg.edit_text("❌ Failed to process the image.")
            return

    contents = [image, prompt or "Describe this image in detail."] if image else prompt

    # Call Gemini 3.8 Flash with automatic retry on transient spikes
    last_error = None
    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=PRIMARY_MODEL,
                contents=contents
            )
            if response and response.text:
                await status_msg.edit_text(response.text)
                return
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Gemini 3.8 Flash attempt {attempt} failed: {e}")
            if attempt == 1:
                await asyncio.sleep(1.5)

    await status_msg.edit_text(
        f"❌ Error communicating with Gemini 3.8 Flash:\n`{last_error}`",
        parse_mode="Markdown"
    )
