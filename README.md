# 🚀 Ultra Manager Bot

A feature-packed, asynchronous multi-purpose Telegram Bot built with Python (`python-telegram-bot` v22), Gemini 3.8 Flash AI, yt-dlp, SQLite, and system monitoring tools.

---

## ✨ Features

- **🎛️ Interactive Menu (`/menu`)**: Dynamic inline keyboards for seamless navigation.
- **🎬 Advanced Video Downloader (`yt-dlp`)**:
  - Paste any video link (YouTube, Shorts, Instagram, TikTok, Twitter/X, Reddit).
  - Thumbnail preview card.
  - Multi-resolution selection (`1080p`, `720p`, `480p`, `360p`, `Best (<50MB)`).
  - `SponsorBlock` integration & `Split by Chapters`.
  - Video segment cutting (`/cut <session> <start> <end>`).
- **🎵 Music / Song Downloader (`/song`)**:
  - Search any song by title or artist and receive an MP3 with complete audio tags.
- **🤖 Gemini 3.8 Flash AI (`/ai`)**:
  - AI chat & vision (multimodal image analysis).
  - Automatic fallback mechanism for zero-downtime answers.
- **📈 Crypto Price Tracker (`/crypto`)**:
  - Real-time market prices in USD & INR with 24-hour changes (e.g. `/crypto btc`, `/crypto eth`).
- **📰 Live Breaking News (`/news`)**:
  - Fresh headlines for Tech, World, and Science categories.
- **📊 System & Bot Health Monitor (`/status`)**:
  - Real-time CPU usage, RAM utilization, Disk storage, and Bot uptime.
- **⏰ Scheduled Reminders (`/remind`)**:
  - Built-in timer alerts (e.g., `/remind 10m Take a break`).
- **🛡️ Group Moderation**:
  - Auto-welcome for new members, `/warn`, `/kick`, and `/ban` admin commands.
- **📁 Image Format Converter (`/convert`)**:
  - Convert images between PNG, JPG, and WEBP.
- **💾 SQLite Database**:
  - Auto-records user activity and download logs.

---

## 🛠️ Quick Setup (Local Machine)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<your-username>/Ultra_Manager_bot.git
   cd Ultra_Manager_bot
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
   GEMINI_API_KEY=your_gemini_api_key_from_aistudio
   ```

5. **Run the bot**:
   ```bash
   python main.py
   ```

---

## ☁️ Running on Kaggle / Cloud

1. In Kaggle, enable **Internet: Always On** in Notebook Settings.
2. Add `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` under **Add-ons ➔ Secrets**.
3. Clone and run:
   ```bash
   !git clone https://github.com/<your-username>/Ultra_Manager_bot.git
   %cd Ultra_Manager_bot
   !pip install -r requirements.txt
   !python main.py
   ```

---

## 📜 Commands Reference

| Command | Description |
| :--- | :--- |
| `/start` | Starts the bot and displays the welcome message |
| `/menu` | Opens the interactive main navigation menu |
| `<link>` or `/download <url>` | Extracts video details and shows download options |
| `/song <title>` | Searches and downloads music track as MP3 |
| `/ai <prompt>` | Asks Gemini 3.8 Flash AI (or caption on photos) |
| `/remind <time> <msg>` | Sets a timer reminder (e.g. `30s`, `15m`, `2h`) |
| `/crypto [symbol]` | Live cryptocurrency price (e.g. `btc`, `eth`, `sol`) |
| `/news [category]` | Fetches top headlines (`tech`, `world`, `science`) |
| `/status` | Displays real-time CPU, RAM, Disk, and bot uptime |
| `/cut <id> <start> <end>` | Cuts video segments |
| `/convert <png\|jpg>` | Converts replied photo format |
| `/warn`, `/kick`, `/ban` | Group admin moderation tools |
