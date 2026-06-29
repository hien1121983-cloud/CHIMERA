"""Quan ly pool API Key voi round-robin thread-safe."""
import os
import threading
import logging
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class APIKeyPool:
    """Quan ly pool API Key voi round-robin thread-safe."""

    def __init__(self, env_prefix: str, total: int):
        self.prefix = env_prefix
        self.keys: List[str] = []
        self.failed_keys: set = set()
        self.current_index: int = 0
        self._lock = threading.Lock()

        for i in range(1, total + 1):
            key = os.getenv(f"{env_prefix}_{i}")
            if key:
                self.keys.append(key)
            else:
                logger.warning(f"[CredManager] Thieu {env_prefix}_{i} trong .env")

        if not self.keys:
            logger.warning(
                f"[CredManager] Khong tim thay bat ky key nao voi prefix {env_prefix}."
            )

    def get_next(self) -> Optional[str]:
        """Lay key tiep theo (round-robin), bo qua key loi."""
        with self._lock:
            active_keys = [k for k in self.keys if k not in self.failed_keys]
            if not active_keys:
                logger.critical(f"[CredManager] Toan bo {self.prefix} key da loi.")
                return None
            key = active_keys[self.current_index % len(active_keys)]
            self.current_index += 1
            return key

    def mark_failed(self, key: str) -> None:
        """Danh dau key loi, loai khoi pool tam thoi."""
        with self._lock:
            self.failed_keys.add(key)
            logger.error(
                f"[CredManager] Key {key[:10]}... bi loai. "
                f"Con {len(self.keys) - len(self.failed_keys)} key hoat dong."
            )

    def reset_failed(self) -> None:
        """Reset pool (dung sau chu ky rotation)."""
        with self._lock:
            self.failed_keys.clear()
            logger.info(f"[CredManager] Da reset pool {self.prefix}.")

    @property
    def active_count(self) -> int:
        return len(self.keys) - len(self.failed_keys)


# Khoi tao pool toan cuc
GEMINI_POOL = APIKeyPool("GEMINI_KEY", total=7)
CLAUDE_POOL = APIKeyPool("CLAUDE_KEY", total=0)
ELEVENLABS_POOL = APIKeyPool("ELEVENLABS_KEY", total=0)
CEREBRAS_POOL = APIKeyPool("CEREBRAS_API_KEY", total=0)
