"""Tram T0g: boc 1 secret item chua dung."""
import random

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0gSecretItems(BaseStation):
    station_id = "T0g"

    def _execute(self):
        db = ChimeraDB()
        items = db.safe_read("secret_items", {"used": {"$ne": True}}, db.permanent)
        if not items:
            raise ValueError("[T0g] CRITICAL: Khong con secret item kha dung.")
        return random.choice(items)
