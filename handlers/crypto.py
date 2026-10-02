import logging
import httpx
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Symbol mapping
POPULAR_COINS = {
    "btc": ("bitcoin", "BTC"),
    "eth": ("ethereum", "ETH"),
    "sol": ("solana", "SOL"),
    "doge": ("dogecoin", "DOGE"),
    "xrp": ("ripple", "XRP"),
    "bnb": ("binancecoin", "BNB"),
    "ada": ("cardano", "ADA"),
    "trx": ("tron", "TRX"),
}

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches live cryptocurrency prices: /crypto [symbol]."""
    symbol = context.args[0].lower() if context.args else "btc"

    coin_id, ticker = POPULAR_COINS.get(symbol, (symbol, symbol.upper()))

    status_msg = await update.message.reply_text(f"📈 Fetching market data for `{ticker}`...", parse_mode="Markdown")

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr&include_24hr_change=true"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()

        if coin_id not in data:
            # Fallback to Binance ticker if CoinGecko ID wasn't matched
            binance_url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={ticker}USDT"
            async with httpx.AsyncClient(timeout=10.0) as client:
                b_resp = await client.get(binance_url)
                if b_resp.status_code == 200:
                    b_data = b_resp.json()
                    price_usd = float(b_data["lastPrice"])
                    change_24h = float(b_data["priceChangePercent"])
                    change_emoji = "🟢" if change_24h >= 0 else "🔴"
                    msg = (
                        f"🪙 **{ticker} Market Overview**\n\n"
                        f"💵 **Price (USD)**: `${price_usd:,.2f}`\n"
                        f"{change_emoji} **24h Change**: `{change_24h:+.2f}%`\n"
                        f"📊 **Source**: Binance"
                    )
                    await status_msg.edit_text(msg, parse_mode="Markdown")
                    return
                else:
                    await status_msg.edit_text(f"❌ Could not find crypto symbol: `{ticker}`")
                    return

        info = data[coin_id]
        usd = info.get("usd", 0)
        inr = info.get("inr", 0)
        change_24h = info.get("usd_24h_change", 0.0)
        change_emoji = "🟢" if change_24h >= 0 else "🔴"

        text = (
            f"🪙 **{ticker} Live Market Price**\n\n"
            f"💵 **USD**: `${usd:,.2f}`\n"
            f"🇮🇳 **INR**: `₹{inr:,.2f}`\n"
            f"{change_emoji} **24h Change**: `{change_24h:+.2f}%`\n\n"
            f"💡 *Tip: Check other coins like `/crypto eth`, `/crypto sol`, `/crypto doge`*"
        )
        await status_msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Crypto fetch error: {e}")
        await status_msg.edit_text("❌ Error fetching crypto price. Please try again later.")
