"""Tram T0d (Va M-10: dung pattern_to_chimera.json)."""
import json
import logging
from dataclasses import dataclass
from typing import List, Dict

import feedparser

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)


@dataclass
class BehaviorPattern:
    pattern_id: str
    strength: int
    source_type: str
    raw_sample: str


@dataclass
class WorldPressure:
    pressure_id: str
    type: str
    intensity: int
    affected_factions: List[str]
    chimera_translation: str


@dataclass
class RDEOutput:
    social_pressure: List[WorldPressure]
    technology_pressure: List[WorldPressure]
    culture_pressure: List[WorldPressure]
    economy_pressure: List[WorldPressure]
    emotion_pressure: List[WorldPressure]


class T0dRDE(BaseStation):
    station_id = "T0d"

    def __init__(self):
        self.genre = self._detect_genre()
        self.pattern_map = self._load_pattern_map()

    def _detect_genre(self) -> str:
        """Doc genre cua vu tru tu database."""
        try:
            db = ChimeraDB()
            world_info = db.permanent.world_info.find_one({})
            return world_info.get("genre", "fantasy") if world_info else "fantasy"
        except Exception:
            return "fantasy"

    def _load_pattern_map(self) -> Dict:
        """Va M-10: Load file pattern_to_chimera.json."""
        with open("config/pattern_to_chimera.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def _execute(self) -> RDEOutput:
        raw_items = self._collect_raw_data()
        patterns = [self._classify_to_pattern(item) for item in raw_items]
        pressures = self._translate_to_pressures(patterns)
        return self._group_by_type(pressures)

    def _collect_raw_data(self) -> List[Dict]:
        """Thu thap 50 news + 20 trends + 20 hashtags."""
        items = []
        rss_urls = [
            "https://vnexpress.net/rss/tin-tuc-moi-nhat.rss",
            "https://tuoitre.vn/rss/thoi-su.rss",
        ]
        for url in rss_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:25]:
                    items.append({
                        "type": "news",
                        "title": entry.title,
                        "summary": entry.get("summary", ""),
                    })
            except Exception:
                pass  # Fail-safe

        try:
            items.extend(self._fetch_google_trends())
        except Exception:
            pass

        return items[:90]

    def _classify_to_pattern(self, item: Dict) -> BehaviorPattern:
        """Phan loai tin tuc thanh pattern bang regex + keyword."""
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        keyword_map = {
            "fear_of_replacement": ["thay the", "replace", "ai", "robot", "mat viec"],
            "hidden_truth_exposed": ["lo bi mat", "phat hien", "scandal", "bi khui"],
            "economic_collapse": ["sap", "khung hoang", "lam phat", "that nghiep"],
            "authority_distrust": ["tay chay", "bieu tinh", "nghi ngo", "mat niem tin"],
        }
        for pattern_id, keywords in keyword_map.items():
            if any(kw in text for kw in keywords):
                strength = min(100, len([kw for kw in keywords if kw in text]) * 25)
                return BehaviorPattern(
                    pattern_id=pattern_id,
                    strength=strength,
                    source_type=item["type"],
                    raw_sample=text[:200],
                )
        return BehaviorPattern("neutral", 30, item.get("type", "unknown"), text[:200])

    def _translate_to_pressures(self, patterns: List[BehaviorPattern]) -> List[WorldPressure]:
        """Va M-10: Map pattern -> chimera_translation theo genre."""
        pressures = []
        for i, p in enumerate(patterns):
            if p.pattern_id == "neutral":
                continue
            translation = self.pattern_map.get(p.pattern_id, {}).get(self.genre, p.pattern_id)
            pressures.append(WorldPressure(
                pressure_id=f"P_{i:03d}",
                type=p.pattern_id,
                intensity=p.strength,
                affected_factions=["guild", "church"],
                chimera_translation=translation,
            ))
        return pressures

    def _group_by_type(self, pressures: List[WorldPressure]) -> RDEOutput:
        """Gom nhom pressures theo 5 loai."""
        type_map = {
            "fear_of_replacement": "technology_pressure",
            "hidden_truth_exposed": "social_pressure",
            "economic_collapse": "economy_pressure",
            "authority_distrust": "social_pressure",
        }
        result = {
            "social_pressure": [],
            "technology_pressure": [],
            "culture_pressure": [],
            "economy_pressure": [],
            "emotion_pressure": [],
        }
        for p in pressures:
            category = type_map.get(p.type, "culture_pressure")
            result[category].append(p)
        return RDEOutput(**result)

    def _fetch_google_trends(self) -> List[Dict]:
        """Gia lap fetch Google Trends."""
        return []
