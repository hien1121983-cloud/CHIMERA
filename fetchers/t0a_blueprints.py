"""Trạm T0a: Quản lý Công dân (Đúc người mới hoặc lấy người đang sống)."""
import random
import uuid
import logging
from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# TỪ ĐIỂN TÊN TIẾNG VIỆT
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM_NAM = ["Văn", "Hữu", "Đức", "Công", "Minh", "Quang", "Bảo", "Đình", "Tuấn", "Hoàng", "Thái", "Gia", "Trọng"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương", "Bích", "Thanh", "Mỹ", "Như", "Diễm", "Kiều", "Hồng", "Mai", "Trúc"]
TEN_NAM = ["Nam", "Hải", "Phong", "Long", "Khoa", "Kiên", "Đạt", "Phúc", "Thành", "Tùng", "Sơn", "Huy", "Cường", "Tuấn"]
TEN_NU = ["Trang", "Linh", "Hương", "Lan", "Mai", "Vy", "Thảo", "Ngọc", "Hà", "Yến", "Nhi", "Anh", "Ly", "Khuê"]

class T0aBlueprints(BaseStation):
    station_id = "T0a"

    def _generate_vn_name(self, gender="M") -> str:
        """Tổ hợp ngẫu nhiên Họ, Đệm, Tên."""
        ho = random.choice(HO)
        if gender == "M":
            return f"{ho} {random.choice(DEM_NAM)} {random.choice(TEN_NAM)}"
        return f"{ho} {random.choice(DEM_NU)} {random.choice(TEN_NU)}"

    def _execute(self):
        db = ChimeraDB()
        
        # 1. Lấy danh sách Công dân ĐANG SỐNG trong thế giới (Character States)
        active_chars = list(db.permanent.character_states.find({"status": "alive"}, {"_id": 0}))

        # 2. Bổ sung nếu thiếu (Cần duy trì tối thiểu 9 người tham gia)
        if len(active_chars) < 9:
            needed = 9 - len(active_chars)
            logger.info(f"[T0a] Thiếu {needed} công dân. Bắt đầu đúc người mới từ Blueprints...")
            
            # Lấy Blueprints (Bộ Khung DNA)
            blueprints = list(db.permanent.character_blueprints.find({}))
            if not blueprints:
                blueprints = [{"_id": f"bp_auto_{i}", "role": "Citizen", "gender": random.choice(["M", "F"]), "traits": ["Bình thường"]} for i in range(needed)]
            
            for _ in range(needed):
                bp = random.choice(blueprints)
                gender = bp.get("gender", random.choice(["M", "F"]))
                full_name = self._generate_vn_name(gender)
                char_id = f"char_{uuid.uuid4().hex[:6]}"

                # Khởi tạo đột biến (Emergent Storytelling) qua Random Python
                traits = bp.get("traits", [])
                stats = {
                    "hp": 100, 
                    "reputation": random.randint(10, 90),
                    "wealth": random.randint(5, 95),
                    "trauma": random.randint(0, 30),
                    "intelligence": random.randint(70, 100) if "Thông minh" in traits else random.randint(10, 80),
                    "strength": random.randint(70, 100) if "Bạo lực" in traits else random.randint(10, 80),
                }

                # Đúc thành một thực thể sống
                new_char = {
                    "character_id": char_id,
                    "name": full_name,
                    "blueprint_id": bp.get("_id"),
                    "role": bp.get("role", "Citizen"),
                    "traits": traits,
                    "stats": stats,
                    "status": "alive",
                    "visual_prompt_en": "",  # TRỐNG - Chờ Trạm A0 vẽ
                    "visual_locked": False
                }

                # Lưu vào DB character_states (Thế giới động)
                db.permanent.character_states.insert_one(new_char)
                active_chars.append(new_char)
                logger.info(f"[T0a] ĐÚC THÀNH CÔNG: {full_name} - ID: {char_id}")

        # 3. Chọn ngẫu nhiên 9 người sẽ xuất hiện trong tập phim này
        selected_for_episode = random.sample(active_chars, min(9, len(active_chars)))
        return selected_for_episode
                
