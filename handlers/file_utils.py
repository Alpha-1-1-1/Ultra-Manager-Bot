import io
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

logger = logging.getLogger(__name__)

async def convert_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Converts images sent with /convert <png|jpg|webp>."""
    if not context.args:
        await update.message.reply_text(
            "💡 **Usage**: Reply to a photo with `/convert png` or `/convert jpg`.",
            parse_mode="Markdown"
        )
        return

    target_format = context.args[0].lower().strip()
    if target_format not in ["png", "jpg", "jpeg", "webp"]:
        await update.message.reply_text("❌ Supported format conversions: `png`, `jpg`, `webp`.")
        return

    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not photo:
        await update.message.reply_text("⚠️ Please send or reply to a photo message.")
        return

    status_msg = await update.message.reply_text("Processing image conversion... ⚙️")

    try:
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        image = Image.open(io.BytesIO(img_bytes))

        # Convert RGBA to RGB if saving to JPG
        if target_format in ["jpg", "jpeg"] and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        output_buffer = io.BytesIO()
        fmt = "JPEG" if target_format in ["jpg", "jpeg"] else target_format.upper()
        image.save(output_buffer, format=fmt)
        output_buffer.seek(0)
        output_buffer.name = f"converted_image.{target_format}"

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=output_buffer,
            caption=f"✅ Converted successfully to `{target_format.upper()}`!",
            parse_mode="Markdown"
        )
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error converting image: {e}")
        await status_msg.edit_text(f"❌ Failed to convert image: {str(e)}")
