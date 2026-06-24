"""Glitch Curse (Vá #3).

Khi countdown_to_glitch == 0 và xảy ra glitch chuyển world, có xác suất
gắn một "curse" lên character_state. Curse có TTL theo episode.
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import Dict, Optional

from ..utils import get_logger

log = get_logger("glitch_curse")

_ROOT = Path(__file__).resolve().parents[2]
_CURSE_PATH = _ROOT / "data" / "glitch_curses.json"

_CACHE: Optional[Dict] = None


def _load() -> Dict:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_CURSE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Không load được glitch_curses.json: %s", e)
            _CACHE = {"curse_types": {}}
    return _CACHE


def roll_curse(rng: Optional[random.Random] = None) -> Dict:
    """Roll 1 curse ngẫu nhiên. Trả dict {type, remaining_episodes, manifestation, example}."""
    rng = rng or random
    types = _load().get("curse_types", {})
    if not types:
        return {}
    ctype = rng.choice(list(types.keys()))
    cfg = types[ctype]
    lo, hi = cfg.get("duration_episodes", [1, 1])
    examples = cfg.get("examples") or [cfg.get("example", "")]
    return {
        "type": ctype,
        "remaining_episodes": rng.randint(lo, hi),
        "manifestation": cfg.get("manifestation", ""),
        "example": rng.choice([e for e in examples if e]) if examples else "",
    }


def apply_to_state(state: dict, curse: Dict) -> dict:
    if not curse:
        return state
    state = dict(state)
    state["active_curse"] = curse
    return state


def tick_down(curse: Optional[Dict]) -> Optional[Dict]:
    """Giảm 1 tập. Trả None khi curse hết hạn."""
    if not curse:
        return None
    curse = dict(curse)
    curse["remaining_episodes"] = max(0, int(curse.get("remaining_episodes", 0)) - 1)
    if curse["remaining_episodes"] <= 0:
        return None
    return curse