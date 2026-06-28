"""Trạm T0d V2 — RDE dùng Gist TikTok thay Google Trends.

Luồng mới:
  1. Fetch JSON từ GIST_TREND_URL (do repo phụ cập nhật 4h/lần)
  2. Parse items → classify_to_pattern() → WorldPressure list
  3. Cache raw items vào MongoDB PERMANENT.trend_cache (fallback khi Gist down)
  4. Nếu Gist fail → đọc MongoDB cache → tiếp tục bình thường
  5. Return RDEOutput (cùng schema như trước, A1 không thay đổi gì)

MongoDB:  chimera_PERMANENT  →  collection: trend_cache
Document: {"_id": "latest", ...}  (upsert, 1 doc duy nhất)
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timezone

import feedparser
import requests

from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# ── URL Gist public (do repo phụ PATCH mỗi 4 giờ) ──────────────────────────
GIST_TREND_URL = (
    "https://gist.githubusercontent.com/"
    "tradeview113d8-code/36eb2530da8921c099ddc3e571e7b55c/"
    "raw/genz_hot_news.json"
)
GIST_TIMEOUT_SEC = 8
CACHE_MAX_AGE_HOURS = 25   # Nếu cache cũ hơn 25h → báo WARNING nhưng vẫn dùng


# ── Data classes (giữ nguyên từ V1) ─────────────────────────────────────────
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


# ── Mapping category TikTok → CHIMERA pattern ────────────────────────────────
# Key = giá trị field "category" trong genz_hot_news.json
# Value = pattern_id trong pattern_to_chimera.json
CATEGORY_TO_PATTERN: Dict[str, str] = {
    # Tài chính / kinh tế
    "finance":          "economic_collapse",
    "debt":             "economic_collapse",
    "bankruptcy":       "economic_collapse",
    "real_estate":      "economic_collapse",
    # Bóc phốt / scandal
    "scandal":          "hidden_truth_exposed",
    "expose":           "hidden_truth_exposed",
    "crime":            "hidden_truth_exposed",
    "corruption":       "hidden_truth_exposed",
    # Bất tin hệ thống
    "protest":          "authority_distrust",
    "distrust":         "authority_distrust",
    "injustice":        "authority_distrust",
    # AI / công nghệ thay người
    "ai":               "fear_of_replacement",
    "tech":             "fear_of_replacement",
    "robot":            "fear_of_replacement",
    "job_loss":         "fear_of_replacement",
    # Lãnh đạo bỏ trống / sụp đổ
    "leadership":       "power_vacuum",
    "ceo_gone":         "power_vacuum",
    # App/tech phản tác dụng
    "scam_app":         "technology_backfire",
    "deepfake":         "technology_backfire",
    # Cô lập xã hội / cancel culture
    "cancel":           "social_isolation",
    "relationship":     "social_isolation",
    "loneliness":       "social_isolation",
    # Lưỡng nan đạo đức
    "dilemma":          "moral_dilemma",
    "toxic":            "moral_dilemma",
    "betrayal":         "moral_dilemma",
    # Ký ức / di sản mất đi
    "nostalgia":        "lost_legacy",
    "tradition":        "lost_legacy",
    "heritage":         "lost_legacy",
}

# Mapping emotion → thêm weight vào intensity
EMOTION_INTENSITY_BOOST: Dict[str, int] = {
    "shock":   25,
    "anger":   20,
    "fear":    15,
    "sadness": 10,
    "disgust": 10,
    "joy":      0,
    "neutral":  0,
}

# Mapping pattern → RDEOutput bucket
PATTERN_TO_BUCKET: Dict[str, str] = {
    "economic_collapse":    "economy_pressure",
    "hidden_truth_exposed": "social_pressure",
    "authority_distrust":   "social_pressure",
    "fear_of_replacement":  "technology_pressure",
    "technology_backfire":  "technology_pressure",
    "power_vacuum":         "social_pressure",
    "social_isolation":     "emotion_pressure",
    "moral_dilemma":        "emotion_pressure",
    "lost_legacy":          "culture_pressure",
    "neutral":              "culture_pressure",
}


class T0dRDE(BaseStation):
    station_id = "T0d"

    def __init__(self):
        self.genre = self._detect_genre()
        self.pattern_map = self._load_pattern_map()
        self.db = ChimeraDB()

    def _detect_genre(self) -> str:
        try:
            db = ChimeraDB()
            world_info = db.permanent.world_info.find_one({})
            return world_info.get("genre", "urban_drama") if world_info else "urban_drama"
        except Exception:
            return "urban_drama"

    def _load_pattern_map(self) -> Dict:
        with open("config/pattern_to_chimera.json", "r", encoding="utf-8") as f:
            return json.load(f)

    # ═══════════════════════════════════════════════════════════════════════════
    # ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════════

    def _execute(self) -> RDEOutput:
        raw_items = self._collect_raw_data()
        patterns = [self._classify_to_pattern(item) for item in raw_items]
        pressures = self._translate_to_pressures(patterns)
        return self._group_by_type(pressures)

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA COLLECTION
    # ═══════════════════════════════════════════════════════════════════════════

    def _collect_raw_data(self) -> List[Dict]:
        """Thu thập dữ liệu từ 3 nguồn theo thứ tự ưu tiên."""
        items: List[Dict] = []

        # ── Nguồn 1: RSS báo VN (luôn chạy, baseline) ───────────────────────
        items.extend(self._fetch_rss_news())

        # ── Nguồn 2: Gist TikTok (ưu tiên cao — thay Google Trends) ─────────
        gist_items = self._fetch_gist_trends()
        if gist_items:
            items.extend(gist_items)
            logger.info(f"[T0d] Gist TikTok: {len(gist_items)} items")
        else:
            # ── Nguồn 3: MongoDB cache (fallback khi Gist down) ───────────────
            cached = self._load_trend_cache()
            if cached:
                items.extend(cached)
                logger.warning(
                    f"[T0d] Gist không khả dụng → dùng MongoDB cache "
                    f"({len(cached)} items)"
                )
            else:
                logger.error(
                    "[T0d] CẢ Gist LẪN MongoDB cache đều trống. "
                    "T0d chỉ có dữ liệu RSS. Context sẽ thiếu trend TikTok."
                )

        return items[:90]

    def _fetch_rss_news(self) -> List[Dict]:
        """RSS VnExpress + Tuổi Trẻ — baseline luôn chạy."""
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
                        "category": None,  # sẽ tự classify bằng keyword
                        "emotion": None,
                        "views": 0,
                    })
            except Exception as e:
                logger.warning(f"[T0d] RSS lỗi ({url}): {e}")
        return items

    def _fetch_gist_trends(self) -> List[Dict]:
        """Fetch JSON từ Gist public (repo phụ cập nhật 4h/lần).

        Schema Gist mong đợi (genz_hot_news.json):
        {
          "updated_at": "2026-06-28T10:00:00Z",
          "source": "tiktok_vn",
          "items": [
            {
              "title":    "Tiêu đề bài viral",
              "hashtags": ["#bocphot", "#taichinhpersonal"],
              "views":    5200000,
              "category": "scandal",
              "emotion":  "shock",
              "raw_text": "Tóm tắt nội dung bài đăng..."
            }
          ]
        }

        Nếu Gist down hoặc schema sai → trả [] để caller dùng MongoDB cache.
        """
        try:
            resp = requests.get(
                GIST_TREND_URL,
                timeout=GIST_TIMEOUT_SEC,
                headers={"User-Agent": "CHIMERA-Pipeline/5.0"},
            )
            resp.raise_for_status()
            data = resp.json()

            # ── Validate schema tối thiểu ─────────────────────────────────
            if "items" not in data or not isinstance(data["items"], list):
                logger.error(
                    "[T0d] Gist JSON thiếu field 'items' hoặc không phải list. "
                    "Kiểm tra lại schema genz_hot_news.json."
                )
                return []

            # ── Cảnh báo nếu data cũ hơn CACHE_MAX_AGE_HOURS ─────────────
            updated_at = data.get("updated_at", "")
            if updated_at:
                try:
                    dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    age_hours = (
                        datetime.now(timezone.utc) - dt
                    ).total_seconds() / 3600
                    if age_hours > CACHE_MAX_AGE_HOURS:
                        logger.warning(
                            f"[T0d] Gist TikTok cũ {age_hours:.1f}h "
                            f"(ngưỡng {CACHE_MAX_AGE_HOURS}h). "
                            f"Repo phụ có thể đang gặp sự cố."
                        )
                except ValueError:
                    pass

            raw_items = data["items"]
            logger.info(
                f"[T0d] Gist fetch OK: {len(raw_items)} items "
                f"(updated_at={updated_at}, source={data.get('source','?')})"
            )

            # ── Convert sang format chung ─────────────────────────────────
            items = []
            for item in raw_items:
                if not item.get("title"):
                    continue
                items.append({
                    "type":     "tiktok",
                    "title":    item.get("title", ""),
                    "summary":  item.get("raw_text", ""),
                    "category": item.get("category"),      # "finance", "scandal"...
                    "emotion":  item.get("emotion"),        # "shock", "anger"...
                    "views":    int(item.get("views", 0)),
                    "hashtags": item.get("hashtags", []),
                })

            # ── Cache vào MongoDB PERMANENT ───────────────────────────────
            self._save_trend_cache(raw_items, data.get("updated_at", ""))
            return items

        except requests.exceptions.Timeout:
            logger.error(
                f"[T0d] Gist fetch TIMEOUT ({GIST_TIMEOUT_SEC}s). "
                f"Fallback MongoDB cache."
            )
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"[T0d] Gist fetch lỗi: {e}. Fallback MongoDB cache.")
            return []
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"[T0d] Gist JSON parse lỗi: {e}.")
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # MONGODB CACHE — chimera_permanent.trend_cache
    # ═══════════════════════════════════════════════════════════════════════════

    def _save_trend_cache(self, raw_items: List[Dict], updated_at: str):
        """Lưu raw items vào MongoDB PERMANENT.trend_cache.

        Collection: chimera_permanent.trend_cache
        Document:   {"_id": "latest"}  — upsert, 1 document duy nhất.
        """
        try:
            self.db.permanent.trend_cache.update_one(
                {"_id": "latest"},
                {
                    "$set": {
                        "_id":           "latest",
                        "fetched_at":    datetime.now(timezone.utc).isoformat(),
                        "gist_updated_at": updated_at,
                        "source":        "tiktok_gist",
                        "items_count":   len(raw_items),
                        "items":         raw_items,
                    }
                },
                upsert=True,
            )
            logger.debug(
                f"[T0d] Cached {len(raw_items)} trend items → "
                f"permanent.trend_cache"
            )
        except Exception as e:
            logger.error(f"[T0d] Không lưu được trend_cache vào MongoDB: {e}")

    def _load_trend_cache(self) -> List[Dict]:
        """Đọc trend_cache từ MongoDB PERMANENT khi Gist không khả dụng."""
        try:
            doc = self.db.permanent.trend_cache.find_one({"_id": "latest"})
            if not doc:
                return []

            # Cảnh báo nếu cache cũ
            fetched_at = doc.get("fetched_at", "")
            if fetched_at:
                try:
                    dt = datetime.fromisoformat(fetched_at)
                    age_hours = (
                        datetime.now(timezone.utc) - dt
                    ).total_seconds() / 3600
                    logger.warning(
                        f"[T0d] Dùng MongoDB cache cũ {age_hours:.1f}h "
                        f"({doc.get('items_count', 0)} items)"
                    )
                except ValueError:
                    pass

            # Convert sang format chung
            items = []
            for item in doc.get("items", []):
                if not item.get("title"):
                    continue
                items.append({
                    "type":     "tiktok_cached",
                    "title":    item.get("title", ""),
                    "summary":  item.get("raw_text", ""),
                    "category": item.get("category"),
                    "emotion":  item.get("emotion"),
                    "views":    int(item.get("views", 0)),
                    "hashtags": item.get("hashtags", []),
                })
            return items

        except Exception as e:
            logger.error(f"[T0d] Lỗi đọc trend_cache MongoDB: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # CLASSIFICATION (nâng cấp từ V1 — dùng category field khi có)
    # ═══════════════════════════════════════════════════════════════════════════

    def _classify_to_pattern(self, item: Dict) -> BehaviorPattern:
        """Phân loại item thành CHIMERA pattern.

        Ưu tiên:
        1. field 'category' từ Gist (chính xác nhất — do repo phụ gán)
        2. Keyword scan title + summary (fallback cho RSS)
        """
        source_type = item.get("type", "unknown")
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        views = item.get("views", 0)

        # ── Bước 1: Dùng category field nếu có (TikTok items) ────────────────
        category = item.get("category")
        if category and category in CATEGORY_TO_PATTERN:
            pattern_id = CATEGORY_TO_PATTERN[category]
            base_strength = self._views_to_intensity(views)
            emotion_boost = EMOTION_INTENSITY_BOOST.get(
                item.get("emotion", "neutral"), 0
            )
            strength = min(100, base_strength + emotion_boost)
            return BehaviorPattern(
                pattern_id=pattern_id,
                strength=strength,
                source_type=source_type,
                raw_sample=text[:200],
            )

        # ── Bước 2: Keyword scan (RSS / category không có) ───────────────────
        keyword_map = {
            "fear_of_replacement": [
                "thay thế", "replace", "ai ", "robot", "mất việc",
                "tự động hóa", "chatgpt", "outsource",
            ],
            "hidden_truth_exposed": [
                "lộ bí mật", "phát hiện", "scandal", "bị khui",
                "bóc phốt", "sự thật", "vạch trần",
            ],
            "economic_collapse": [
                "sập", "khủng hoảng", "lạm phát", "thất nghiệp",
                "vỡ nợ", "phá sản", "tín dụng đen", "bất động sản",
            ],
            "authority_distrust": [
                "tẩy chay", "biểu tình", "nghi ngờ", "mất niềm tin",
                "tố cáo", "chống lại", "tiêu cực",
            ],
            "power_vacuum": [
                "từ chức", "bỏ trốn", "mất tích", "sếp chạy",
                "ghế trống", "không ai lãnh đạo",
            ],
            "social_isolation": [
                "cô đơn", "tẩy chay", "bị loại", "lẻ loi",
                "không ai quan tâm", "cô lập",
            ],
            "moral_dilemma": [
                "khó xử", "lưỡng nan", "phản bội", "tố giác",
                "đạo đức", "lương tâm",
            ],
            "lost_legacy": [
                "mất mát", "hoài niệm", "truyền thống", "ngày xưa",
                "phá bỏ", "biến mất",
            ],
            "technology_backfire": [
                "deepfake", "lừa đảo app", "hack", "rò rỉ dữ liệu",
                "bị lừa online", "scam",
            ],
        }

        best_pattern = "neutral"
        best_strength = 20

        for pattern_id, keywords in keyword_map.items():
            matches = [kw for kw in keywords if kw in text]
            if matches:
                strength = min(100, len(matches) * 20 + 20)
                if strength > best_strength:
                    best_pattern = pattern_id
                    best_strength = strength

        return BehaviorPattern(
            pattern_id=best_pattern,
            strength=best_strength,
            source_type=source_type,
            raw_sample=text[:200],
        )

    @staticmethod
    def _views_to_intensity(views: int) -> int:
        """Chuyển số lượt xem TikTok → intensity 0-100."""
        if views >= 10_000_000:  return 95
        if views >= 5_000_000:   return 85
        if views >= 1_000_000:   return 70
        if views >= 500_000:     return 55
        if views >= 100_000:     return 40
        return 25

    # ═══════════════════════════════════════════════════════════════════════════
    # TRANSLATION & GROUPING (giữ nguyên từ V1)
    # ═══════════════════════════════════════════════════════════════════════════

    def _translate_to_pressures(
        self, patterns: List[BehaviorPattern]
    ) -> List[WorldPressure]:
        """Map pattern → chimera_translation theo genre (Va M-10)."""
        pressures = []
        for i, p in enumerate(patterns):
            if p.pattern_id == "neutral":
                continue
            # Dùng genre của world_info, fallback về pattern_id thô
            translation = (
                self.pattern_map
                .get(p.pattern_id, {})
                .get(self.genre)
                or self.pattern_map
                .get(p.pattern_id, {})
                .get("sci_fi", p.pattern_id)  # secondary fallback
            )
            pressures.append(WorldPressure(
                pressure_id=f"P_{i:03d}",
                type=p.pattern_id,
                intensity=p.strength,
                affected_factions=["guild", "church"],
                chimera_translation=translation,
            ))
        return pressures

    def _group_by_type(self, pressures: List[WorldPressure]) -> RDEOutput:
        """Gom nhóm pressures vào 5 bucket của RDEOutput."""
        result = {
            "social_pressure":     [],
            "technology_pressure": [],
            "culture_pressure":    [],
            "economy_pressure":    [],
            "emotion_pressure":    [],
        }
        for p in pressures:
            bucket = PATTERN_TO_BUCKET.get(p.type, "culture_pressure")
            result[bucket].append(p)

        # Log summary
        non_empty = {k: len(v) for k, v in result.items() if v}
        logger.info(f"[T0d] RDE output: {non_empty}")
        return RDEOutput(**result)
