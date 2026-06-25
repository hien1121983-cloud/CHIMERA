"""Engine cap nhat kinh te the gioi."""
import logging
from typing import Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class EconomyEngine:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply(self, delta: Dict):
        target = delta.get("id", "global")
        changes = delta.get("changes", {})
        if not changes:
            logger.warning(f"[EconomyEngine] Delta thieu changes: {delta}")
            return
        self.db.permanent.economy_states.update_one(
            {"economy_id": target},
            {"$inc": changes},
            upsert=True,
        )
        logger.info(f"[EconomyEngine] Cap nhat {target}: {changes}")
