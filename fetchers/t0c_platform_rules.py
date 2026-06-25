"""Tram T0c: doc quy tac kiem duyet nen tang."""
import json

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB


class T0cPlatformRules(BaseStation):
    station_id = "T0c"

    def _execute(self):
        db = ChimeraDB()
        rules = db.safe_read("platform_rules", {}, db.permanent)
        if rules:
            return rules[0] if isinstance(rules, list) else rules
        with open("config/platform_rules.json", "r", encoding="utf-8") as f:
            return json.load(f)
