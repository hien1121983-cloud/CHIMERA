"""Tram T0: thu thap khung 15 phan canh (archetypes)."""
import random

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0Archetypes(BaseStation):
    station_id = "T0"

    def _execute(self):
        db = ChimeraDB()
        archetypes = db.safe_read("archetypes", {}, db.permanent)
        if not archetypes:
            return []
        return random.choice(archetypes) if isinstance(archetypes, list) else archetypes
