"""WorldHistoryEngine: Tích lũy lịch sử thế giới qua từng tick."""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

COLLECTION_FOUNDING = "world_history_founding"
COLLECTION_TICKS    = "world_history_ticks"


class WorldHistoryEngine:

    def __init__(self, db: ChimeraDB):
        self.db = db

    # ── Founding history (từ WorldGenesis) ──────────────────────────────────

    def seed_from_genesis(self, world_history_data: Dict):
        """Ghi WorldHistory từ WorldGenesis vào MongoDB."""
        self.db.permanent[COLLECTION_FOUNDING].delete_many({})
        self.db.permanent[COLLECTION_FOUNDING].insert_one(world_history_data)
        logger.info(
            f"[WorldHistoryEngine] Đã seed "
            f"{len(world_history_data.get('founding_events', []))} founding events."
        )

    def get_era_summary(self) -> str:
        """Trả về tóm tắt kỷ nguyên cho ContextSliceV2 và A1."""
        doc = self.db.permanent[COLLECTION_FOUNDING].find_one({}, {"_id": 0})
        if not doc:
            return "Thế giới chưa có lịch sử nền."
        return f"{doc.get('era_name', '')} — {doc.get('era_tagline', '')}"

    # ── Tick history (tích lũy từng tick) ───────────────────────────────────

    def append_tick_event(
        self,
        tick: int,
        event_type: str,
        description: str,
        involved_chars: Optional[List[str]] = None,
        involved_factions: Optional[List[str]] = None,
        significance: int = 50,
    ):
        """Ghi 1 sự kiện vào lịch sử tick."""
        doc = {
            "tick": tick,
            "event_type": event_type,
            "description": description,
            "involved_chars": involved_chars or [],
            "involved_factions": involved_factions or [],
            "significance": significance,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.permanent[COLLECTION_TICKS].insert_one(doc)
        logger.debug(
            f"[WorldHistoryEngine] Tick {tick} — {event_type}: {description[:60]}"
        )

    def get_recent_history(self, n_ticks: int = 10) -> List[Dict]:
        """Lấy N tick gần nhất từ lịch sử."""
        cursor = (
            self.db.permanent[COLLECTION_TICKS]
            .find({}, {"_id": 0})
            .sort("tick", -1)
            .limit(n_ticks * 5)  # tối đa 5 events/tick
        )
        return list(cursor)

    def get_significant_events(self, min_significance: int = 75) -> List[Dict]:
        """Lấy các sự kiện có mức ảnh hưởng cao (cho A1 context)."""
        cursor = (
            self.db.permanent[COLLECTION_TICKS]
            .find(
                {"significance": {"$gte": min_significance}},
                {"_id": 0},
            )
            .sort("tick", -1)
            .limit(20)
        )
        return list(cursor)

    def get_full_timeline_summary(self) -> Dict:
        """Tóm tắt toàn bộ timeline cho ContextSliceV2."""
        founding_doc = self.db.permanent[COLLECTION_FOUNDING].find_one(
            {}, {"_id": 0}
        )
        recent = self.get_recent_history(n_ticks=5)
        significant = self.get_significant_events(min_significance=80)

        return {
            "era_name": founding_doc.get("era_name", "") if founding_doc else "",
            "era_tagline": founding_doc.get("era_tagline", "") if founding_doc else "",
            "founding_events_count": len(
                founding_doc.get("founding_events", []) if founding_doc else []
            ),
            "recent_events": recent[:10],
            "landmark_events": significant[:5],
        }
