import logging
from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

class A0CharacterArtist:
    """Trạm A0: Cấp phát và Khóa ngoại hình (Visual Lock) cho thực thể mới."""
    
    def __init__(self):
        self.db = ChimeraDB()

    def get_or_create_visual_lock(self, entity_id: str, blueprint_data: dict) -> dict:
        """Kiểm tra DB, nếu nhân vật chưa có mặt thì tạo mới và khóa lại."""
        # 1. Kiểm tra Cụm Não Số 1
        existing_char = self.db.permanent.characters.find_one({"entity_id": entity_id})
        
        if existing_char and "visual_lock" in existing_char:
            logger.info(f"[A0] Nhan vat {entity_id} da co ngoai hinh. Tai su dung.")
            return existing_char["visual_lock"]

        # 2. Nếu chưa có, gọi LLM (Groq/Gemini) để sinh Visual Lock dựa trên Blueprint
        logger.info(f"[A0] Nhan vat {entity_id} chua co mat. Dang tien hanh ve...")
        new_visual_lock = self._generate_visual_prompt_from_llm(blueprint_data)
        
        # 3. Lưu cứng vào Database
        self.db.permanent.characters.update_one(
            {"entity_id": entity_id},
            {"$set": {
                "blueprint_id": blueprint_data["blueprint_id"],
                "full_name": blueprint_data["full_name"],
                "visual_lock": new_visual_lock
            }},
            upsert=True
        )
        return new_visual_lock

    def _generate_visual_prompt_from_llm(self, blueprint_data: dict) -> dict:
        # TODO: Gọi LLM tạo prompt tiếng Anh mô tả tĩnh (tuổi, tóc, sẹo, quần áo signature)
        # Trả về format: {"image_prompt_en": "...", "fixed_accessories": "..."}
        pass

