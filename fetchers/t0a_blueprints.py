"""Tram T0a (Va M-08: kiem tra count < 9)."""
import random

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0aBlueprints(BaseStation):
    station_id = "T0a"

    def _execute(self):
        db = ChimeraDB()
        blueprints = db.safe_read(
            "character_blueprints",
            {"used": {"$ne": True}},
            db.permanent,
        )

        # Va M-08: Kiem tra count truoc khi sample
        if len(blueprints) < 9:
            raise ValueError(
                f"[T0a] CRITICAL: Chi co {len(blueprints)}/9 blueprints kha dung. "
                f"Database can duoc bo sung ngay!"
            )

        selected = random.sample(blueprints, 9)
        for bp in selected:
            pool = bp.get("inner_conflict_pool", [])
            bp["inner_conflicts"] = random.sample(
                pool, k=min(len(pool), random.randint(5, 7))
            )
        return selected
