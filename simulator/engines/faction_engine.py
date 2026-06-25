"""Engine cap nhat trang thai phe phai."""
import logging
from typing import Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class FactionEngine:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply(self, delta: Dict):
        faction_id = delta.get("id")
        changes = delta.get("changes", {})
        if not faction_id or not changes:
            logger.warning(f"[FactionEngine] Delta thieu id hoac changes: {delta}")
            return
        self.db.permanent.faction_states.update_one(
            {"faction_id": faction_id},
            {"$inc": changes},
            upsert=True,
        )
        logger.info(f"[FactionEngine] Cap nhat {faction_id}: {changes}")

    def get_all(self) -> Dict:
        states = self.db.permanent.faction_states.find({}, {"_id": 0})
        return {s["faction_id"]: s for s in states}
