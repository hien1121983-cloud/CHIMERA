"""Tram T0h: boc supporting cast (wildcards)."""
import random

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0hWildcards(BaseStation):
    station_id = "T0h"

    def _execute(self):
        db = ChimeraDB()
        cast = db.safe_read("character_blueprints", {"role": "supporting"}, db.permanent)
        if not cast:
            raise ValueError("[T0h] CRITICAL: Khong co supporting cast kha dung.")
        k = min(len(cast), random.randint(2, 5))
        return random.sample(cast, k)
