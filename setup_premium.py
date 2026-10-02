import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client

# Load credentials from .env
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

async def main():
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID or TELEGRAM_API_HASH is missing in your .env file!")
        print("Please add them to your .env file first.")
        return

    print("🚀 Starting Telegram Premium 4GB Uploader Authentication...")
    print(f"Using API_ID: {API_ID}")

    app = Client(
        name="premium_uploader",
        api_id=int(API_ID),
        api_hash=API_HASH,
        workdir=os.path.dirname(os.path.abspath(__file__))
    )

    await app.start()
    me = await app.get_me()
    print("\n✅ Successfully authenticated!")
    print(f"Logged in as: {me.first_name} (@{me.username or 'No username'})")
    print(f"Telegram Premium Active: {me.is_premium}")
    print("\n🎉 Your 4GB upload session is ready and saved as premium_uploader.session!")
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
