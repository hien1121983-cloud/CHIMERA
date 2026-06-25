"""Tram T0f: lay danh sach world rules dang ap dung."""
from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0fWorldRules(BaseStation):
    station_id = "T0f"

    def _execute(self):
        db = ChimeraDB()
        rules = db.safe_read("world_rules", {"active": {"$ne": False}}, db.permanent)
        return [r.get("rule_id") for r in rules if r.get("rule_id")]
