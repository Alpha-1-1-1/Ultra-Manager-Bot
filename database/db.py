import sqlite3
import os
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_data.db")

def init_db() -> None:
    """Initializes SQLite database and tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Reminders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            reminder_text TEXT,
            due_timestamp INTEGER,
            is_completed INTEGER DEFAULT 0
        )
    """)

    # Downloads history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            media_type TEXT,
            title TEXT,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("SQLite database initialized successfully.")

def log_user(user_id: int, username: Optional[str], first_name: str) -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (user_id, username, first_name))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging user {user_id}: {e}")

def log_download(user_id: int, media_type: str, title: str) -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO download_logs (user_id, media_type, title)
            VALUES (?, ?, ?)
        """, (user_id, media_type, title))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging download: {e}")

def get_stats() -> Tuple[int, int]:
    """Returns (total_users, total_downloads)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM download_logs")
        total_downloads = cursor.fetchone()[0]
        conn.close()
        return total_users, total_downloads
    except Exception:
        return 0, 0
