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
            
            # FIX LỖI maxItems: Ép Gemini sinh đúng 3 drafts thông qua Prompt thay vì Schema
            enforced_prompt = (
                A1_SYSTEM_PROMPT + 
                "\n\n[QUAN TRỌNG] BẮT BUỘC TRẢ VỀ CHÍNH XÁC 3 BẢN NHÁP (DRAFTS) TRONG MẢNG. KHÔNG ĐƯỢC NHIỀU HƠN HOẶC ÍT HƠN."
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=enforced_prompt,
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

    def generate_3_drafts_with_warning(self, master_payload: dict, warning: str, _attempt: int = 0) -> list:
        """Sinh 3 ban nhap voi canh bao dac biet tu Auditor (Va loi Retry).
        
        Ep nhiet do (temperature) len 1.0 va tiem canh bao vao system_prompt
        de LLM bat buoc phai sang tao mot huong di hoan toan khac.
        """
        import google.generativeai as genai

        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            raise RuntimeError(
                f"[A1] Tat ca {GEMINI_POOL.active_count} Gemini key da that bai "
                f"sau {_attempt} lan thu (khi dang retry voi warning)."
            )

        key = GEMINI_POOL.get_next()
        if not key:
            raise RuntimeError("[A1] Khong co Gemini key kha dung.")

        try:
            genai.configure(api_key=key)
            
            # Tiem canh bao vao thang system instruction
            dynamic_system_prompt = (
                A1_SYSTEM_PROMPT + 
                f"\n\n[WARNING FROM AUDITOR - BAT BUOC PHAI DOC]\n{warning}\n"
                f"YEU CAU: Hay sang tao mot huong di, cot truyen hoan toan khac biet so voi ban truoc do!\n"
                f"[QUAN TRỌNG] BẮT BUỘC TRẢ VỀ CHÍNH XÁC 3 BẢN NHÁP (DRAFTS)."
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=dynamic_system_prompt,
            )
            
            response = model.generate_content(
                json.dumps(master_payload, ensure_ascii=False, default=str),
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": A1Output,
                    "temperature": 1.0,  # Tang nhiet do toi da de ep thoat khoi loi mon
                },
            )
            data = json.loads(response.text)
            validated = A1Output(**data)
            logger.info(
                f"[A1] Sinh thanh cong 3 drafts (kem WARNING). "
                f"Creativity scores: {[d.creativity_score for d in validated.drafts]}"
            )
            return validated.model_dump()["drafts"]
        except json.JSONDecodeError as e:
            logger.error(f"[A1] JSON parse loi (khi xu ly warning): {e}")
            GEMINI_POOL.mark_failed(key)
            return self.generate_3_drafts_with_warning(master_payload, warning, _attempt + 1)
        except Exception as e:
            logger.error(f"[A1] Loi goi Gemini (khi xu ly warning): {e}")
            GEMINI_POOL.mark_failed(key)
            return self.generate_3_drafts_with_warning(master_payload, warning, _attempt + 1)
