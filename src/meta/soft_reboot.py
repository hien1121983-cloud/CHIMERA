"""Cơ chế #2 — Soft Reboot Engine.

Kích hoạt khi: `episode_id % 100 == 0` HOẶC entropy recommend SOFT_REBOOT.
Quy trình:
  1. Roll 1 reboot_event từ data/reboot_events.json
  2. Extract `core_soul` cho mỗi character alive -> Mongo `character_souls`
  3. Roll new_world
  4. Update current_state: reboot_active=True, reboot_event, new_world
  5. Notify Telegram

T1 (alchemist) sẽ đọc `reboot_active` và dùng `character_souls` làm seed.
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings
from ..utils import get_logger

log = get_logger("meta.reboot")

ROOT = Path(__file__).resolve().parent.parent.parent
REBOOT_EVENTS_FILE = ROOT / "data" / "reboot_events.json"
CONTEXTS_FILE = ROOT / "data" / "contexts.json"

SOUL_KEYS = ("root_traumas", "core_belief", "key_relationships", "unresolved_secrets")


def should_reboot(episode_id: int, entropy_action: Optional[str] = None) -> bool:
    if not settings.enable_soft_reboot:
        return False
    if entropy_action == "SOFT_REBOOT":
        return True
    interval = settings.soft_reboot_interval_episodes
    return interval > 0 and episode_id > 0 and (episode_id % interval == 0)


def roll_reboot_event(rng: Optional[random.Random] = None) -> Dict:
    rng = rng or random.Random()
    try:
        data = json.loads(REBOOT_EVENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = [{"name": "Vạn giới sụp đổ", "description": "Fallback event."}]
    return rng.choice(data)


def extract_core_soul(entity: Dict) -> Dict:
    """Bóc tách phần "linh hồn" của 1 entity để mang qua reboot."""
    return {
        "entity_id": entity.get("id") or entity.get("entity_id") or entity.get("name"),
        "full_name": entity.get("name") or entity.get("full_name", ""),
        "core_soul": {k: entity.get(k) for k in SOUL_KEYS if k in entity},
        "plot_armor_tokens": entity.get("plot_armor_tokens", 3),
        "visual_anchor": entity.get("visual_anchor", ""),
    }


def roll_new_world(exclude: Optional[List[str]] = None,
                   rng: Optional[random.Random] = None) -> str:
    rng = rng or random.Random()
    try:
        worlds = json.loads(CONTEXTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        worlds = ["modern_vn", "xianxia", "cyberpunk"]
    pool = [w for w in worlds if w not in (exclude or [])] or worlds
    return rng.choice(pool)


def execute(episode_id: int, alive_entities: List[Dict],
            current_world: str = "") -> Dict:
    """Chạy reboot. Trả về dict tóm tắt; KHÔNG raise nếu Mongo/Telegram fail."""
    if not settings.enable_soft_reboot:
        log.info("[META] soft_reboot disabled by flag — skip.")
        return {"executed": False, "reason": "flag_off"}

    event = roll_reboot_event()
    souls = [extract_core_soul(e) for e in alive_entities]
    new_world = roll_new_world(exclude=[current_world] if current_world else None)

    try:
        from ..storage import mongo
        for s in souls:
            if s.get("entity_id"):
                mongo.save_character_soul(s)
        # Persist trạng thái reboot vào current_state (theo doc id cố định)
        mongo.db_inputs()["current_state"].update_one(
            {"character_id": "__reboot_marker__"},
            {"$set": {
                "character_id": "__reboot_marker__",
                "reboot_active": True,
                "reboot_event": event,
                "new_world": new_world,
                "reboot_episode": episode_id,
            }},
            upsert=True,
        )
    except Exception as e:
        log.warning("[META] reboot persist fail: %s", e)

    summary = {
        "executed": True,
        "episode_id": episode_id,
        "event": event,
        "new_world": new_world,
        "souls_saved": len(souls),
    }
    log.warning("[META] SOFT REBOOT ep=%s event=%s -> world=%s souls=%d",
                episode_id, event.get("name"), new_world, len(souls))

    try:
        from ..delivery import telegram_bot
        telegram_bot.status_message(
            f"♻️ SOFT REBOOT @ ep {episode_id}\n"
            f"Event: {event.get('name')}\n"
            f"New world: {new_world}\n"
            f"Souls preserved: {len(souls)}"
        )
    except Exception:
        pass

    return summary


def consume_reboot_marker() -> Optional[Dict]:
    """Đọc & xoá marker reboot (T1 gọi sau khi đã apply)."""
    try:
        from ..storage import mongo
        doc = mongo.db_inputs()["current_state"].find_one_and_delete(
            {"character_id": "__reboot_marker__"}
        )
        return doc
    except Exception:
        return None