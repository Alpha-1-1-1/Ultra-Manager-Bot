import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

async def main():
    if not API_ID or not API_HASH:
        print("❌ Error: Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
        return

    workdir = os.path.dirname(os.path.abspath(__file__))
    session_file = os.path.join(workdir, "premium_uploader.session")
    if not os.path.exists(session_file):
        print("❌ Error: premium_uploader.session not found. Run setup_premium.py first to log in.")
        return

    app = Client(
        name="premium_uploader",
        api_id=int(API_ID),
        api_hash=API_HASH,
        workdir=workdir
    )

    await app.start()
    session_str = await app.export_session_string()
    await app.stop()

    print("\n" + "=" * 60)
    print("🔑 YOUR TELEGRAM_SESSION_STRING (FOR KAGGLE SECRETS):")
    print("=" * 60)
    print(session_str)
    print("=" * 60)
    print("\nCopy this string and add it as a secret named TELEGRAM_SESSION_STRING in Kaggle!")

if __name__ == "__main__":
    asyncio.run(main())
