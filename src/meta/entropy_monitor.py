"""Cơ chế #1 — Entropy Monitor.

Đo "độ già" của hệ thống mỗi tập và gợi ý hành động (CONTINUE / INJECT_ANTI_PATTERN /
ACTIVATE_PLOT_ARMOR / SOFT_REBOOT). Ghi log vào collection `entropy_history` (NO1).

Pure-function core (`compute_entropy_from_data`) để dễ test; wrapper
`calculate_entropy(episode_id)` đọc Mongo.
"""
from __future__ import annotations
import math
from collections import Counter
from typing import Dict, List, Optional

from ..config import settings
from ..utils import get_logger

log = get_logger("meta.entropy")

WEIGHTS = {
    "lore_contradiction": 0.25,
    "archetype_repetition": 0.25,
    "character_death_risk": 0.15,
    "trend_relevance_decay": 0.15,
    "audience_fatigue": 0.20,
}

ACTION_CONTINUE = "CONTINUE_NORMAL"
ACTION_ANTI_PATTERN = "INJECT_ANTI_PATTERN"
ACTION_PLOT_ARMOR = "ACTIVATE_PLOT_ARMOR"
ACTION_SOFT_REBOOT = "SOFT_REBOOT"


def _shannon_entropy_norm(items: List[str]) -> float:
    """0..1; cao = đa dạng, thấp = lặp."""
    if not items:
        return 1.0
    c = Counter(items)
    total = sum(c.values())
    h = -sum((n / total) * math.log2(n / total) for n in c.values())
    h_max = math.log2(len(c)) if len(c) > 1 else 1.0
    return h / h_max if h_max > 0 else 1.0


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def compute_entropy_from_data(
    contradictions_in_window: int,
    window_size: int,
    archetype_tags: List[str],
    plot_armor_avg: float,
    drama_trend_delta: float,
    trending_today: List[str],
    trending_at_episode: List[str],
    view_drop_ratio: float,
) -> Dict:
    """Trả `{metrics, total_entropy (0..100), recommended_action}`."""
    # 1. Lore contradiction (0..1) — tỉ lệ mâu thuẫn trong 50 tập gần nhất
    lore = min(1.0, contradictions_in_window / max(1, window_size))
    # 2. Archetype repetition (0..1) — 1 - entropy đa dạng
    arche_rep = 1.0 - _shannon_entropy_norm(archetype_tags)
    # 3. Character death risk — token armor thấp + drama tăng nhanh
    armor_norm = max(0.0, min(1.0, 1.0 - plot_armor_avg / 3.0))
    drama_norm = max(0.0, min(1.0, drama_trend_delta))
    death_risk = 0.6 * armor_norm + 0.4 * drama_norm
    # 4. Trend relevance decay — 1 - jaccard
    trend_decay = 1.0 - _jaccard(trending_today, trending_at_episode)
    # 5. Audience fatigue — view drop %
    fatigue = max(0.0, min(1.0, view_drop_ratio))

    metrics = {
        "lore_contradiction": round(lore, 3),
        "archetype_repetition": round(arche_rep, 3),
        "character_death_risk": round(death_risk, 3),
        "trend_relevance_decay": round(trend_decay, 3),
        "audience_fatigue": round(fatigue, 3),
    }
    total = sum(metrics[k] * WEIGHTS[k] for k in WEIGHTS) * 100.0
    total = round(total, 2)

    if total >= settings.entropy_reboot_threshold:
        action = ACTION_SOFT_REBOOT
    elif arche_rep >= 0.7:
        action = ACTION_ANTI_PATTERN
    elif death_risk >= 0.8:
        action = ACTION_PLOT_ARMOR
    else:
        action = ACTION_CONTINUE

    return {"metrics": metrics, "total_entropy": total, "recommended_action": action}


def _gather_inputs_from_mongo(episode_id: int) -> Dict:
    """Đọc dữ liệu thực để tính entropy. Bao bọc try/except để không crash pipeline."""
    from ..storage import mongo
    out = {
        "contradictions_in_window": 0,
        "window_size": settings.t_checker_history_window,
        "archetype_tags": [],
        "plot_armor_avg": 3.0,
        "drama_trend_delta": 0.0,
        "trending_today": [],
        "trending_at_episode": [],
        "view_drop_ratio": 0.0,
    }
    try:
        recent = mongo.list_canon_recent(settings.t_checker_history_window)
        out["archetype_tags"] = [
            (d.get("script") or {}).get("archetype_tag") or
            (d.get("script") or {}).get("emotion_tag") or "neutral"
            for d in recent
        ]
        scores = [
            float((d.get("script") or {}).get("drama_score") or 0.0) for d in recent
        ]
        if len(scores) >= 6:
            head = sum(scores[:3]) / 3.0
            tail = sum(scores[-3:]) / 3.0
            out["drama_trend_delta"] = max(0.0, head - tail)
        out["trending_today"] = mongo.load_keywords()
        if recent:
            out["trending_at_engineer_episode"] = (recent[-1].get("script") or {}).get(
                "trending", []
            )
            out["trending_at_episode"] = (recent[-1].get("script") or {}).get("trending", [])
    except Exception as e:
        log.warning("entropy gather fail: %s", e)
    return out


def calculate_entropy(episode_id: int) -> Dict:
    data = _gather_inputs_from_mongo(episode_id)
    result = compute_entropy_from_data(**{k: v for k, v in data.items() if not k.startswith("trending_at_engineer")})
    log.info("[META] entropy ep=%s total=%.1f action=%s",
             episode_id, result["total_entropy"], result["recommended_action"])
    try:
        from ..storage import mongo
        mongo.save_entropy(episode_id, result["metrics"], result["recommended_action"])
    except Exception as e:
        log.warning("save_entropy fail: %s", e)
    return result


def latest() -> Optional[Dict]:
    try:
        from ..storage import mongo
        return mongo.latest_entropy()
    except Exception:
        return None