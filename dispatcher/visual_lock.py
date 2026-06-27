"""Quan ly visual_lock_seed + visual_prompt_en da khoa cho tung nhan vat
(giu nhat quan ngoai hinh giua cac scene)."""
import logging
import hashlib

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# Fallback khi nhan vat chua duoc A0 khoa hinh (vi du: nhan vat dam dong/vo danh)
FALLBACK_VISUAL_PROMPT = "an unnamed Vietnamese person"


class VisualLockManager:
    def __init__(self):
        self.db = ChimeraDB()
        self._cache = {}
        # Cache rieng cho visual_prompt_en, tranh nham voi cache seed
        self._prompt_cache = {}

    def get_seed_for_character(self, character_name: str) -> int:
        """Lay seed on dinh cho nhan vat (deterministic)."""
        if character_name in self._cache:
            return self._cache[character_name]

        seed = None
        try:
            doc = self.db.permanent.visual_locks.find_one(
                {"character": character_name}
            )
            if doc and doc.get("seed") is not None:
                seed = int(doc["seed"])
        except Exception as e:
            logger.warning(f"[VisualLock] Khong doc duoc DB: {e}")

        if seed is None:
            digest = hashlib.sha256(character_name.encode("utf-8")).hexdigest()
            seed = int(digest[:8], 16)
            try:
                self.db.permanent.visual_locks.update_one(
                    {"character": character_name},
                    {"$set": {"seed": seed}},
                    upsert=True,
                )
            except Exception:
                pass

        self._cache[character_name] = seed
        return seed

    def get_visual_prompt_for_character(self, character_name: str) -> str:
        """Lay visual_prompt_en DA KHOA boi A0 cho nhan vat (theo ten).

        Day la "the chung minh nhan dan bang chu" cua nhan vat: mo ta khuon
        mat, kieu toc, trang phuc... da duoc A0 chot 1 lan va luu trong
        character_states.visual_prompt_en. A2 dung lai nguyen van prompt nay
        de ghep vao tung scene, dam bao nhan vat khong bi doi mat/do khac
        nhau giua cac canh.

        Fallback: neu chua tim thay (nhan vat moi/dam dong vo danh), tra ve
        FALLBACK_VISUAL_PROMPT va log WARNING ro rang de biet ma dang thieu
        khoa hinh thay vi am tham bo qua.
        """
        if character_name in self._prompt_cache:
            return self._prompt_cache[character_name]

        prompt = None
        try:
            doc = self.db.permanent.character_states.find_one(
                {"name": character_name, "visual_locked": True},
                {"visual_prompt_en": 1},
            )
            if doc and doc.get("visual_prompt_en"):
                prompt = doc["visual_prompt_en"]
        except Exception as e:
            logger.warning(
                f"[VisualLock] Khong doc duoc visual_prompt_en cho "
                f"'{character_name}': {e}"
            )

        if not prompt:
            logger.warning(
                f"[VisualLock] '{character_name}' CHUA CO visual_prompt_en "
                f"da khoa (A0 chua xu ly hoac la nhan vat vo danh). "
                f"Dung fallback: '{FALLBACK_VISUAL_PROMPT}'"
            )
            prompt = FALLBACK_VISUAL_PROMPT

        self._prompt_cache[character_name] = prompt
        return prompt

    def get_scene_seed(self, characters) -> int:
        """Seed dac trung cho scene dua tren nhan vat dau tien."""
        if not characters:
            return 0
        return self.get_seed_for_character(characters[0])
