"""Trạm A0: Cấp phát và Khóa ngoại hình (Visual Lock) bằng AI, lưu DB bằng Python thuần."""
import json
import logging
from pydantic import BaseModel, Field

from core.db_client import ChimeraDB
from core.credential_manager import GEMINI_POOL

logger = logging.getLogger(__name__)

class A0VisualOutput(BaseModel):
    visual_prompt_en: str = Field(
        description="Miêu tả ngoại hình nhân vật bằng tiếng Anh (dành cho AI tạo ảnh). "
                    "Tối đa 30 từ. Chỉ tập trung vào khuôn mặt, độ tuổi, kiểu tóc, và trang phục đặc trưng."
    )

class A0CharacterArtist:
    
    def __init__(self):
        self.db = ChimeraDB()
        self.model_name = "gemini-2.5-flash"

    def process_payload_characters(self, master_payload: dict) -> dict:
        """Duyệt payload, tìm nhân vật chưa có hình, gọi LLM vẽ và lưu DB."""
        
        characters = []
        if "protagonists" in master_payload:
            characters.extend(master_payload["protagonists"])
        if "supporting_cast" in master_payload:
            characters.extend(master_payload["supporting_cast"])
            
        ctx = master_payload.get("context_slice_v2", {})
        if "layer_2_character_states" in ctx:
            states = ctx["layer_2_character_states"]
            if isinstance(states, dict):
                characters.extend(states.values())
            elif isinstance(states, list):
                characters.extend(states)
                
        unique_chars = {}
        for c in characters:
            if not isinstance(c, dict): continue
            cid = c.get("character_id") or c.get("_id") or c.get("name")
            if cid:
                unique_chars[cid] = c
                
        for char_id, char_data in unique_chars.items():
            if not char_data.get("visual_locked", False) or not char_data.get("visual_prompt_en"):
                logger.info(f"[A0] Phát hiện '{char_data.get('name')}' chưa có ngoại hình. Bắt đầu cấp phát...")
                self._draw_and_lock_character(char_id, char_data)
                
        return master_payload

    def _draw_and_lock_character(self, char_id: str, char_data: dict, _attempt: int = 0):
        import google.generativeai as genai
        
        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            logger.error(f"[A0] Thất bại khi vẽ nhân vật {char_id}. Dùng Fallback.")
            fallback_prompt = f"A cinematic portrait of a Vietnamese character named {char_data.get('name', 'Unknown')}, highly detailed, 8k"
            self._save_to_db(char_id, char_data, fallback_prompt)
            return

        key = GEMINI_POOL.get_next()
        if not key:
            return

        try:
            genai.configure(api_key=key)
            schema_str = json.dumps(A0VisualOutput.model_json_schema(), ensure_ascii=False)
            
            prompt = (
                f"Bạn là A0 (Họa sĩ thiết kế). Hãy sáng tạo ngoại hình (prompt tiếng Anh) "
                f"cho nhân vật Việt Nam sau:\n"
                f"- Tên: {char_data.get('name', 'Unknown')}\n"
                f"- Vai trò: {char_data.get('role', 'Unknown')}\n"
                f"- Tính cách: {', '.join(char_data.get('traits', []))}\n"
                f"YÊU CẦU: Trả về JSON thuần túy chứa 'visual_prompt_en'.\n"
                f"CẤU TRÚC JSON:\n{schema_str}"
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction="Chỉ trả về JSON thuần túy, không định dạng markdown.",
            )
            
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.8},
            )
            
            data = json.loads(response.text)
            visual_prompt = A0VisualOutput(**data).visual_prompt_en
            
            # Ghi vào MongoDB bằng Python thuần
            self._save_to_db(char_id, char_data, visual_prompt)
            
        except Exception as e:
            logger.error(f"[A0] Lỗi LLM khi vẽ nhân vật {char_id}: {e}")
            GEMINI_POOL.mark_failed(key)
            self._draw_and_lock_character(char_id, char_data, _attempt + 1)
            
    def _save_to_db(self, char_id: str, char_data: dict, visual_prompt: str):
        try:
            update_query = {"$set": {"visual_prompt_en": visual_prompt, "visual_locked": True}}
            # Lưu vào Database
            self.db.permanent.character_states.update_one({"character_id": char_id}, update_query)
            
            # Cập nhật trực tiếp vào payload in-memory để A1 xài luôn
            char_data["visual_prompt_en"] = visual_prompt
            char_data["visual_locked"] = True
            
            logger.info(f"[A0] KHÓA THÀNH CÔNG ngoại hình cho '{char_data.get('name')}'.")
        except Exception as e:
            logger.error(f"[A0] Lỗi ghi MongoDB: {e}")
