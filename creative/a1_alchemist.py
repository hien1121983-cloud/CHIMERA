"""Tram A1 (Va C-01: retry huu han)."""
import json
import logging

from core.credential_manager import GEMINI_POOL
from creative.prompt_templates import A1_SYSTEM_PROMPT
from creative.schemas import A1Output

logger = logging.getLogger(__name__)


class A1Alchemist:
    """Tram A1: Goi Gemini 2.5 Flash de sinh 3 ban nhap kich ban."""

    def __init__(self):
        self.model_name = "gemini-2.5-flash"

    def generate_3_drafts(self, master_payload: dict, _attempt: int = 0) -> list:
        """Sinh 3 ban nhap voi co che retry huu han.

        Va C-01: Gioi han so lan thu bang active_count + 1.
        """
        import google.generativeai as genai

        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            raise RuntimeError(
                f"[A1] Tat ca {GEMINI_POOL.active_count} Gemini key da that bai "
                f"sau {_attempt} lan thu."
            )

        key = GEMINI_POOL.get_next()
        if not key:
            raise RuntimeError("[A1] Khong co Gemini key kha dung.")

        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=A1_SYSTEM_PROMPT,
            )
            response = model.generate_content(
                json.dumps(master_payload, ensure_ascii=False, default=str),
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": A1Output,
                    "temperature": 0.9,
                },
            )
            data = json.loads(response.text)
            validated = A1Output(**data)
            logger.info(
                f"[A1] Sinh thanh cong 3 drafts. "
                f"Creativity scores: {[d.creativity_score for d in validated.drafts]}"
            )
            return validated.model_dump()["drafts"]
        except json.JSONDecodeError as e:
            logger.error(f"[A1] JSON parse loi: {e}")
            GEMINI_POOL.mark_failed(key)
            return self.generate_3_drafts(master_payload, _attempt + 1)
        except Exception as e:
            logger.error(f"[A1] Loi goi Gemini: {e}")
            GEMINI_POOL.mark_failed(key)
            return self.generate_3_drafts(master_payload, _attempt + 1)
