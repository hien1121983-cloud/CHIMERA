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
        """Sinh 3 ban nhap voi co che retry huu han."""
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
            
            # GIẢI PHÁP TỐI THƯỢNG: Trích xuất Schema từ Pydantic và nhúng thẳng vào Prompt
            # Điều này giúp lách qua hoàn toàn bộ dịch Schema bị lỗi của thư viện genai cũ.
            schema_str = json.dumps(A1Output.model_json_schema(), ensure_ascii=False, indent=2)
            enforced_prompt = (
                A1_SYSTEM_PROMPT + 
                "\n\n[QUAN TRỌNG] BẮT BUỘC TRẢ VỀ CHÍNH XÁC 3 BẢN NHÁP (DRAFTS) TRONG MẢNG.\n"
                "BẠN BẮT BUỘC PHẢI TRẢ VỀ DỮ LIỆU JSON TUÂN THỦ NGHIÊM NGẶT CẤU TRÚC SAU ĐÂY:\n"
                f"{schema_str}"
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=enforced_prompt,
            )
            
            # Đã xóa "response_schema" khỏi generation_config, chỉ giữ lại mime_type JSON
            response = model.generate_content(
                json.dumps(master_payload, ensure_ascii=False, default=str),
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.9,
                },
            )
            
            # Pydantic sẽ chịu trách nhiệm kiểm tra cấu trúc thay cho SDK
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
        """Sinh 3 ban nhap voi canh bao dac biet tu Auditor."""
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
            
            schema_str = json.dumps(A1Output.model_json_schema(), ensure_ascii=False, indent=2)
            dynamic_system_prompt = (
                A1_SYSTEM_PROMPT + 
                f"\n\n[WARNING FROM AUDITOR - BAT BUOC PHAI DOC]\n{warning}\n"
                f"YEU CAU: Hay sang tao mot huong di, cot truyen hoan toan khac biet so voi ban truoc do!\n"
                f"[QUAN TRỌNG] BẮT BUỘC TRẢ VỀ CHÍNH XÁC 3 BẢN NHÁP (DRAFTS).\n"
                "BẠN BẮT BUỘC PHẢI TRẢ VỀ DỮ LIỆU JSON TUÂN THỦ NGHIÊM NGẶT CẤU TRÚC SAU ĐÂY:\n"
                f"{schema_str}"
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=dynamic_system_prompt,
            )
            
            response = model.generate_content(
                json.dumps(master_payload, ensure_ascii=False, default=str),
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 1.0, 
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
