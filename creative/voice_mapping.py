"""Map ten nhan vat -> ElevenLabs Voice ID."""
import logging

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

DEFAULT_VOICE_POOL = [
    "premade/Adam",
    "premade/Elli",
    "premade/Josh",
    "premade/Rachel",
    "premade/Antoni",
]


class VoiceMapper:
    def __init__(self):
        self.db = ChimeraDB()
        self._cache = {}

    def get_voice_for_character(self, character_name: str) -> str:
        """Lay voice_id da gan cho nhan vat, hoac gan moi tu pool."""
        if character_name in self._cache:
            return self._cache[character_name]

        doc = None
        try:
            doc = self.db.permanent.voice_mapping.find_one(
                {"character": character_name}
            )
        except Exception as e:
            logger.warning(f"[VoiceMapper] Khong doc duoc DB: {e}")

        if doc and doc.get("voice_id"):
            voice_id = doc["voice_id"]
        else:
            idx = len(self._cache) % len(DEFAULT_VOICE_POOL)
            voice_id = DEFAULT_VOICE_POOL[idx]
            try:
                self.db.permanent.voice_mapping.update_one(
                    {"character": character_name},
                    {"$set": {"voice_id": voice_id}},
                    upsert=True,
                )
            except Exception:
                pass

        self._cache[character_name] = voice_id
        return voice_id

    def build_mapping(self, character_names) -> dict:
        return {name: self.get_voice_for_character(name) for name in character_names}
