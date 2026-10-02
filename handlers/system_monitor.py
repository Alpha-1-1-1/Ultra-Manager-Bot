import time
import platform
import logging
from datetime import timedelta
from telegram import Update
from telegram.ext import ContextTypes
import psutil

logger = logging.getLogger(__name__)

# Track bot start time for uptime calculation
BOT_START_TIME = time.time()

def get_size_gb(bytes_num: int) -> float:
    return round(bytes_num / (1024 ** 3), 2)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Returns real-time system and bot status metrics."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_count(logical=True)

    ram = psutil.virtual_memory()
    ram_total = get_size_gb(ram.total)
    ram_used = get_size_gb(ram.used)
    ram_percent = ram.percent

    disk = psutil.disk_usage("/")
    disk_total = get_size_gb(disk.total)
    disk_used = get_size_gb(disk.used)
    disk_percent = disk.percent

    uptime_seconds = int(time.time() - BOT_START_TIME)
    uptime_str = str(timedelta(seconds=uptime_seconds))

    os_info = f"{platform.system()} {platform.release()}"

    status_text = (
        "📊 **System & Bot Resource Monitor**\n\n"
        f"🖥️ **OS**: `{os_info}`\n"
        f"⏱️ **Bot Uptime**: `{uptime_str}`\n\n"
        f"⚡ **CPU Usage**: `{cpu_percent}%` ({cpu_cores} Threads)\n"
        f"🧠 **RAM Usage**: `{ram_used} GB / {ram_total} GB` (`{ram_percent}%`)\n"
        f"💾 **Disk Space**: `{disk_used} GB / {disk_total} GB` (`{disk_percent}%`)\n\n"
        "✅ All core services are running normally!"
    )

    await update.message.reply_text(status_text, parse_mode="Markdown")
