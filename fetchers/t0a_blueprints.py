"""Trạm T0a: Duy trì dân số thế giới (World Population Maintenance).

Vai trò đã được phân tách rõ ràng:
  - T0a (Stage 1): Kiểm tra và duy trì dân số nền của thế giới.
    Đảm bảo luôn có đủ công dân sống để thế giới không trống rỗng.
    KHÔNG còn chọn nhân vật cho tập phim (việc đó giờ thuộc về CharacterFactory).

  - CharacterFactory (Stage 2, trước A1): Đúc nhân vật theo yêu cầu (on-demand).
    Tung xúc sắc blueprint → randomize stats → tên VN → gọi A0 inline → MongoDB.

Phân tách này đảm bảo:
  - Nhân vật tập phim luôn mới, không bị tái sử dụng máy móc.
  - A1 không bao giờ tự ý định nghĩa nhân vật.
  - World state vẫn có dân số nền phong phú để Simulator tham chiếu.
"""
import random
import uuid
import logging
from fetchers.base_station import BaseStation
from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# Dân số tối thiểu của thế giới (background NPCs, không nhất thiết xuất hiện trong tập)
MIN_WORLD_POPULATION = 15

# Tên tiếng Việt (dùng cho dân số nền)
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
      "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM_NAM = ["Văn", "Hữu", "Đức", "Công", "Minh", "Quang", "Bảo", "Đình",
           "Tuấn", "Hoàng", "Thái", "Gia", "Trọng"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Phương", "Bích", "Thanh", "Mỹ", "Như",
          "Diễm", "Kiều", "Hồng", "Mai", "Trúc"]
TEN_NAM = ["Nam", "Hải", "Phong", "Long", "Khoa", "Kiên", "Đạt", "Phúc",
           "Thành", "Tùng", "Sơn", "Huy", "Cường", "Tuấn"]
TEN_NU = ["Trang", "Linh", "Hương", "Lan", "Mai", "Vy", "Thảo", "Ngọc",
          "Hà", "Yến", "Nhi", "Anh", "Ly", "Khuê"]


def _generate_vn_name(gender: str = "M") -> str:
    ho = random.choice(HO)
    if gender == "M":
        return f"{ho} {random.choice(DEM_NAM)} {random.choice(TEN_NAM)}"
    return f"{ho} {random.choice(DEM_NU)} {random.choice(TEN_NU)}"


class T0aBlueprints(BaseStation):
    """Trạm T0a: Duy trì dân số nền của thế giới Chimera.

    Output của trạm này là danh sách công dân đang sống trong thế giới
    (dùng để Simulator tham chiếu quan hệ, faction, economy).
    Không phải danh sách nhân vật sẽ xuất hiện trong tập — việc đó
    thuộc về CharacterFactory ở Stage 2.
    """

    station_id = "T0a"

    def _execute(self):
        db = ChimeraDB()

        # 1. Lấy danh sách dân số hiện tại
        alive_chars = list(db.permanent.character_states.find(
            {"status": "alive"}, {"_id": 0}
        ))

        # 2. Bổ sung nếu dân số nền xuống thấp hơn ngưỡng
        if len(alive_chars) < MIN_WORLD_POPULATION:
            needed = MIN_WORLD_POPULATION - len(alive_chars)
            logger.info(
                f"[T0a] Dân số nền thiếu {needed} công dân. "
                f"Đúc nền từ Blueprints (không qua A0, không visual_lock)..."
            )

            blueprints = list(db.permanent.character_blueprints.find({}))
            if not blueprints:
                logger.warning("[T0a] Không có blueprint nào. Bỏ qua bổ sung dân số.")
            else:
                for _ in range(needed):
                    bp = random.choice(blueprints)
                    gender = bp.get("gender", random.choice(["M", "F"]))
                    name = _generate_vn_name(gender)
                    char_id = f"npc_{uuid.uuid4().hex[:6]}"

                    # Dân số nền: chỉ stats cơ bản, không visual_lock
                    # (họ là background, không cần ảnh)
                    base_matrix = bp.get("core_data", {}).get("1_base_stats_matrix_1_100", {})
                    simple_stats = {}
                    if base_matrix:
                        for cat, vals in base_matrix.items():
                            for stat, val in vals.items():
                                simple_stats[stat] = max(0, min(100, val + random.randint(-10, 10)))

                    npc = {
                        "character_id": char_id,
                        "name": name,
                        "gender": gender,
                        "blueprint_id": bp.get("blueprint_id", ""),
                        "archetype_name": bp.get("archetype_name", ""),
                        "role": "Background",
                        "stats": simple_stats,
                        "status": "alive",
                        "visual_prompt_en": "",
                        "visual_locked": False,  # NPC nền không cần visual lock
                    }
                    db.permanent.character_states.insert_one(npc)
                    alive_chars.append(npc)
                    logger.info(f"[T0a] NPC nền: {name} ({char_id})")

        logger.info(f"[T0a] Dân số thế giới: {len(alive_chars)} công dân còn sống.")

        # 3. Trả về toàn bộ dân số (để Simulator dùng, không phải để A1 dùng)
        return alive_chars
