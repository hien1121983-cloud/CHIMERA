"""Tram A2 (Groq): boc tach Master_Script -> Execution.json."""
import json
import logging

from core.credential_manager import GROQ_POOL
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
        self.model = "llama-3.3-70b-versatile"
        self.visual_lock = VisualLockManager()

    def decompose_script(self, master_script: dict, _attempt: int = 0) -> dict:
        """Boc tach Master_Script thanh Execution JSON (retry huu han)."""
        import groq

        max_attempts = GROQ_POOL.active_count + 1
        if _attempt >= max_attempts:
            raise RuntimeError(
                f"[A2] Tat ca {GROQ_POOL.active_count} Groq key da that bai "
                f"sau {_attempt} lan thu."
            )

        key = GROQ_POOL.get_next()
        if not key:
            raise RuntimeError("[A2] Khong co Groq key kha dung.")

        try:
            client = groq.Groq(api_key=key)
            enriched_script = self._inject_visual_lock(master_script)

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": A2_SYSTEM_PROMPT},
                    {"role": "user",
                     "content": json.dumps(enriched_script, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=8000,
            )
            result = json.loads(response.choices[0].message.content)

            input_scenes = len(master_script.get("script", {}).get("scenes", []))
            output_scenes = len(result.get("scenes", []))
            if input_scenes and output_scenes != input_scenes:
                logger.warning(
                    f"[A2] Scene mismatch: input={input_scenes} output={output_scenes}"
                )
                raise ValueError("Scene count mismatch")

            logger.info(f"[A2] Boc tach thanh cong {output_scenes} scenes")
            return result
        except Exception as e:
            logger.error(f"[A2] Loi: {e}")
            GROQ_POOL.mark_failed(key)
            return self.decompose_script(master_script, _attempt + 1)

    def _inject_visual_lock(self, master_script: dict) -> dict:
        """Inject visual_lock_seed + ghep prompt nhan vat khoa vao moi scene
        truoc khi gui Groq.

        Voi moi scene:
        1. Xac dinh characters_present tu danh sach dialogues.
        2. Voi MOI nhan vat co mat, tra cuu visual_prompt_en DA KHOA (A0)
           qua VisualLockManager.get_visual_prompt_for_character().
        3. Enrich prompt canh goc (tu A1) voi hau to ky thuat (9:16, cinematic...).
        4. Ghep tat ca thanh 1 prompt hoan chinh theo dinh dang:
           "Character A: <mo ta>; Character B: <mo ta>; Scene: <mo ta canh>"
           va GHI DE truc tiep vao scene["visual_prompt_en"].

        Day la buoc bat buoc de dam bao nhan vat giu nguyen ngoai hinh da
        khoa giua cac scene khi Pollinations ve anh - neu thieu, ImageGenerator
        chi nhan duoc prompt canh chung do A1 tu bia, khong he biet nhan vat
        trong canh do trong nhu the nao.
        """
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

            # Tra cuu prompt khoa cho TAT CA nhan vat co mat (giu thu tu xuat hien)
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
