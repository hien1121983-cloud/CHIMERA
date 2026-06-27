"""Trạm A0: Vẽ và World-Lock ngoại hình nhân vật (Gemini prompt → MongoDB Python thuần).

Hai chế độ:
  1. draw_and_lock_single(char_data)  — được gọi inline từ CharacterFactory
     (T0a đúc xong → gọi ngay, nhân vật chưa vào DB).
  2. process_payload_characters(payload) — legacy batch scan (vẫn giữ để
     đảm bảo backward-compat với mọi nhân vật sót lại chưa có visual_locked).

Nguyên tắc:
  - A0 CHỈ làm 1 việc: sáng tạo visual_prompt_en (tiếng Anh ≤ 30 từ).
  - Mọi thao tác ghi DB đều là Python thuần (không LLM).
  - LLM chỉ trả lời câu hỏi: "Nhân vật này trông như thế nào?"
"""
import json
import logging
from pydantic import BaseModel, Field

from core.db_client import ChimeraDB
from core.credential_manager import GEMINI_POOL

logger = logging.getLogger(__name__)


class A0VisualOutput(BaseModel):
    visual_prompt_en: str = Field(
        description=(
            "Miêu tả ngoại hình nhân vật bằng tiếng Anh dành cho AI tạo ảnh. "
            "Tối đa 30 từ. Tập trung: khuôn mặt, độ tuổi, kiểu tóc, trang phục đặc trưng. "
            "Bắt đầu bằng 'Vietnamese [man/woman]'. Phong cách điện ảnh."
        )
    )


class A0CharacterArtist:

    def __init__(self):
        self.db = ChimeraDB()
        self.model_name = "gemini-2.5-flash"

    # ══════════════════════════════════════════════════════════════════════════
    # CHÍNH: draw_and_lock_single — được CharacterFactory gọi inline
    # ══════════════════════════════════════════════════════════════════════════

    def draw_and_lock_single(self, char_data: dict, _attempt: int = 0) -> dict:
        """Vẽ ngoại hình cho 1 nhân vật và world-lock ngay lập tức.

        Được gọi bởi CharacterFactory ngay sau khi T0a đúc xong nhân vật thô.
        Trả về char_data đã có visual_prompt_en + visual_locked=True.

        A0 nhận đầy đủ DNA từ blueprint để vẽ nhân quả:
          - archetype_name: biết đây là "kẻ đạo đức giả" hay "kẻ cơ hội"
          - inner_conflicts: biết nỗi đau ẩn → thể hiện ra khuôn mặt
          - fatal_flaw: điểm yếu chết người → ảnh hưởng khí thái
          - micro_habits: thói quen nhỏ → chi tiết trang phục/diện mạo
          - social_class: tầng lớp xã hội → style trang phục
        """
        max_attempts = GEMINI_POOL.active_count + 1
        if _attempt >= max_attempts:
            logger.error(
                f"[A0] Tất cả Gemini key thất bại cho '{char_data.get('name')}'. "
                f"Dùng fallback visual prompt."
            )
            return self._apply_fallback(char_data)

        key = GEMINI_POOL.get_next()
        if not key:
            return self._apply_fallback(char_data)

        try:
            import google.generativeai as genai
            genai.configure(api_key=key)

            # Xây dựng context giàu hơn từ blueprint DNA
            inner_conflicts_str = "; ".join(char_data.get("inner_conflicts", []))
            micro_habits = char_data.get("micro_habits", {})
            stress_tick = micro_habits.get("stress_tick", "")
            lie_tell = micro_habits.get("lie_tell", "")

            # Lấy top stats nổi bật nhất để gợi ý ngoại hình
            stats = char_data.get("stats", {})
            notable_stats = self._get_notable_stats(stats)

            prompt = (
                f"[A0 - Họa sĩ thiết kế nhân vật]\n"
                f"Tạo visual_prompt_en (≤30 từ tiếng Anh) cho nhân vật Việt Nam:\n\n"
                f"Tên: {char_data.get('name', 'Unknown')}\n"
                f"Archetype: {char_data.get('archetype_name', '')}\n"
                f"Triết lý sống: {char_data.get('philosophy', '')}\n"
                f"Tầng lớp: {char_data.get('social_class', '')}\n"
                f"Mâu thuẫn nội tâm: {inner_conflicts_str}\n"
                f"Thói quen khi căng thẳng: {stress_tick}\n"
                f"Điểm yếu chết người: {char_data.get('fatal_flaw', '')}\n"
                f"Chỉ số nổi bật: {notable_stats}\n\n"
                f"YÊU CẦU: Ngoại hình phải PHẢN ÁNH tâm lý. "
                f"Nếu manipulation=95 → ánh mắt sắc lạnh, nụ cười tính toán. "
                f"Nếu trauma cao → vầng mắt trũng sâu. "
                f"Trả về JSON thuần với 'visual_prompt_en'.\n"
                f"Schema: {json.dumps(A0VisualOutput.model_json_schema(), ensure_ascii=False)}"
            )

            model = genai.GenerativeModel(
                self.model_name,
                system_instruction="Chỉ trả về JSON thuần túy, không markdown, không giải thích.",
            )
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.75},
            )

            data = json.loads(response.text)
            visual_prompt = A0VisualOutput(**data).visual_prompt_en

            # World-lock: ghi vào char_data (Python thuần, không LLM)
            char_data["visual_prompt_en"] = visual_prompt
            char_data["visual_locked"] = True

            logger.info(
                f"[A0] 🎨 KHÓA NGOẠI HÌNH: '{char_data.get('name')}' → "
                f"\"{visual_prompt[:60]}...\""
            )
            return char_data

        except json.JSONDecodeError as e:
            logger.error(f"[A0] JSON parse lỗi cho '{char_data.get('name')}': {e}")
            GEMINI_POOL.mark_failed(key)
            return self.draw_and_lock_single(char_data, _attempt + 1)
        except Exception as e:
            logger.error(f"[A0] Lỗi Gemini cho '{char_data.get('name')}': {e}")
            GEMINI_POOL.mark_failed(key)
            return self.draw_and_lock_single(char_data, _attempt + 1)

    # ══════════════════════════════════════════════════════════════════════════
    # LEGACY: process_payload_characters — batch scan cho nhân vật sót
    # ══════════════════════════════════════════════════════════════════════════

    def process_payload_characters(self, master_payload: dict) -> dict:
        """Scan toàn bộ payload, vẽ ngoại hình cho nhân vật chưa có visual_lock.

        Được gọi ở đầu Stage 2 như safety net — sau khi CharacterFactory đã
        mint các nhân vật chính, hàm này xử lý mọi nhân vật sót lại
        (ví dụ: NPC từ world state, nhân vật cũ từ Stage 1).
        """
        characters = []
        for key in ("protagonists", "supporting_cast"):
            characters.extend(master_payload.get(key, []))

        ctx = master_payload.get("context_slice_v2", {})
        layer2 = ctx.get("layer_2_character_states", {})
        if isinstance(layer2, dict):
            characters.extend(layer2.values())
        elif isinstance(layer2, list):
            characters.extend(layer2)

        unique_chars = {}
        for c in characters:
            if not isinstance(c, dict):
                continue
            cid = c.get("character_id") or c.get("_id") or c.get("name")
            if cid:
                unique_chars[cid] = c

        locked_count = 0
        for char_id, char_data in unique_chars.items():
            if not char_data.get("visual_locked") or not char_data.get("visual_prompt_en"):
                logger.info(
                    f"[A0][Batch] '{char_data.get('name')}' chưa có ngoại hình. Vẽ..."
                )
                updated = self.draw_and_lock_single(char_data)
                # Cập nhật DB
                self._save_lock_to_db(char_id, updated)
                locked_count += 1

        if locked_count:
            logger.info(f"[A0][Batch] Đã khóa {locked_count} nhân vật sót.")
        return master_payload

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _get_notable_stats(self, stats: dict) -> str:
        """Trích top 3 stat cao nhất và thấp nhất để gợi ý ngoại hình."""
        flat = {}
        for category, values in stats.items():
            if isinstance(values, dict):
                flat.update(values)

        if not flat:
            return "N/A"

        sorted_stats = sorted(flat.items(), key=lambda x: x[1], reverse=True)
        top = [(k, v) for k, v in sorted_stats[:3]]
        bottom = [(k, v) for k, v in sorted_stats[-2:] if v < 30]

        parts = [f"{k}={v}" for k, v in top]
        if bottom:
            parts += [f"{k}={v}(low)" for k, v in bottom]
        return ", ".join(parts)

    def _apply_fallback(self, char_data: dict) -> dict:
        """Fallback visual prompt khi Gemini thất bại hoàn toàn."""
        name = char_data.get("name", "Unknown")
        archetype = char_data.get("archetype_name", "")
        social_class = char_data.get("social_class", "")
        gender_word = "man" if char_data.get("gender", "M") == "M" else "woman"

        fallback = (
            f"Vietnamese {gender_word}, {social_class.lower() or 'middle-aged'}, "
            f"cinematic portrait, sharp eyes, 8k, dramatic lighting, 9:16"
        )
        char_data["visual_prompt_en"] = fallback
        char_data["visual_locked"] = True
        logger.warning(f"[A0] Fallback visual prompt cho '{name}': {fallback}")
        return char_data

    def _save_lock_to_db(self, char_id: str, char_data: dict):
        """Lưu visual lock vào MongoDB (Python thuần)."""
        try:
            self.db.permanent.character_states.update_one(
                {"character_id": char_id},
                {"$set": {
                    "visual_prompt_en": char_data.get("visual_prompt_en", ""),
                    "visual_locked": True,
                }},
                upsert=False,
            )
        except Exception as e:
            logger.error(f"[A0] Lỗi ghi DB cho {char_id}: {e}")
