"""Tram T0b (Va I-02: cooldown tu settings)."""
import random
import asyncio

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB
from config.settings import settings
from core.helpers import get_current_episode, send_telegram_alert


class T0bLocations(BaseStation):
    station_id = "T0b"

    def _execute(self):
        db = ChimeraDB()
        num_locations = random.randint(1, 6)

        available = db.safe_read(
            "location_settings",
            {"cooldown_remaining": 0},
            db.permanent,
        )

        if not available:
            try:
                asyncio.run(
                    send_telegram_alert(
                        "[T0b] Toan bo location dang cooldown, dung tam cooldown thap nhat"
                    )
                )
            except Exception:
                pass
            available = list(
                db.permanent.location_settings.find()
                .sort("cooldown_remaining", 1)
                .limit(num_locations)
            )

        if not available:
            raise ValueError("[T0b] Khong co location nao kha dung.")

        selected = random.sample(available, min(num_locations, len(available)))

        # Va I-02: Doc cooldown tu settings
        cooldown_value = settings.LOCATION_COOLDOWN_EPISODES
        current_ep = get_current_episode()

        for loc in selected:
            if "_id" in loc:
                db.permanent.location_settings.update_one(
                    {"_id": loc["_id"]},
                    {"$set": {
                        "cooldown_remaining": cooldown_value,
                        "last_used_episode": current_ep,
                    }},
                )
        return selected
