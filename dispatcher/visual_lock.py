"""Quan ly visual_lock_seed cho tung nhan vat (giu nhat quan ngoai hinh)."""
import logging
import hashlib

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class VisualLockManager:
    def __init__(self):
        self.db = ChimeraDB()
        self._cache = {}

    def get_seed_for_character(self, character_name: str) -> int:
        """Lay seed on dinh cho nhan vat (deterministic)."""
        if character_name in self._cache:
            return self._cache[character_name]

        seed = None
        try:
            doc = self.db.permanent.visual_locks.find_one(
                {"character": character_name}
            )
            if doc and doc.get("seed") is not None:
                seed = int(doc["seed"])
        except Exception as e:
            logger.warning(f"[VisualLock] Khong doc duoc DB: {e}")

        if seed is None:
            digest = hashlib.sha256(character_name.encode("utf-8")).hexdigest()
            seed = int(digest[:8], 16)
            try:
                self.db.permanent.visual_locks.update_one(
                    {"character": character_name},
                    {"$set": {"seed": seed}},
                    upsert=True,
                )
            except Exception:
                pass

        self._cache[character_name] = seed
        return seed

    def get_scene_seed(self, characters) -> int:
        """Seed dac trung cho scene dua tren nhan vat dau tien."""
        if not characters:
            return 0
        return self.get_seed_for_character(characters[0])
