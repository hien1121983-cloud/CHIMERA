"""T5 — Analytics Feedback (chạy 24h sau publish).

Hiện cào view/like từ chính Telegram (forward count). Có thể mở rộng TikTok/YT
nếu có token. Ghi `view_count`, `like_count` vào canon doc tương ứng.
"""
from __future__ import annotations
import datetime as dt
from typing import Dict, List

from ..utils import get_logger

log = get_logger("analytics_feedback")


def fetch_telegram_metrics(message_id: int | None = None) -> Dict[str, int]:
    """Stub — Telegram Bot API không expose view count cho private chat.
    Trả 0/0; có thể plug-in MTProto sau."""
    return {"view_count": 0, "like_count": 0}


def feedback_recent(limit: int = 10) -> List[Dict]:
    try:
        from ..storage import mongo
    except Exception as e:
        log.error("mongo unavailable: %s", e)
        return []
    docs = mongo.list_canon_recent(limit)
    out: List[Dict] = []
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=24)
    for d in docs:
        committed = d.get("committed_at")
        if not committed or committed > cutoff:
            continue
        m = fetch_telegram_metrics(d.get("telegram_message_id"))
        try:
            mongo.db_history()["canon"].update_one(
                {"episode_id": d["episode_id"]},
                {"$set": {"view_count": m["view_count"],
                          "like_count": m["like_count"],
                          "analytics_at": dt.datetime.utcnow()}},
            )
        except Exception as e:
            log.warning("write analytics fail: %s", e)
        out.append({"episode_id": d["episode_id"], **m})
    log.info("analytics_feedback updated=%d", len(out))
    return out


if __name__ == "__main__":
    feedback_recent()