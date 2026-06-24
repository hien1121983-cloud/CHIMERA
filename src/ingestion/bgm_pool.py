"""BGM pool — đọc bgm_index.json, chọn file mp3 theo thẻ cảm xúc."""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import Dict, List


def load_index(path: str | Path = "data/bgm/bgm_index.json") -> Dict[str, List[str]]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def pick_bgm(emotion_tag: str, index: Dict[str, List[str]] | None = None,
             base: str | Path = "data/bgm") -> str | None:
    """Trả về path tới file mp3 phù hợp. None nếu pool rỗng."""
    index = index or load_index()
    candidates = index.get(emotion_tag) or index.get("neutral") or []
    if not candidates:
        # fallback: bất kỳ file mp3 nào trong pool
        all_mp3 = list(Path(base).glob("*.mp3"))
        return str(random.choice(all_mp3)) if all_mp3 else None
    chosen = random.choice(candidates)
    full = Path(base) / chosen
    return str(full) if full.exists() else None
