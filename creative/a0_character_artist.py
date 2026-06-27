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
                    "Tối đa 30 từ. Chỉ tập trung vào khuôn mặt, kiểu tóc, và trang phục đặc trưng."
    )

class A0CharacterArtist:
    """Trạm A0: Vẽ ngoại hình cho các nhân vật chưa có hình ảnh."""
    
    def __init__(self):
        self.db = ChimeraDB()
        self.model_name = "gemini-2.5-flash"

    def process_payload_characters(self, master_payload: dict) -> dict:
        """Duyệt qua payload, tìm nhân vật chưa có hình, gọi LLM vẽ và lưu DB bằng Python thuần."""
        
        # 1. Thu thập toàn bộ nhân vật từ Payload
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
                
        # 2. Lọc unique và kiểm tra khóa
        unique_chars = {}
        for c in characters:
            if not isinstance(c, dict): continue
            cid = c.get("character_id") or c.get("_id") or c.get("name")
            if cid:
                unique_chars[cid] = c
                
        # 3. Tiến hành vẽ và khóa
        for char_id, char_data in unique_chars.items():
            if not char_data.get("visual_locked", False) or not char_data.get("visual_prompt_en"):
                logger.info(f"[A0] Phat hien '{char_data.get('name')}' chua co ngoai hinh. Bat dau ve...")
                self._draw_and_lock_character(char_id, char_data)
                
        return master_payload

    def _draw_and_lock_character(self, char_id: str, char_data: dict, _attempt: int = 0):
        import google.generativeai as genai
        
        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            logger.error(f"[A0] That bai khi ve nhan vat {char_id}. Dung Fallback.")
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
                f"YÊU CẦU: Trả về JSON chứa 'visual_prompt_en' theo cấu trúc:\n{schema_str}"
            )
            
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction="Chỉ trả về JSON thuần túy.",
            )
            
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.8},
            )
            
            data = json.loads(response.text)
            visual_prompt = A0VisualOutput(**data).visual_prompt_en
            
            # CHỐT CHẶT: GHI VÀO MONGODB BẰNG PYTHON THUẦN
            self._save_to_db(char_id, char_data, visual_prompt)
            
        except Exception as e:
            logger.error(f"[A0] Loi LLM khi ve nhan vat {char_id}: {e}")
            GEMINI_POOL.mark_failed(key)
            self._draw_and_lock_character(char_id, char_data, _attempt + 1)
            
    def _save_to_db(self, char_id: str, char_data: dict, visual_prompt: str):
        try:
            # Lưu vĩnh viễn vào Database
            update_query = {"$set": {"visual_prompt_en": visual_prompt, "visual_locked": True}}
            self.db.permanent.character_profiles.update_one({"character_id": char_id}, update_query)
            self.db.permanent.character_states.update_one({"character_id": char_id}, update_query)
            
            # Cập nhật trực tiếp vào payload in-memory để A1 xài luôn
            char_data["visual_prompt_en"] = visual_prompt
            char_data["visual_locked"] = True
            
            logger.info(f"[A0] KHÓA THÀNH CÔNG ngoại hình cho '{char_data.get('name')}'")
        except Exception as e:
            logger.error(f"[A0] Loi ghi MongoDB: {e}")
