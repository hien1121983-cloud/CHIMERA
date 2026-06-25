"""Engine quan ly ap suat bi mat (ticking bombs)."""
import logging
from typing import List, Dict

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


class PressureEngine:
    def __init__(self, db: ChimeraDB):
        self.db = db

    def apply_pressure_change(self, delta: Dict):
        secret_id = delta.get("id")
        changes = delta.get("changes", {})
        if not secret_id or not changes:
            logger.warning(f"[PressureEngine] Delta khong hop le: {delta}")
            return
        self.db.permanent.secret_pressures.update_one(
            {"secret_id": secret_id},
            {"$inc": changes},
            upsert=True,
        )

    def tick_all(self, increment: int = 2):
        """Tang ap suat tu nhien moi tap cho moi bi mat chua no."""
        self.db.permanent.secret_pressures.update_many(
            {"pressure": {"$lt": 100}},
            {"$inc": {"pressure": increment}},
        )

    def get_active(self) -> List[Dict]:
        return list(self.db.permanent.secret_pressures.find({}, {"_id": 0}))

    def get_above_threshold(self) -> List[Dict]:
        """Lay cac bi mat da vuot nguong (bom no cham)."""
        result = []
        for s in self.db.permanent.secret_pressures.find({}, {"_id": 0}):
            if s.get("pressure", 0) >= s.get("threshold", 80):
                result.append(s)
        return result
