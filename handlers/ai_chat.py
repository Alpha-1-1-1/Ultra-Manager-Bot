import io
import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

logger = logging.getLogger(__name__)

# Active Gemini 3 models (Primary: 3.8 Flash, High-Availability Fallback: 3.6 Flash)
MODELS_TO_TRY = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
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

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = _get_genai_client()
    if not client:
        await update.message.reply_text(
            "⚠️ **Gemini AI is not configured.**\n"
            "Please check that your `GEMINI_API_KEY` is added to `.env` or Render Environment Variables.\n\n"
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

    # Try gemini-3.8-flash first; if Google returns 503 high demand, failover to gemini-3.6-flash seamlessly
    last_error = None
    for model_name in MODELS_TO_TRY:
        for attempt in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                if response and response.text:
                    await status_msg.edit_text(response.text)
                    return
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                logger.warning(f"Model {model_name} attempt {attempt} error: {e}")
                # If 503 high demand, wait a moment and retry or proceed to next Gemini 3 model
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    await asyncio.sleep(1.0)
                    continue
                else:
                    break

    await status_msg.edit_text(
        f"❌ Error communicating with Gemini AI:\n`{last_error}`",
        parse_mode="Markdown"
    )
