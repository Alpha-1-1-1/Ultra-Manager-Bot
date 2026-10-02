import os
import logging
from typing import Optional
from pyrogram import Client

logger = logging.getLogger(__name__)

_client: Optional[Client] = None

def get_premium_client() -> Optional[Client]:
    """Initializes and returns the Pyrogram client if credentials exist."""
    global _client
    if _client is not None:
        return _client

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        return None

    try:
        workdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        session_file = os.path.join(workdir, "premium_uploader.session")
        if not os.path.exists(session_file):
            logger.warning("premium_uploader.session not found. Run setup_premium.py first.")
            return None

        _client = Client(
            name="premium_uploader",
            api_id=int(api_id),
            api_hash=api_hash,
            workdir=workdir
        )
        return _client
    except Exception as e:
        logger.error(f"Error initializing Pyrogram client: {e}")
        return None

async def upload_premium_file(chat_id: int, file_path: str, caption: str, media_type: str = "video") -> bool:
    """Uploads large files (up to 4GB) using the Telegram Premium MTProto session."""
    client = get_premium_client()
    if not client:
        return False

    need_stop = False
    if not client.is_connected:
        await client.start()
        need_stop = True

    try:
        if media_type == "video":
            await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                supports_streaming=True
            )
        elif media_type == "audio":
            await client.send_audio(
                chat_id=chat_id,
                audio=file_path,
                caption=caption
            )
        else:
            await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption
            )
        return True
    except Exception as e:
        logger.error(f"Failed to upload via Premium MTProto: {e}")
        raise e
    finally:
        if need_stop and client.is_connected:
            await client.stop()
