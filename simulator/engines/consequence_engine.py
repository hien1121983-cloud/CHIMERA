"""Engine quan ly hau qua dang dien ra."""
import logging
from typing import List, Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class ConsequenceEngine:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply(self, delta: Dict):
        event_id = delta.get("event_id")
        if not event_id:
            logger.warning(f"[ConsequenceEngine] Delta thieu event_id: {delta}")
            return
        self.db.permanent.consequences.update_one(
            {"event_id": event_id},
            {"$set": delta},
            upsert=True,
        )

    def get_active(self) -> List[Dict]:
        return list(
            self.db.permanent.consequences.find({"resolved": {"$ne": True}}, {"_id": 0})
        )
