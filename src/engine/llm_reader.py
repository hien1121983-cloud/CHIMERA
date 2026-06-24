"""LLM Reader — V4.0.

Sinh kịch bản CHI TIẾT từ một SKELETON đã được Showrunner duyệt.

Quy tắc mới so với phiên bản trước:
  1. Scene 1 (THE HOOK)  -> xuất ``cinematic_video_prompt`` (TIẾNG ANH ~80-120 từ).
                            KHÔNG sinh ``image_prompt`` cho Scene 1.
  2. Scene 2..N          -> xuất ``image_prompt`` như cũ.
  3. MỖI scene BẮT BUỘC có ``audio_directive`` chứa `narrator_text` và `character_text`.
     - narrator_text: lời dẫn chuyện (không giới hạn độ dài).
     - character_text: lời thoại trực tiếp. LUẬT SINH TỒN: TỔNG ký tự
       ``character_text`` TRÊN TOÀN TẬP KHÔNG vượt quá ``settings.max_character_dialogue_chars`` (1000).
       Nếu vượt, hệ thống cắt từ scene cuối cùng trở lên cho tới khi hợp lệ.
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

SCENE1_SCHEMA = {
    "type": "object",
    "required": ["scene", "audio_directive", "cinematic_video_prompt", "sfx_tag"],
    "properties": {
        "scene": {"type": "integer", "enum": [1]},
        "actor": {"type": "string"},
        "audio_directive": {
            "type": "object",
            "properties": {
                "narrator_text": {"type": "string"},
                "character_text": {"type": "string"}
            }
        },
        "cinematic_video_prompt": {"type": "string", "minLength": 40},
        "sfx_tag": {"type": "string"},
        "comic_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "no_ad": {"type": "boolean"},
    },
    "not": {"required": ["image_prompt", "dialogue", "speaker_role"]},
}

SCENE_SCHEMA = {
    "type": "object",
    "required": ["scene", "audio_directive", "image_prompt", "sfx_tag"],
    "properties": {
        "scene": {"type": "integer"},
        "actor": {"type": "string"},
        "audio_directive": {
            "type": "object",
            "properties": {
                "narrator_text": {"type": "string"},
                "character_text": {"type": "string"}
            }
        },
        "image_prompt": {"type": "string"},
        "sfx_tag": {"type": "string"},
        "comic_text": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "no_ad": {"type": "boolean"},
        "is_glitch": {"type": "boolean"},
    },
    "not": {"required": ["dialogue", "speaker_role"]}
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


# ---------- Stage 1: outline ----------

def stage1_outline(alchemy_prompt: str, scenes: int, budget) -> dict:
    extra = (
        f"\n\nTRẢ VỀ JSON đúng schema sau, đúng {scenes} phân cảnh:\n"
        + json.dumps(OUTLINE_SCHEMA)
        + "\n\nLƯU Ý: nếu khung kịch bản đã đánh dấu phân cảnh xuyên không / "
        "glitch (thường scene 8 trong tập 15) thì giữ nguyên is_glitch=true."
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

_CHAR_BUDGET_HINT = (
    "\n- audio_directive: TUYỆT ĐỐI tuân thủ giới hạn ngân sách. "
    "TỔNG lượng ký tự trong 'character_text' trên CẢ TẬP không được vượt quá "
    f"{getattr(settings, 'max_character_dialogue_chars', 1000)} ký tự."
)

def _scene1_prompt(outline_meta: dict, scene_skel: dict) -> str:
    extras = ""
    if settings.enable_comic_sfx:
        extras += ("\n- comic_text (TÙY CHỌN): nếu có sát thương tâm lý / bất ngờ lớn, "
                   "điền 1-3 từ ALL CAPS. Không cần thì bỏ trống.")
    return (
        "Bạn là đạo diễn hình ảnh + biên kịch cho video dọc 9:16.\n"
        f"Bối cảnh tập: title={outline_meta.get('episode_title')}, "
        f"emotion={outline_meta.get('emotion_tag')}\n\n"
        f"Phân cảnh Scene 1 (THE HOOK) — phân cảnh do CON NGƯỜI tự dựng video:\n"
        f"{json.dumps(scene_skel, ensure_ascii=False)}\n\n"
        "Hãy viết:\n"
        "- audio_directive: Trả về object chứa 'narrator_text' (dẫn truyện) và 'character_text' (thoại nhân vật).\n"
        "- cinematic_video_prompt: BẰNG TIẾNG ANH chuyên nghiệp, 80-120 từ, miêu tả camera/lighting/mood/subject cho 1 clip 5s. Không kèm dialogue.\n"
        "- sfx_tag: 1 từ ∈ {tense, dramatic, sad, twist, calm, hopeful, dark}.\n"
        + _CHAR_BUDGET_HINT + extras +
        "\n- TUYỆT ĐỐI không sinh image_prompt cho Scene 1.\n\n"
        f"TRẢ VỀ JSON theo schema:\n{json.dumps(SCENE1_SCHEMA)}"
    )

def _scene_prompt(outline_meta: dict, scene_skel: dict) -> str:
    extras = ""
    if settings.enable_comic_sfx:
        extras += ("\n- comic_text (TÙY CHỌN): nếu cảnh có drama lớn, "
                   "điền 1-3 từ ALL CAPS (VD: 'BANG!').")
    return (
        "Bạn là biên kịch + đạo diễn hình ảnh cho video dọc 9:16.\n"
        f"Tập: {outline_meta.get('episode_title')} | "
        f"emotion: {outline_meta.get('emotion_tag')}\n"
        f"Phân cảnh:\n{json.dumps(scene_skel, ensure_ascii=False)}\n\n"
        "Hãy viết:\n"
        "- audio_directive: Trả về object chứa 'narrator_text' (dẫn truyện) và 'character_text' (thoại nhân vật).\n"
        "- image_prompt: TIẾNG ANH, chi tiết camera/lighting/composition, style 'cinematic comic'.\n"
        "- sfx_tag: 1 từ ∈ {tense, dramatic, sad, twist, calm, hopeful, dark}.\n"
        + _CHAR_BUDGET_HINT + extras +
        "\n- Giữ nguyên scene number và actor.\n\n"
        f"TRẢ VỀ JSON theo schema:\n{json.dumps(SCENE_SCHEMA)}"
    )

def stage2_scene(outline_meta: dict, scene_skel: dict, scene_index: int, budget) -> dict:
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
            data.setdefault("audio_directive", {"narrator_text": "", "character_text": ""})
            
            if scene_skel.get("no_ad"):    data["no_ad"] = True
            if scene_skel.get("is_glitch"): data["is_glitch"] = True
            if is_hook and "image_prompt" in data:
                data.pop("image_prompt", None)
            validate(data, schema)
            log.info("scene %d OK (key …%s)%s",
                     data["scene"], key[-6:], " [HOOK]" if is_hook else "")
            return data
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)[:200]
            log.warning("scene %d JSON err (key …%s): %s",
                        scene_skel.get("scene"), key[-6:], last_err)
            try: budget.consume("json_error")
            except Exception: pass
        except Exception as e:
            log.warning("scene %d LLM err (key …%s): %s",
                        scene_skel.get("scene"), key[-6:], e)
            gemini_pool.mark_dead(key)
            try: budget.consume("content_filter")
            except Exception: pass
    raise RuntimeError(f"Scene {scene_skel.get('scene')} thất bại trên toàn bộ key.")

# ---------- Enforce ngân sách 1000 ký tự cho character ----------

def _enforce_character_budget(scenes: List[Dict]) -> None:
    cap = getattr(settings, "max_character_dialogue_chars", 1000)
    total = sum(len(s.get("audio_directive", {}).get("character_text") or "") for s in scenes)
    if total <= cap:
        return
    log.warning("Character dialogue %d ký tự > cap %d — cắt dần từ cuối.", total, cap)
    
    # Quét NGƯỢC: cắt chữ từ các scene cuối cho tới khi đạt cap
    for s in reversed(scenes):
        if total <= cap: break
        char_text = s.get("audio_directive", {}).get("character_text", "")
        if not char_text: continue
        
        if total - len(char_text) <= cap:
            keep = max(0, cap - (total - len(char_text)))
            s["audio_directive"]["character_text"] = char_text[:keep].rstrip()
            total = total - len(char_text) + len(s["audio_directive"]["character_text"])
            log.info("Cắt thoại nhân vật scene %s xuống %d ký tự.", s.get("scene"), len(s["audio_directive"]["character_text"]))
        else:
            # Hạ luôn thoại character
            s["audio_directive"]["character_text"] = ""
            total -= len(char_text)
            log.info("Xóa trắng thoại nhân vật scene %s.", s.get("scene"))

def generate_script(alchemy_prompt: str, scenes: int, budget) -> dict:
    outline = stage1_outline(alchemy_prompt, scenes, budget)
    meta = {"episode_title": outline["episode_title"],
            "emotion_tag":   outline["emotion_tag"]}
    enriched: List[Dict] = []
    for i, skel in enumerate(outline["scenes"]):
        enriched.append(stage2_scene(meta, skel, i, budget))
    _enforce_character_budget(enriched)
    return {
        "episode_title": meta["episode_title"],
        "emotion_tag":   meta["emotion_tag"],
        "scenes":        enriched,
    }

def get_director_system_prompt():
    return """
    Ngươi là Tổng Đạo Diễn CHIMERA. Nhiệm vụ của ngươi là viết chi tiết 15 phân cảnh dựa trên Khung Xương đã duyệt.
    
    BẢO TOÀN CẤU TRÚC GIAO DIỆN (UI): Phải trả về chính xác 15 phân cảnh, không thêm, không bớt.
    
    [KỶ LUẬT HÌNH ẢNH MẶC ĐỊNH]
    - DUY NHẤT Scene 1: KHÔNG CÓ trường 'image_prompt'. BẮT BUỘC có 'cinematic_video_prompt'.
    - TỪ Scene 2 ĐẾN Scene 15: KHÔNG CÓ 'cinematic_video_prompt'. BẮT BUỘC có 'image_prompt'.
    
    [KỶ LUẬT ÂM THANH HYBRID - QUẢN TRỊ NGÂN SÁCH]
    Trong mỗi phân cảnh, âm thanh (audio_directive) phải được chia làm 2 phần tĩnh biệt:
    1. "narrator_text": Lời dẫn truyện, giải thích nội tâm, bối cảnh (Đọc trước). KHÔNG GIỚI HẠN KÝ TỰ.
    2. "character_text": Lời thoại trực tiếp của nhân vật (Đọc sau). Nếu không có ai nói, để rỗng "".
    
    LUẬT SINH TỒN: Tổng số ký tự của tất cả các trường "character_text" trong toàn bộ 15 phân cảnh TUYỆT ĐỐI KHÔNG ĐƯỢC VƯỢT QUÁ 1.000 KÝ TỰ. Hãy để thoại nhân vật thật ngắn gọn, sắc lẹm và mang tính sát thương cao.
    """

def extract_hook_video_prompt(script: dict) -> str:
    scenes = script.get("scenes") or []
    if not scenes: return ""
    return (scenes[0].get("cinematic_video_prompt") or "").strip()
