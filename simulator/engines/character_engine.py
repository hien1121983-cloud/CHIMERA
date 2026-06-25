"""Engine cap nhat character state."""
import logging
from typing import Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class CharacterEngine:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply(self, delta: Dict):
        """Ap dung delta cho character state."""
        char_id = delta.get("id")
        changes = delta.get("changes", {})

        if not char_id or not changes:
            logger.warning(f"[CharacterEngine] Delta thieu id hoac changes: {delta}")
            return

        # Dung $inc de tu xu ly +15 hoac -20
        self.db.permanent.character_states.update_one(
            {"character_id": char_id},
            {"$inc": changes},
            upsert=True,
        )
        logger.info(f"[CharacterEngine] Cap nhat {char_id}: {changes}")

    def get_all(self) -> Dict:
        """Lay toan bo character states."""
        states = self.db.permanent.character_states.find({}, {"_id": 0})
        return {s["character_id"]: s for s in states}
