"""Tram T0e: lay trend phrase tu nen tang."""
import random

from fetchers.base_station import BaseStation


class T0eTrends(BaseStation):
    station_id = "T0e"

    _PHRASES = [
        {"phrase": "khong ai biet su that", "platform": "TikTok"},
        {"phrase": "cu ngo la ket thuc", "platform": "TikTok"},
        {"phrase": "buoc ngoat cuoc doi", "platform": "YouTube"},
    ]

    def _execute(self):
        return random.choice(self._PHRASES)
