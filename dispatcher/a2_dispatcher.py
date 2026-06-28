"""Tram A2 (Gemini Uncensored): boc tach Master_Script -> Execution.json."""
import json
import logging

from core.credential_manager import GEMINI_POOL
from dispatcher.visual_lock import VisualLockManager
from dispatcher.prompt_translator import enrich_visual_prompt, build_scene_prompt

logger = logging.getLogger(__name__)

A2_SYSTEM_PROMPT = """
[BAN LA A2 - THE DISPATCHER]
Nhiem vu: Chuyen hoa Master_Script.json thanh Execution.json chi tiet.

NGUYEN TAC BAT BUOC:
1. KHONG them/bot/sua doi bat ky noi dung sang tao nao tu Master_Script.
2. Voi moi dialogue, uoc tinh thoi luong (ms) = so tu tieng Viet x 180ms.
3. Voi moi scene, GIU NGUYEN TUYET DOI visual_prompt_en va visual_lock_seed
   dung y nhu ban nhan duoc trong input - day la prompt da duoc ghep san
   tu prompt khoa nhan vat (A0) + prompt canh (A1), TUYET DOI KHONG viet
   lai, dien giai lai, hay rut gon noi dung nay.
4. Xuat ra JSON dung schema ExecutionSchema.
5. Neu Master_Script co 15 scenes, output BAT BUOC co dung 15 scenes.

OUTPUT SCHEMA:
{
 "meta": {"episode_number": int, "generated_at": "ISO-8601",
          "total_scenes": int, "estimated_duration_seconds": int},
 "scenes": [
   {"scene_id": "S01", "visual_prompt_en": "string", "visual_lock_seed": int,
    "characters_present": ["string"],
    "dialogues": [{"character": "string", "voice_id": "string", "emotion": "string",
                   "line": "string", "estimated_duration_ms": int}],
    "bgm_mood": "string", "camera_angle": "string"}
 ],
 "voice_mapping": {"character_name": "voice_id"}
}
"""

class A2Dispatcher:
    """Boc tach kich ban van hoc thanh lenh thuc thi ky thuat."""

    def __init__(self):
        self.model_name = "gemini-2.5-flash"
        self.visual_lock = VisualLockManager()

    def decompose_script(self, master_script: dict, _attempt: int = 0) -> dict:
        import google.generativeai as genai
        from google.generativeai.types import HarmCategory, HarmBlockThreshold

        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            raise RuntimeError(
                f"[A2] Tat ca {GEMINI_POOL.active_count} Gemini key da that bai "
                f"sau {_attempt} lan thu."
            )

        key = GEMINI_POOL.get_next()
        if not key:
            raise RuntimeError("[A2] Khong co Gemini key kha dung.")

        try:
            genai.configure(api_key=key)
            enriched_script = self._inject_visual_lock(master_script)

            # TẮT TOÀN BỘ KIỂM DUYỆT CỦA GOOGLE (Uncensored Mode)
            # Biến Gemini thành một con AI "dễ tính" nhất có thể
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=A2_SYSTEM_PROMPT,
            )

            # Ép trả về chuẩn JSON không kèm văn bản thừa
            response = model.generate_content(
                json.dumps(enriched_script, ensure_ascii=False),
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1,
                },
                safety_settings=safety_settings
            )
            
            result = json.loads(response.text)

            input_scenes = len(master_script.get("script", {}).get("scenes", []))
            output_scenes = len(result.get("scenes", []))
            if input_scenes and output_scenes != input_scenes:
                logger.warning(
                    f"[A2] Scene mismatch: input={input_scenes} output={output_scenes}"
                )
                raise ValueError("Scene count mismatch")

            logger.info(f"[A2] Boc tach thanh cong {output_scenes} scenes voi Gemini (Uncensored)")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[A2] Loi parse JSON: {e}")
            GEMINI_POOL.mark_failed(key)
            return self.decompose_script(master_script, _attempt + 1)
        except Exception as e:
            logger.error(f"[A2] Loi goi LLM: {e}")
            GEMINI_POOL.mark_failed(key)
            return self.decompose_script(master_script, _attempt + 1)

    def _inject_visual_lock(self, master_script: dict) -> dict:
        import copy

        enriched = copy.deepcopy(master_script)
        scenes = enriched.get("script", {}).get("scenes", [])
        for scene in scenes:
            chars = [d.get("character") for d in scene.get("dialogues", []) if d.get("character")]
            characters_present = list(dict.fromkeys(chars))
            scene["characters_present"] = characters_present
            scene["visual_lock_seed"] = self.visual_lock.get_scene_seed(
                characters_present
            )

            # Tra cuu prompt khoa cho TAT CA nhan vat co mat
            character_prompts = {
                name: self.visual_lock.get_visual_prompt_for_character(name)
                for name in characters_present
            }

            scene_prompt_enriched = enrich_visual_prompt(
                scene.get("visual_prompt_en", "")
            )
            scene["visual_prompt_en"] = build_scene_prompt(
                character_prompts, scene_prompt_enriched
            )
        return enriched
