"""Database execution layer for FacebookSnoof using SQLite in WAL mode."""

import os
import sqlite3
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("FacebookSnoof.Database")


class DatabaseManager:
    """Manages SQLite database connections, schema creation, and data persistence."""

    def __init__(self, db_path: str = "database/tracker.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a new SQLite database connection with row factory enabled."""
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Initialize the database schema and indexes."""
        logger.info(f"Initializing database at: {self.db_path}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Monitored groups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitored_groups (
                    group_id TEXT PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    last_scraped_at DATETIME
                );
            """)

            # Extracted marketplace posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    post_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    author_name TEXT,
                    post_text TEXT,
                    post_url TEXT NOT NULL,
                    post_timestamp DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES monitored_groups(group_id)
                );
            """)

            # Cognitive deal evaluations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deal_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT UNIQUE NOT NULL,
                    hardware_name TEXT,
                    item_category TEXT,
                    asking_price INTEGER,
                    estimated_market_price INTEGER,
                    condition_summary TEXT,
                    deal_score INTEGER,
                    verdict TEXT,
                    is_notified INTEGER DEFAULT 0,
                    evaluated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(post_id)
                );
            """)

            # Performance indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(post_timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_score ON deal_evaluations(deal_score);")
            
            conn.commit()
        logger.info("Database schema initialized successfully.")

    def sync_monitored_groups(self, groups: List[Dict[str, str]]) -> None:
        """Sync monitored Facebook groups from runtime configuration."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for group in groups:
                group_id = str(group["id"])
                group_name = group.get("name", "Unknown Group")
                cursor.execute("""
                    INSERT INTO monitored_groups (group_id, group_name, is_active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(group_id) DO UPDATE SET group_name = excluded.group_name;
                """, (group_id, group_name))
            conn.commit()

    def post_exists(self, post_id: str) -> bool:
        """Check whether a post has already been processed and saved."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM posts WHERE post_id = ? LIMIT 1;", (str(post_id),))
            return cursor.fetchone() is not None

    def insert_post(
        self,
        post_id: str,
        group_id: str,
        post_url: str,
        post_text: str,
        author_name: Optional[str] = None,
        post_timestamp: Optional[str] = None
    ) -> bool:
        """Insert a newly extracted raw post into the database. Returns True if inserted."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO posts (post_id, group_id, post_url, post_text, author_name, post_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (str(post_id), str(group_id), post_url, post_text, author_name, post_timestamp))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Post ID {post_id} insert failed: {e}")
            return False

    def save_deal_evaluation(
        self,
        post_id: str,
        hardware_name: str,
        item_category: str,
        asking_price: int,
        estimated_market_price: int,
        condition_summary: str,
        deal_score: int,
        verdict: str
    ) -> Optional[int]:
        """Save Ollama cognitive valuation result into database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO deal_evaluations (
                        post_id, hardware_name, item_category, asking_price,
                        estimated_market_price, condition_summary, deal_score, verdict
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    str(post_id), hardware_name, item_category, asking_price,
                    estimated_market_price, condition_summary, deal_score, verdict
                ))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"Deal evaluation for post {post_id} already exists.")
            return None

    def mark_as_notified(self, evaluation_id: int) -> None:
        """Mark a deal evaluation as notified to Telegram."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE deal_evaluations SET is_notified = 1 WHERE id = ?;
            """, (evaluation_id,))
            conn.commit()

    def update_group_last_scraped(self, group_id: str) -> None:
        """Update last scraped timestamp for a monitored group."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE monitored_groups SET last_scraped_at = CURRENT_TIMESTAMP WHERE group_id = ?;
            """, (str(group_id),))
            conn.commit()
