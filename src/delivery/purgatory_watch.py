"""Vá #5 — Purgatory TTL + auto-escalation.

CLI:
    python -m src.delivery.purgatory_watch

Workflow purgatory_watch.yml gọi 30 phút/lần.
"""
from __future__ import annotations
import sys

from ..config import settings
from ..storage import mongo
from ..utils import get_logger

log = get_logger("purgatory_watch")


def _notify_urgent(episode_id: str, hours_left: int) -> None:
    try:
        import requests
        url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
        requests.post(url, data={
            "chat_id": settings.chat_id,
            "text": f"⚠️ TẬP {episode_id} SẮP HẾT HẠN DUYỆT (~{hours_left}h còn lại).",
        }, timeout=8)
    except Exception as e:
        log.warning("notify_urgent fail: %s", e)


def _notify_auto(episode_id: str, version: int) -> None:
    try:
        import requests
        url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
        requests.post(url, data={
            "chat_id": settings.chat_id,
            "text": f"🤖 AUTO-DUYỆT tập {episode_id} → bản v{version} (ai_score cao nhất).",
        }, timeout=8)
    except Exception as e:
        log.warning("notify_auto fail: %s", e)


def run() -> int:
    # Cảnh báo "sắp hết hạn"
    warning_hrs = settings.purgatory_warning_hours_before
    for doc in mongo.find_expiring_purgatory(within_hours=warning_hrs):
        _notify_urgent(doc["episode_id"], warning_hrs)

    # Auto-escalate những bản đã hết hạn
    expired_by_ep = {}
    for doc in mongo.find_expired_purgatory():
        expired_by_ep.setdefault(doc["episode_id"], []).append(doc)

    for episode_id, variants in expired_by_ep.items():
        best = max(variants, key=lambda v: v.get("ai_score") or v.get("drama_score") or 0)
        try:
            mongo.commit_canon(
                episode_id=episode_id,
                version=best.get("version", 1),
                script=best.get("script", {}),
                character_state=best.get("character_state", []),
            )
            mongo.mark_purgatory_reviewed(episode_id)
            _notify_auto(episode_id, best.get("version", 1))
            log.info("Auto-promoted %s v%s", episode_id, best.get("version"))
        except Exception as e:
            log.error("auto-promote %s fail: %s", episode_id, e)

    return 0


if __name__ == "__main__":
    sys.exit(run())