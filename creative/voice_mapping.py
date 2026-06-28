"""Map tên nhân vật → ElevenLabs Voice ID.

Thứ tự ưu tiên:
  1. Cache trong phiên (tránh truy vấn DB lặp lại).
  2. MongoDB permanent.voice_mapping (giọng đã gán ở tập trước → nhất quán xuyên suốt series).
  3. Khớp archetype_name với voice_pool trong database_seeds/voice_mapping.json.
  4. Fallback theo giới tính (male / female) từ seed.

FIX R5: Trước đây build_mapping chỉ nhận list[str] tên nhân vật nên không có
  archetype_name / gender để khớp → luôn rơi vào DEFAULT_VOICE_POOL premade chung.
  Nay nhận list[dict] nhân vật đầy đủ (hoặc tương thích ngược với list[str]).
"""
import json
import logging
from pathlib import Path

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

_SEED_PATH = Path("database_seeds/voice_mapping.json")


def _load_voice_seed() -> dict:
    """Đọc voice_pool + fallback_voice từ file seed."""
    try:
        if _SEED_PATH.exists():
            with open(_SEED_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[VoiceMapper] Không đọc được voice seed ({_SEED_PATH}): {e}")
    # Giá trị mặc định an toàn nếu seed không tồn tại
    return {
        "voice_pool": [],
        "fallback_voice": {"male": "premade/Adam", "female": "premade/Elli"},
    }


class VoiceMapper:
    def __init__(self):
        self.db = ChimeraDB()
        self._cache: dict[str, str] = {}
        self._seed = _load_voice_seed()

    # ── Helpers nội bộ ───────────────────────────────────────────────────────

    def _match_by_archetype(self, archetype_name: str) -> str | None:
        """Tìm voice_id đầu tiên trong voice_pool có archetype_match nằm trong archetype_name."""
        for entry in self._seed.get("voice_pool", []):
            match_key = entry.get("archetype_match", "")
            if match_key and match_key in archetype_name:
                logger.debug(
                    f"[VoiceMapper] Archetype match: '{match_key}' → {entry['voice_id']}"
                )
                return entry["voice_id"]
        return None

    def _fallback_by_gender(self, gender: str) -> str:
        """Giọng dự phòng theo giới tính từ seed (male / female)."""
        fb = self._seed.get("fallback_voice", {})
        if str(gender).upper() == "F":
            return fb.get("female", "premade/Elli")
        return fb.get("male", "premade/Adam")

    # ── API công khai ────────────────────────────────────────────────────────

    def get_voice_for_character(self, character_data: dict) -> str:
        """Trả về voice_id cho nhân vật theo thứ tự ưu tiên đã mô tả ở module docstring.

        Args:
            character_data: Dict nhân vật với các khoá hữu ích:
                - name          (str)  bắt buộc
                - archetype_name (str) để khớp voice_pool
                - gender        (str)  "M" | "F" để fallback
        """
        character_name = character_data.get("name", "")
        if not character_name:
            # Không có tên → trả fallback theo giới tính ngay
            return self._fallback_by_gender(character_data.get("gender", "M"))

        # 1. Cache trong phiên
        if character_name in self._cache:
            return self._cache[character_name]

        # 2. MongoDB (giọng đã gán từ tập trước)
        doc = None
        try:
            doc = self.db.permanent.voice_mapping.find_one({"character": character_name})
        except Exception as e:
            logger.warning(f"[VoiceMapper] Không đọc được DB cho '{character_name}': {e}")

        if doc and doc.get("voice_id"):
            voice_id = doc["voice_id"]
            logger.debug(f"[VoiceMapper] '{character_name}' → DB: {voice_id}")
        else:
            archetype_name = character_data.get("archetype_name", "")
            gender = character_data.get("gender", "M")

            # 3. Khớp archetype từ voice_pool seed
            voice_id = self._match_by_archetype(archetype_name)

            if voice_id:
                logger.info(
                    f"[VoiceMapper] '{character_name}' khớp archetype "
                    f"'{archetype_name[:40]}' → {voice_id}"
                )
            else:
                # 4. Fallback theo giới tính
                voice_id = self._fallback_by_gender(gender)
                logger.info(
                    f"[VoiceMapper] '{character_name}' không khớp archetype nào "
                    f"→ fallback gender='{gender}': {voice_id}"
                )

            # Lưu vào MongoDB để các tập sau dùng lại (giữ giọng nhất quán)
            try:
                self.db.permanent.voice_mapping.update_one(
                    {"character": character_name},
                    {"$set": {
                        "character": character_name,
                        "voice_id": voice_id,
                        "archetype_name": archetype_name,
                        "gender": gender,
                    }},
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"[VoiceMapper] Không lưu được voice mapping cho '{character_name}': {e}")

        self._cache[character_name] = voice_id
        return voice_id

    def build_mapping(self, characters: list) -> dict:
        """Xây dựng bảng {tên → voice_id} cho danh sách nhân vật.

        Args:
            characters: list[dict]  ← định dạng ưu tiên (có name, archetype_name, gender)
                        list[str]   ← tương thích ngược (chỉ có tên, không khớp archetype)
        """
        mapping: dict[str, str] = {}
        for item in characters:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name:
                    mapping[name] = self.get_voice_for_character(item)
            elif isinstance(item, str) and item:
                # Tương thích ngược: chỉ có tên → không có archetype, dùng fallback
                mapping[item] = self.get_voice_for_character({"name": item})
        return mapping
