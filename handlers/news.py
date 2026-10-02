import logging
import httpx
import xml.etree.ElementTree as ET
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

FEEDS = {
    "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
}

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches top breaking news headlines: /news [tech|world|science]."""
    category = context.args[0].lower() if context.args else "tech"
    if category not in FEEDS:
        category = "tech"

    feed_url = FEEDS[category]
    status_msg = await update.message.reply_text(f"📰 Fetching latest **{category.title()}** headlines...", parse_mode="Markdown")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            xml_data = resp.text

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")[:5]

        if not items:
            await status_msg.edit_text("❌ No news items found at the moment.")
            return

        headlines = [f"📰 **Latest {category.title()} News**:\n"]
        for idx, item in enumerate(items, 1):
            title = item.find("title").text if item.find("title") is not None else "No Title"
            link = item.find("link").text if item.find("link") is not None else ""
            headlines.append(f"{idx}. [{title}]({link})")

        headlines.append("\n💡 *Try `/news world` or `/news science`*")
        await status_msg.edit_text("\n".join(headlines), parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"News fetch error: {e}")
        await status_msg.edit_text("❌ Error fetching news feed. Please try again.")
