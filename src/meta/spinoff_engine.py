"""Cơ chế #3 — Spin-off Engine.

Mỗi 30 tập, phân tích nhân vật hot (mentions × positive_ratio).
Spawn 1–3 spin-off (mỗi cái 5 tập) vào collection `spinoffs`.
Workflow `spinoff_run.yml` đọc và chạy riêng.
"""
from __future__ import annotations
import datetime as dt
import hashlib
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..utils import get_logger

log = get_logger("meta.spinoff")

SPINOFF_EPISODES = 5


def score_character(mentions: int, positive_ratio: float) -> float:
    return float(mentions) * max(0.0, min(1.0, positive_ratio))


def analyze_popularity(canon_window: List[Dict],
                       comments_by_episode: Optional[Dict[str, List[Dict]]] = None
                       ) -> List[Tuple[str, float]]:
    """Trả [(character_name, score)] sort desc."""
    mention_counter: Dict[str, int] = {}
    sentiment_pos: Dict[str, int] = {}
    sentiment_total: Dict[str, int] = {}

    for doc in canon_window:
        ep = doc.get("episode_id")
        for name in (doc.get("script", {}).get("character_mentions") or []):
            mention_counter[name] = mention_counter.get(name, 0) + 1
        if comments_by_episode and ep in comments_by_episode:
            for c in comments_by_episode[ep]:
                for name, sent in (c.get("mentions") or {}).items():
                    sentiment_total[name] = sentiment_total.get(name, 0) + 1
                    if sent > 0:
                        sentiment_pos[name] = sentiment_pos.get(name, 0) + 1

    out: List[Tuple[str, float]] = []
    for name, m in mention_counter.items():
        pos = sentiment_pos.get(name, 0)
        tot = sentiment_total.get(name, 0) or 1
        out.append((name, score_character(m, pos / tot)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _spinoff_id(name: str) -> str:
    h = hashlib.sha256(f"{name}|{dt.date.today()}".encode()).hexdigest()[:10]
    return f"spin_{h}"


def spawn_spinoff(protagonist: str, archetype_pool: Optional[List[str]] = None) -> Dict:
    spinoff = {
        "spinoff_id": _spinoff_id(protagonist),
        "protagonist": protagonist,
        "total_episodes": SPINOFF_EPISODES,
        "completed_episodes": 0,
        "status": "pending",
        "archetype_pool": archetype_pool or [],
        "created_at": dt.datetime.utcnow(),
    }
    try:
        from ..storage import mongo
        mongo.insert_spinoff(spinoff)
    except Exception as e:
        log.warning("insert_spinoff fail: %s", e)
    log.info("[META] Spin-off spawned: %s (%s)", spinoff["spinoff_id"], protagonist)
    return spinoff


def maybe_spawn_top_k(k: int = 1) -> List[Dict]:
    if not settings.enable_spinoff:
        return []
    try:
        from ..storage import mongo
        recent = mongo.list_canon_recent(30)
    except Exception as e:
        log.warning("spinoff read canon fail: %s", e)
        return []
    ranking = analyze_popularity(recent)
    return [spawn_spinoff(name) for name, _ in ranking[:k]]