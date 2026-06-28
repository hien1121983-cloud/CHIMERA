"""Singleton quan ly 3 cum MongoDB + SQLite fallback."""
import os
import json
import sqlite3
import logging
import threading
from typing import Optional

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class ChimeraDB:
    """Singleton quan ly 3 cum MongoDB + SQLite fallback."""

    _instance: Optional["ChimeraDB"] = None
    # FIX #1: Lock cap class de dam bao double-checked locking thread-safe.
    # Truoc day khong co lock -> 2 thread dong thoi vao __new__ co the
    # tao 2 MongoClient rieng khi _instance chua duoc set.
    _class_lock = threading.Lock()

    def __new__(cls):
        # Fast path (khong can lock neu da co instance)
        if cls._instance is None:
            with cls._class_lock:
                # Re-check ben trong lock (double-checked locking pattern)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.permanent = MongoClient(os.getenv("MONGODB_URI_PERMANENT"))["chimera_permanent"]
        self.purgatory = MongoClient(os.getenv("MONGODB_URI_PURGATORY"))["chimera_purgatory"]
        self.canon = MongoClient(os.getenv("MONGODB_URI_CANON"))["chimera_canon"]

        self.sqlite_cache = self._init_sqlite()
        # FIX #5: Lock de serialize cac SQLite write tu nhieu thread.
        # check_same_thread=False chi tat canh bao, khong tu dong serialize.
        self._sqlite_lock = threading.Lock()
        self._create_indexes()
        self._initialized = True

    def _init_sqlite(self) -> sqlite3.Connection:
        """Khoi tao SQLite cache."""
        cache_path = os.getenv("LOCAL_CACHE_PATH", "./cache/local_cache.sqlite")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        conn = sqlite3.connect(cache_path, check_same_thread=False)

        # FIX #5: WAL mode cho phep concurrent reads trong khi write dang dien ra.
        # synchronous=NORMAL giam fsync (an toan cho cache, khong phai primary store).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # Tao san mot so bang mac dinh
        tables = [
            "character_blueprints", "world_rules", "secret_items",
            "location_settings", "archetypes", "platform_rules",
            "episode_summaries",
        ]
        for table in tables:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        conn.commit()
        return conn

    def _create_indexes(self):
        """Tao index cho MongoDB."""
        try:
            self.permanent.character_blueprints.create_index([("used", 1), ("created_at", -1)])
            self.permanent.location_settings.create_index([("cooldown_remaining", 1)])
            self.permanent.secret_items.create_index([("used", 1)])

            self.purgatory.draft_scripts.create_index(
                [("created_at", 1)], expireAfterSeconds=604800
            )
            self.purgatory.execution_json.create_index(
                [("created_at", 1)], expireAfterSeconds=604800
            )

            self.canon.episode_summaries.create_index([("episode_number", -1)])
        except Exception as e:
            logger.warning(f"[DB] Khong tao duoc index: {e}")

    def safe_read(self, collection_name: str, query: dict, db_source):
        """Doc tu MongoDB voi fallback SQLite."""
        try:
            result = list(db_source[collection_name].find(query, {"_id": 0}))
            self._cache_to_sqlite(collection_name, result)
            return result
        except Exception as e:
            logger.warning(f"[DB] MongoDB loi, fallback SQLite: {e}")
            return self._read_from_sqlite(collection_name)

    def _cache_to_sqlite(self, collection_name: str, data: list):
        """Ghi de cache SQLite (thread-safe voi write lock)."""
        try:
            with self._sqlite_lock:
                # Tu dong tao bang neu chua co (Giai quyet loi no such table)
                self.sqlite_cache.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {collection_name} (
                        id TEXT PRIMARY KEY,
                        data TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self.sqlite_cache.execute(f"DELETE FROM {collection_name}")
                for item in data:
                    self.sqlite_cache.execute(
                        # Dung INSERT OR REPLACE de de len thay vi loi UNIQUE constraint
                        f"INSERT OR REPLACE INTO {collection_name} (id, data) VALUES (?, ?)",
                        (
                            str(item.get("_id", item.get("id", ""))),
                            json.dumps(item, ensure_ascii=False),
                        ),
                    )
                self.sqlite_cache.commit()
        except Exception as e:
            logger.error(f"[DB] Loi cache SQLite ghi bang {collection_name}: {e}")

    def _read_from_sqlite(self, collection_name: str) -> list:
        """Doc tu SQLite cache."""
        try:
            # Dam bao bang ton tai truoc khi doc de tranh loi no such table
            self.sqlite_cache.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {collection_name} (
                    id TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor = self.sqlite_cache.execute(f"SELECT data FROM {collection_name}")
            return [json.loads(row[0]) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[DB] Loi doc SQLite tu bang {collection_name}: {e}")
            return []
