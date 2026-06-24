"""Cơ chế #4 — Audience Co-creation.

Mỗi 20 tập sinh poll Telegram (3 world chưa dùng 50 tập qua).
Webhook ghi winner vào `current_state.audience_chosen_world`.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import random
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings
from ..utils import get_logger

log = get_logger("meta.co_creation")

ROOT = Path(__file__).resolve().parent.parent.parent
CONTEXTS_FILE = ROOT / "data" / "contexts.json"
POLL_INTERVAL_EPISODES = 20
POLL_TTL_HOURS = 48


def _all_worlds() -> List[str]:
    try:
        return json.loads(CONTEXTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ["modern_vn", "xianxia", "cyberpunk", "isekai", "noir"]


def pick_unused_worlds(recent_worlds: List[str], k: int = 3,
                       rng: Optional[random.Random] = None) -> List[str]:
    rng = rng or random.Random()
    pool = [w for w in _all_worlds() if w not in set(recent_worlds)]
    if len(pool) < k:
        pool = list(set(_all_worlds()))
    rng.shuffle(pool)
    return pool[:k]


def _poll_id(question: str) -> str:
    h = hashlib.sha256(f"{question}|{dt.datetime.utcnow().date()}".encode()).hexdigest()[:10]
    return f"poll_{h}"


def launch_world_poll(episode_id: int, recent_worlds: List[str]) -> Optional[Dict]:
    if not settings.enable_co_creation:
        log.info("[META] co_creation disabled — skip launch")
        return None
    options = pick_unused_worlds(recent_worlds)
    question = f"🌌 Tập {episode_id + 10}: Bối cảnh tiếp theo?"
    poll_id = _poll_id(question)
    expires_at = dt.datetime.utcnow() + dt.timedelta(hours=POLL_TTL_HOURS)

    try:
        from ..storage import mongo
        mongo.db_scripts()["active_votes"].update_one(
            {"poll_id": poll_id},
            {"$set": {
                "poll_id": poll_id,
                "question": question,
                "options": options,
                "episode_target": episode_id + 10,
                "created_at": dt.datetime.utcnow(),
                "expires_at": expires_at,
                "closed": False,
            }},
            upsert=True,
        )
    except Exception as e:
        log.warning("save active_vote fail: %s", e)

    try:
        from ..delivery import telegram_bot
        from ..config import settings as _s
        import requests
        url = telegram_bot.API.format(token=_s.bot_token, method="sendPoll")
        requests.post(url, timeout=30, data={
            "chat_id": _s.chat_id, "question": question,
            "options": json.dumps(options, ensure_ascii=False),
            "is_anonymous": "false",
        })
    except Exception as e:
        log.warning("sendPoll fail: %s", e)

    log.info("[META] launched poll %s options=%s", poll_id, options)
    return {"poll_id": poll_id, "options": options, "episode_target": episode_id + 10}


def record_winner(poll_id: str, winning_option: str, episode_target: int) -> None:
    try:
        from ..storage import mongo
        mongo.db_scripts()["active_votes"].update_one(
            {"poll_id": poll_id},
            {"$set": {"closed": True, "winner": winning_option,
                      "closed_at": dt.datetime.utcnow()}},
        )
        mongo.db_inputs()["current_state"].update_one(
            {"character_id": "__audience_choice__"},
            {"$set": {
                "character_id": "__audience_choice__",
                "audience_chosen_world": winning_option,
                "forced_at_episode": episode_target,
            }},
            upsert=True,
        )
    except Exception as e:
        log.warning("record_winner fail: %s", e)