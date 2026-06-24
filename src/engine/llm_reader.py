"""LLM Reader — sinh kịch bản theo cơ chế "1 key cho 1 phân cảnh".

V4.0 PHASE-1 FIX
================
Scene 1 (THE HOOK) sẽ KHÔNG sinh ảnh tự động nữa. Thay vào đó LLM phải xuất
một trường ``cinematic_video_prompt`` (TIẾNG ANH chuẩn, ~80–120 từ) để người
dùng copy sang nền tảng video tự sinh thủ công (Runway / Pika / Kling / Sora…).
Các Scene 2..N giữ nguyên schema (xuất ``image_prompt``).

Quy trình:
  1. STAGE-OUTLINE: outline thô cả tập.
  2. STAGE-SCENE  : mỗi scene 1 key Gemini riêng.
       - Scene 1   -> cinematic_video_prompt (KHÔNG image_prompt)
       - Scene 2..N -> image_prompt
"""
from __future__ import annotations
import json
from typing import Dict, List
from jsonschema import validate, ValidationError
from ..config import settings
from ..utils import get_logger
from . import gemini_pool

log = get_logger("llm_reader")

# ---------- Schemas ----------

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "episode_title": {"type": "string"},
        "emotion_tag": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene", "actor", "beat", "tags"],
                "properties": {
                    "scene": {"type": "integer"},
                    "actor": {"type": "string"},
                    "beat": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "no_ad": {"type": "boolean"},
                    "is_glitch": {"type": "boolean"},
                },
            },
        },
    },
    "required": ["episode_title", "emotion_tag", "scenes"],
}

# Scene 1 — Hook (KHÔNG còn image_prompt, BẮT BUỘC cinematic_video_prompt)
SCENE1_SCHEMA = {
    "type": "object",
    "required": ["scene", "dialogue", "cinematic_video_prompt", "sfx_tag"],
    "properties": {
        "scene": {"type": "integer", "enum": [1]},
        "actor": {"type": "string"},
        "dialogue": {"type": "string"},
        "cinematic_video_prompt": {"type": "string", "minLength": 40},
        "sfx_tag": {"type": "string"},
        "comic_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "no_ad": {"type": "boolean"},
    },
    # Đặc biệt: KHÔNG cho phép image_prompt ở Scene 1
    "not": {"required": ["image_prompt"]},
}

# Scene >= 2 — vẫn dùng image_prompt như cũ
SCENE_SCHEMA = {
    "type": "object",
    "required": ["scene", "dialogue", "image_prompt", "sfx_tag"],
    "properties": {
        "scene": {"type": "integer"},
        "actor": {"type": "string"},
        "dialogue": {"type": "string"},
        "image_prompt": {"type": "string"},
        "sfx_tag": {"type": "string"},
        "comic_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "no_ad": {"type": "boolean"},
        "is_glitch": {"type": "boolean"},
    },
}


# ---------- Groq fallback (outline only) ----------

def _groq_outline(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": prompt + "\n\nBẮT BUỘC trả về JSON hợp lệ."}],
        max_tokens=settings.max_output_tokens,
        temperature=0.9,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


# ---------- Stage 1: outline cả tập ----------

def stage1_outline(alchemy_prompt: str, scenes: int, budget) -> dict:
    extra = (
        f"\n\nTRẢ VỀ JSON đúng schema sau, đúng {scenes} phân cảnh:\n"
        + json.dumps(OUTLINE_SCHEMA)
        + "\n\nLƯU Ý: nếu có phân cảnh 'xuyên không / glitch thời gian / "
        "chuyển bối cảnh đột ngột', đánh dấu is_glitch=true cho scene NGAY TRƯỚC "
        "điểm chuyển. Ví dụ điển hình: scene 8 trong tập 15 phân cảnh."
    )
    last_err = ""
    alive = gemini_pool.ensure_pool()
    for attempt in range(settings.retry_budget["json_error"] + 1):
        prompt = alchemy_prompt + extra + (
            f"\n\nLỖI TRƯỚC: {last_err}\nSửa lại." if last_err else ""
        )
        try:
            if alive:
                key = alive[attempt % len(alive)]
                data = gemini_pool.generate_json(key, prompt)
            elif settings.groq_api_key:
                data = json.loads(_groq_outline(prompt))
            else:
                raise RuntimeError("Không có LLM khả dụng cho outline.")
            validate(data, OUTLINE_SCHEMA)
            return data
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)[:200]
            log.warning("Stage1 JSON error: %s", last_err)
            budget.consume("json_error")
        except Exception as e:
            log.warning("Stage1 LLM error: %s", e)
            budget.consume("json_error")
    raise RuntimeError("Stage1 outline thất bại sau khi hết budget JSON.")


# ---------- Stage 2: từng scene ----------

def _scene1_prompt(outline_meta: dict, scene_skel: dict) -> str:
    """Prompt riêng cho Scene 1 — HOOK do người dùng tự dựng video."""
    extras = ""
    if settings.enable_comic_sfx:
        extras += (
            "\n- comic_text (TÙY CHỌN): nếu cảnh có sát thương tâm lý / bất ngờ lớn, "
            "điền 1-3 từ ALL CAPS (VD: 'BANG!', 'PHẢN BỘI!!'). Không cần thì bỏ trống."
        )
    return (
        "Bạn là biên kịch + đạo diễn hình ảnh cho video dọc 9:16.\n"
        f"Bối cảnh tập phim:\n- Tiêu đề: {outline_meta.get('episode_title')}\n"
        f"- Cảm xúc chủ đạo: {outline_meta.get('emotion_tag')}\n\n"
        f"Phân cảnh được giao (Scene 1 — THE HOOK):\n"
        f"{json.dumps(scene_skel, ensure_ascii=False)}\n\n"
        "Đây là phân cảnh đặc biệt: KHÔNG sinh image_prompt. Thay vào đó, hãy viết:\n"
        "- dialogue: lời thoại TIẾNG VIỆT, ≤ 280 ký tự, gây tò mò trong 3 giây đầu.\n"
        "- cinematic_video_prompt: PROMPT TIẾNG ANH chuẩn quốc tế (~80–120 từ) để người dùng "
        "copy sang Runway/Pika/Kling/Sora dựng 1 clip 6–10 giây dọc 9:16. "
        "BẮT BUỘC mô tả đầy đủ: subject + action, camera (angle / movement / lens), "
        "lighting (warm/cold/backlit), environment, mood, style (cinematic, 35mm film, "
        "shallow depth of field, anamorphic, etc.). KHÔNG dùng tiếng Việt trong trường này.\n"
        "- sfx_tag: 1 từ trong {tense, dramatic, sad, twist, calm, hopeful, dark}.\n"
        "- Giữ nguyên scene=1 và actor."
        + extras + "\n\n"
        "TUYỆT ĐỐI KHÔNG xuất khoá 'image_prompt'.\n"
        f"TRẢ VỀ JSON theo schema:\n{json.dumps(SCENE1_SCHEMA)}"
    )


def _scene_prompt(outline_meta: dict, scene_skel: dict) -> str:
    extras = ""
    if settings.enable_comic_sfx:
        extras += (
            "\n- comic_text (TÙY CHỌN): nếu cảnh có sát thương tâm lý / bất ngờ lớn, "
            "điền 1-3 từ ALL CAPS. Không cần thì bỏ trống."
        )
    return (
        "Bạn là biên kịch truyện tranh có thoại. Bạn được giao DUY NHẤT 1 phân cảnh.\n"
        f"Bối cảnh tập phim:\n- Tiêu đề: {outline_meta.get('episode_title')}\n"
        f"- Cảm xúc chủ đạo: {outline_meta.get('emotion_tag')}\n\n"
        f"Phân cảnh được giao:\n{json.dumps(scene_skel, ensure_ascii=False)}\n\n"
        "Hãy viết:\n"
        "- dialogue: lời thoại TIẾNG VIỆT, ≤ 280 ký tự, đúng tính cách nhân vật.\n"
        "- image_prompt: mô tả ảnh BẰNG TIẾNG ANH, chi tiết camera/lighting, style 'cinematic comic'.\n"
        "- sfx_tag: 1 từ trong {tense, dramatic, sad, twist, calm, hopeful, dark}.\n"
        "- Giữ nguyên scene number và actor."
        + extras + "\n\n"
        f"TRẢ VỀ JSON theo schema:\n{json.dumps(SCENE_SCHEMA)}"
    )


def stage2_scene(outline_meta: dict, scene_skel: dict, scene_index: int, budget) -> dict:
    """Sinh 1 scene. Scene 1 dùng SCENE1_SCHEMA, các scene khác dùng SCENE_SCHEMA."""
    is_hook = scene_index == 0
    prompt = _scene1_prompt(outline_meta, scene_skel) if is_hook \
        else _scene_prompt(outline_meta, scene_skel)
    schema = SCENE1_SCHEMA if is_hook else SCENE_SCHEMA

    alive = gemini_pool.ensure_pool()
    if not alive:
        raise RuntimeError("Không còn key Gemini sống.")
    last_err = ""
    for offset in range(len(alive)):
        key = alive[(scene_index + offset) % len(alive)]
        p = prompt + (f"\n\nLỖI TRƯỚC: {last_err}\nSửa lại." if last_err else "")
        try:
            data = gemini_pool.generate_json(key, p, max_tokens=2048)
            data.setdefault("scene", scene_skel.get("scene", scene_index + 1))
            data.setdefault("actor", scene_skel.get("actor", ""))
            data.setdefault("tags", scene_skel.get("tags", []))
            if scene_skel.get("no_ad"):
                data["no_ad"] = True
            if scene_skel.get("is_glitch"):
                data["is_glitch"] = True
            # Quy tắc nghiêm: Scene 1 phải KHÔNG có image_prompt
            if is_hook and "image_prompt" in data:
                data.pop("image_prompt", None)
            validate(data, schema)
            log.info("scene %d OK (key …%s)%s",
                     data["scene"], key[-6:],
                     " [HOOK - human video]" if is_hook else "")
            return data
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)[:200]
            log.warning("scene %d JSON error (key …%s): %s",
                        scene_skel.get("scene"), key[-6:], last_err)
            try: budget.consume("json_error")
            except Exception: pass
        except Exception as e:
            log.warning("scene %d LLM error (key …%s): %s",
                        scene_skel.get("scene"), key[-6:], e)
            gemini_pool.mark_dead(key)
            try: budget.consume("content_filter")
            except Exception: pass
    raise RuntimeError(f"Scene {scene_skel.get('scene')} thất bại trên toàn bộ key.")


def generate_script(alchemy_prompt: str, scenes: int, budget) -> dict:
    outline = stage1_outline(alchemy_prompt, scenes, budget)
    meta = {
        "episode_title": outline["episode_title"],
        "emotion_tag": outline["emotion_tag"],
    }
    enriched: List[Dict] = []
    for i, skel in enumerate(outline["scenes"]):
        enriched.append(stage2_scene(meta, skel, i, budget))
    return {
        "episode_title": meta["episode_title"],
        "emotion_tag": meta["emotion_tag"],
        "scenes": enriched,
    }


def extract_hook_video_prompt(script: dict) -> str:
    """Trích cinematic_video_prompt của Scene 1 (để gửi cho user qua Telegram)."""
    scenes = script.get("scenes") or []
    if not scenes:
        return ""
    s1 = scenes[0]
    return (s1.get("cinematic_video_prompt") or "").strip()
