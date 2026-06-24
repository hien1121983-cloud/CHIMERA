"""Cơ chế #5 — Plot Armor.

Mỗi main character có `plot_armor_tokens` (mặc định 3).
Sau T2.3 (đã có skeleton), trước T3:
  - Đoán nguy cơ "chết" trong skeleton bằng regex.
  - Còn token: inject macguffin (rescue) -> giảm token.
  - Hết token: ALLOW_DEATH (đánh dấu drama spike).
"""
from __future__ import annotations
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..utils import get_logger

log = get_logger("meta.armor")

ROOT = Path(__file__).resolve().parent.parent.parent
MACGUFFIN_FILE = ROOT / "data" / "macguffin_events.json"

DEATH_PATTERNS = re.compile(
    r"\b(chết|tử vong|hy sinh|tử nạn|tự sát|tan biến|diệt vong|qua đời|"
    r"bị giết|bỏ mạng)\b",
    re.IGNORECASE,
)


def _skeleton_text(skeleton) -> str:
    if skeleton is None:
        return ""
    if isinstance(skeleton, str):
        return skeleton
    if isinstance(skeleton, dict):
        return json.dumps(skeleton, ensure_ascii=False)
    if isinstance(skeleton, list):
        return " ".join(_skeleton_text(x) for x in skeleton)
    return str(skeleton)


def predict_death_in_skeleton(skeleton, character_name: str) -> float:
    """0..1: xác suất nhân vật bị 'kill' trong skeleton này."""
    if not character_name:
        return 0.0
    text = _skeleton_text(skeleton).lower()
    if character_name.lower() not in text:
        return 0.0
    hits = len(DEATH_PATTERNS.findall(text))
    if hits == 0:
        return 0.0
    # heuristic: 1 hit ~ 0.55, 2 ~ 0.8, >=3 ~ 0.95
    return min(0.95, 0.4 + 0.25 * hits)


def _pick_rescue_macguffin(rng: random.Random) -> Optional[Dict]:
    try:
        pool = json.loads(MACGUFFIN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not pool:
        return None
    rescue = [m for m in pool if str(m.get("type", "")).lower() in ("rescue", "save")]
    chosen = rng.choice(rescue) if rescue else rng.choice(pool)
    return chosen


def evaluate(skeleton, characters: List[Dict],
             rng: Optional[random.Random] = None) -> Dict:
    """Trả `{decisions: [{character, risk, action, macguffin?, tokens_left}]}`."""
    if not settings.enable_plot_armor:
        return {"decisions": [], "skipped": True}
    rng = rng or random.Random()
    decisions: List[Dict] = []
    for ch in characters:
        name = ch.get("name") or ch.get("full_name") or ""
        tokens = int(ch.get("plot_armor_tokens", 3))
        risk = predict_death_in_skeleton(skeleton, name)
        if risk < 0.5:
            continue
        if tokens > 0:
            mg = _pick_rescue_macguffin(rng)
            ch["plot_armor_tokens"] = tokens - 1
            decisions.append({
                "character": name, "risk": round(risk, 3),
                "action": "INJECT_MACGUFFIN", "macguffin": mg,
                "tokens_left": ch["plot_armor_tokens"],
            })
        else:
            decisions.append({
                "character": name, "risk": round(risk, 3),
                "action": "ALLOW_DEATH", "tokens_left": 0,
                "drama_spike": True,
            })
    if decisions:
        log.warning("[META] PlotArmor decisions: %s", decisions)
    return {"decisions": decisions, "skipped": False}


def refresh_tokens(characters: List[Dict], floor: int = 3) -> None:
    """Đảm bảo mọi character có ít nhất `floor` token sau soft reboot."""
    for ch in characters:
        cur = int(ch.get("plot_armor_tokens", 0))
        if cur < floor:
            ch["plot_armor_tokens"] = floor