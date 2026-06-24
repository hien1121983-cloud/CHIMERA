"""T3.2 — Storyboard Parser.

Đầu vào: raw JSON từ LLM Director (T3).
Đầu ra: 3 list song song
  - visual_prompts:  [{scene, prompt, seed, primary_character}]
  - audio_prompts:   [{scene, text, voice, is_hook}]
  - bgm_cues:        [{scene, mood, duck_to}]
"""
from __future__ import annotations
from typing import Dict, List

from . import seed_lock
from ..config import settings
from ..utils import get_logger

log = get_logger("storyboard_parser")


def parse(script: dict) -> Dict[str, List[dict]]:
    scenes = script.get("scenes", [])
    visual, audio, bgm = [], [], []

    for i, s in enumerate(scenes):
        idx = i + 1
        primary = s.get("primary_character") or {}
        seed = seed_lock.get_stable_seed(primary) if (settings.enable_seed_lock and primary) else None
        visual.append({
            "scene": idx,
            "prompt": s.get("image_prompt", ""),
            "seed": seed,
            "primary_character": primary.get("entity_id") or primary.get("full_name"),
        })
        audio.append({
            "scene": idx,
            "text": s.get("dialogue", ""),
            "voice": s.get("voice", settings.edge_voice),
            "is_hook": (i == 0) or (i == len(scenes) - 1),
        })
        bgm.append({
            "scene": idx,
            "mood": s.get("emotion") or script.get("emotion_tag", "neutral"),
            "duck_to": settings.bgm_volume_ratio,
        })

    return {"visual_prompts": visual, "audio_prompts": audio, "bgm_cues": bgm}