"""CharacterFactory: Đúc nhân vật theo yêu cầu (T0a on-demand → A0 inline).

Luồng mới (thay thế cách A1 tự ý tạo nhân vật):
  1. Tung xúc sắc chọn 1 trong 9 blueprint từ MongoDB.
  2. Tung xúc sắc randomize stats trong vùng blueprint (±STAT_VARIANCE, clamp 0-100).
  3. Chọn ngẫu nhiên 1-3 inner_conflicts từ pool của blueprint.
  4. Tạo tên tiếng Việt ngẫu nhiên (Họ + Đệm + Tên).
  5. Gọi A0 inline để vẽ visual_prompt_en và world-lock vào MongoDB.
  6. Trả về nhân vật hoàn chỉnh, sẵn sàng cho A1.

Nguyên tắc: Không LLM nào tự định nghĩa nhân vật.
  - T0a (python thuần) = DNA gốc (blueprint + dice roll).
  - A0 (Gemini) = chỉ vẽ khuôn mặt bằng visual_prompt.
  - A1 (Gemini) = đắp thịt kịch bản dựa trên nhân vật đã khóa.
"""
import uuid
import random
import logging
from typing import Optional

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# Variance cho stat randomization: ±N quanh giá trị base của blueprint
# Đủ lớn để tạo cá thể độc đáo, đủ nhỏ để giữ bản sắc archetype
STAT_VARIANCE = 15

# ─── Kho tên tiếng Việt ───────────────────────────────────────────────────────
HO = [
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan",
    "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý",
]
DEM_NAM = [
    "Văn", "Hữu", "Đức", "Công", "Minh", "Quang", "Bảo",
    "Đình", "Tuấn", "Hoàng", "Thái", "Gia", "Trọng",
]
DEM_NU = [
    "Thị", "Ngọc", "Thu", "Phương", "Bích", "Thanh", "Mỹ",
    "Như", "Diễm", "Kiều", "Hồng", "Mai", "Trúc",
]
TEN_NAM = [
    "Nam", "Hải", "Phong", "Long", "Khoa", "Kiên", "Đạt",
    "Phúc", "Thành", "Tùng", "Sơn", "Huy", "Cường", "Tuấn",
]
TEN_NU = [
    "Trang", "Linh", "Hương", "Lan", "Mai", "Vy", "Thảo",
    "Ngọc", "Hà", "Yến", "Nhi", "Anh", "Ly", "Khuê",
]


# ─── Helpers thuần Python ─────────────────────────────────────────────────────

def _roll_vn_name(gender: str = "M") -> str:
    """Tổ hợp ngẫu nhiên Họ + Đệm + Tên theo giới tính."""
    ho = random.choice(HO)
    if gender == "M":
        return f"{ho} {random.choice(DEM_NAM)} {random.choice(TEN_NAM)}"
    return f"{ho} {random.choice(DEM_NU)} {random.choice(TEN_NU)}"


def _roll_stat(base: int) -> int:
    """Tung xúc sắc: giá trị trong [max(0, base-VAR), min(100, base+VAR)]."""
    lo = max(0, base - STAT_VARIANCE)
    hi = min(100, base + STAT_VARIANCE)
    return random.randint(lo, hi)


def _roll_stat_matrix(matrix: dict) -> dict:
    """Áp dụng dice roll cho toàn bộ stat matrix, giữ cấu trúc category → stat."""
    return {
        category: {stat: _roll_stat(val) for stat, val in stats.items()}
        for category, stats in matrix.items()
    }


# ─── CharacterFactory ─────────────────────────────────────────────────────────

class CharacterFactory:
    """Nhà máy đúc nhân vật theo yêu cầu.

    Được gọi từ main_creative_pipeline TRƯỚC khi A1 chạy.
    Đảm bảo mọi nhân vật trong payload đều đã visual_locked=True.
    """

    def __init__(self):
        self.db = ChimeraDB()
        self._blueprints: Optional[list] = None  # lazy-load 1 lần

    # ── Blueprint pool ─────────────────────────────────────────────────────────

    def _load_blueprints(self) -> list:
        if self._blueprints is None:
            self._blueprints = list(self.db.permanent.character_blueprints.find({}))
            if not self._blueprints:
                raise RuntimeError(
                    "[CharacterFactory] Không có Blueprint nào trong DB. "
                    "Hãy chạy database_seeder.py trước."
                )
            logger.info(
                f"[CharacterFactory] Loaded {len(self._blueprints)} blueprints từ DB."
            )
        return self._blueprints

    # ── Mint 1 nhân vật ────────────────────────────────────────────────────────

    def mint_character(self, role: str = "Protagonist") -> dict:
        """Đúc 1 nhân vật hoàn chỉnh: blueprint → dice stats → VN name → A0 lock.

        Args:
            role: "Protagonist" hoặc "Supporting"

        Returns:
            dict nhân vật với visual_prompt_en đã được khóa (visual_locked=True).
        """
        blueprints = self._load_blueprints()

        # ── Bước 1: Tung xúc sắc chọn 1 trong N blueprint ──────────────────
        blueprint = random.choice(blueprints)
        bp_id = blueprint.get("blueprint_id", "bp_unknown")
        archetype_name = blueprint.get("archetype_name", "Unknown Archetype")
        logger.info(f"[CharacterFactory] 🎲 Xúc sắc blueprint → {bp_id} ({archetype_name})")

        # ── Bước 2: Giới tính (blueprint ưu tiên, không có thì 50/50) ────────
        gender = blueprint.get("gender", random.choice(["M", "F"]))

        # ── Bước 3: Tên tiếng Việt ────────────────────────────────────────────
        name = _roll_vn_name(gender)

        # ── Bước 4: Dice roll stats trong vùng blueprint ──────────────────────
        core_data = blueprint.get("core_data", {})
        base_matrix = core_data.get("1_base_stats_matrix_1_100", {})
        rolled_stats = _roll_stat_matrix(base_matrix) if base_matrix else {}

        # Log để debug: so sánh base vs rolled
        if base_matrix and rolled_stats:
            for cat, stats in base_matrix.items():
                rolled_cat = rolled_stats.get(cat, {})
                diffs = {s: rolled_cat[s] - v for s, v in stats.items() if s in rolled_cat}
                logger.debug(f"[CharacterFactory]   {cat}: {diffs}")

        # ── Bước 5: Chọn 1-3 inner_conflict ngẫu nhiên từ pool ───────────────
        conflict_pool = blueprint.get("inner_conflict_pool", [])
        n_conflicts = random.randint(1, min(3, len(conflict_pool))) if conflict_pool else 0
        chosen_conflicts = random.sample(conflict_pool, k=n_conflicts) if conflict_pool else []

        # ── Bước 6: Lắp ráp nhân vật thô ────────────────────────────────────
        char_id = f"char_{uuid.uuid4().hex[:8]}"

        new_char = {
            "character_id": char_id,
            "name": name,
            "gender": gender,
            "blueprint_id": bp_id,
            "archetype_name": archetype_name,
            "role": role,
            # Dữ liệu cốt lõi từ blueprint (A1 sẽ dùng để "đắp thịt")
            "philosophy": core_data.get("_blueprint_philosophy", ""),
            "core_skill": core_data.get("3_economy_and_skills", {}).get("core_skill", ""),
            "income_source": core_data.get("3_economy_and_skills", {}).get("income_source", ""),
            "hidden_debt": core_data.get("3_economy_and_skills", {}).get("hidden_debt", ""),
            "social_class": core_data.get("4_social_network", {}).get("class", ""),
            "allies": core_data.get("4_social_network", {}).get("allies", ""),
            "hidden_enemies": core_data.get("4_social_network", {}).get("hidden_enemies", ""),
            "micro_habits": core_data.get("5_micro_habits", {}),
            "fatal_flaw": core_data.get("6_blindspots_and_risks", {}).get("fatal_flaw", ""),
            "blackmail_secret": core_data.get("6_blindspots_and_risks", {}).get("blackmail_secret", ""),
            "biometrics": core_data.get("2_biometrics_and_health", {}),
            "voice_desc": blueprint.get("elevenlabs_voice_desc", ""),
            # Dice-rolled soul
            "inner_conflicts": chosen_conflicts,
            "stats": rolled_stats,
            # Trạng thái sống
            "status": "alive",
            # Visual (chờ A0)
            "visual_prompt_en": "",
            "visual_locked": False,
        }

        # ── Bước 7: Gọi A0 inline → vẽ + khóa ngoại hình ────────────────────
        new_char = self._request_visual_from_a0(new_char)

        # ── Bước 8: Lưu vào MongoDB (Python thuần) ───────────────────────────
        try:
            self.db.permanent.character_states.replace_one(
                {"character_id": char_id},
                {**new_char},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"[CharacterFactory] Lỗi lưu DB cho {char_id}: {e}")

        logger.info(
            f"[CharacterFactory] ✅ ĐÚCXONG: '{name}' | {bp_id} | "
            f"visual_locked={new_char.get('visual_locked')} | role={role}"
        )
        return new_char

    # ── Mint dàn nhân vật cho 1 tập ───────────────────────────────────────────

    def mint_episode_cast(
        self,
        n_protagonists: int = 2,
        n_supporting: int = 3,
    ) -> dict:
        """Đúc toàn bộ dàn nhân vật cho 1 tập phim.

        Được gọi ở đầu Stage 2, trước khi A1 viết kịch bản.
        Đảm bảo A1 KHÔNG bao giờ tự ý tạo nhân vật.

        Returns:
            {"protagonists": [...], "supporting_cast": [...]}
        """
        logger.info(
            f"[CharacterFactory] 🎬 Đúc dàn nhân vật tập mới: "
            f"{n_protagonists} chính + {n_supporting} phụ"
        )

        protagonists = [
            self.mint_character(role="Protagonist")
            for _ in range(n_protagonists)
        ]
        supporting = [
            self.mint_character(role="Supporting")
            for _ in range(n_supporting)
        ]

        logger.info(
            f"[CharacterFactory] 🎭 Dàn nhân vật sẵn sàng: "
            + ", ".join(f"{c['name']}({c['blueprint_id']})" for c in protagonists + supporting)
        )
        return {"protagonists": protagonists, "supporting_cast": supporting}

    # ── Gọi A0 inline ─────────────────────────────────────────────────────────

    def _request_visual_from_a0(self, char_data: dict) -> dict:
        """Chuyển nhân vật thô đến A0 để vẽ và khóa ngoại hình ngay lập tức.

        Trả về char_data đã được cập nhật visual_prompt_en + visual_locked=True.
        """
        from creative.a0_character_artist import A0CharacterArtist

        artist = A0CharacterArtist()
        return artist.draw_and_lock_single(char_data)
