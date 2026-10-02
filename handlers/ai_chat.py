import io
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

logger = logging.getLogger(__name__)

# Primary and fallback Gemini models
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

def _get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
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
            "Please check that your `GEMINI_API_KEY` in `.env` is correct.\n\n"
            "Get a free API key at: https://aistudio.google.com/",
            parse_mode="Markdown"
        )
        return

    # Extract prompt
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

    last_error = None
    for model_name in CANDIDATE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents
            )
            if response and response.text:
                await status_msg.edit_text(response.text)
                return
        except Exception as e:
            logger.warning(f"Model {model_name} failed: {e}. Trying fallback...")
            last_error = str(e)

    await status_msg.edit_text(
        f"❌ Could not reach Gemini AI models.\n"
        f"Error details: `{last_error}`",
        parse_mode="Markdown"
    )
