"""Xu ly sau khi Showrunner duyet (Va M-09)."""
import logging
from datetime import datetime

from core.db_client import ChimeraDB
from core.helpers import _generate_summary
from simulator.t0i_world_state import WorldStateSimulator

logger = logging.getLogger(__name__)


class PostApprovalHandler:
    """Xu ly sau khi duyet:
    1. Goi Ban 1 (T0i) de cap nhat World State.
    2. Luu script vao Cum 3 (Canon).
    3. Xoa khoi Cum 2 (Purgatory).
    """

    def __init__(self):
        self.db = ChimeraDB()
        self.simulator = WorldStateSimulator(self.db)

    def process_approval(self, master_script: dict) -> bool:
        try:
            episode_number = master_script["meta"]["episode_number"]
            deltas = master_script.get("world_state_deltas", [])

            # 1. Cap nhat World State (Va M-09)
            self.simulator.apply_episode_events(episode_number, deltas)

            # 2. Luu vao Canon
            self._save_to_canon(master_script)

            # 3. Don Purgatory
            self._cleanup_purgatory(episode_number)

            logger.info(f"[PostApproval] Hoan tat episode {episode_number}")
            return True
        except Exception as e:
            logger.critical(f"[PostApproval] Loi: {e}")
            return False

    def _save_to_canon(self, script: dict):
        """Luu kich ban + summary + embedding vao Cum 3."""
        episode_number = script["meta"]["episode_number"]
        summary = _generate_summary(script)

        self.db.canon.episode_summaries.update_one(
            {"episode_number": episode_number},
            {"$set": {
                "episode_number": episode_number,
                "summary": summary,
                "approved_at": datetime.utcnow().isoformat() + "Z",
            }},
            upsert=True,
        )

        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model.encode([summary])[0].tolist()
            self.db.canon.episode_embeddings.update_one(
                {"episode_number": episode_number},
                {"$set": {
                    "episode_number": episode_number,
                    "summary": summary,
                    "embedding": embedding,
                }},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"[PostApproval] Khong sinh duoc embedding: {e}")

    def _cleanup_purgatory(self, episode_number: int):
        try:
            self.db.purgatory.draft_scripts.delete_many(
                {"episode_number": episode_number}
            )
        except Exception as e:
            logger.warning(f"[PostApproval] Khong don duoc Purgatory: {e}")

    def handle_rewrite_extreme(self, master_payload: dict) -> dict:
        """Bơm nội tâm cực đoan vào từng nhân vật rồi trả payload cho Stage 2 chạy lại.

        Chiến lược:
        1. Lấy toàn bộ inner_conflict_pool từ blueprint của mỗi nhân vật (thay vì 1-3 mục).
        2. Đẩy các stat "độc hại" (narcissism, manipulation, betrayal_tendency, greed) lên 100.
        3. Đánh dấu nhân vật extreme_mode=True và thêm rewrite_extreme_warning vào payload
           để A1 biết cần viết kịch bản khốc liệt nhất có thể.
        """
        logger.warning("[PostApproval] ⚡ REWRITE_EXTREME — bắt đầu bơm nội tâm cực đoan")

        _TOXIC_STATS = {"narcissism", "manipulation", "betrayal_tendency", "greed"}

        all_characters = (
            master_payload.get("protagonists", []) +
            master_payload.get("supporting_cast", [])
        )

        for char in all_characters:
            char_name = char.get("name", "unknown")

            # ── 1. Bơm toàn bộ inner_conflict_pool từ blueprint ──────────────
            bp_id = char.get("blueprint_id", "")
            if bp_id:
                try:
                    bp_doc = self.db.permanent.character_blueprints.find_one(
                        {"blueprint_id": bp_id}, {"inner_conflict_pool": 1}
                    )
                    if bp_doc and bp_doc.get("inner_conflict_pool"):
                        full_pool = bp_doc["inner_conflict_pool"]
                        char["inner_conflicts"] = full_pool
                        logger.info(
                            f"[PostApproval] {char_name}: "
                            f"bơm {len(full_pool)} inner_conflicts từ {bp_id}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[PostApproval] Không đọc được blueprint {bp_id} "
                        f"cho '{char_name}': {e}"
                    )

            # ── 2. Boost các stat độc hại lên 100 ───────────────────────────
            stats = char.get("stats", {})
            boosted = []
            for category, stat_dict in stats.items():
                for stat_name in list(stat_dict.keys()):
                    if stat_name in _TOXIC_STATS:
                        stat_dict[stat_name] = 100
                        boosted.append(stat_name)
            char["stats"] = stats
            if boosted:
                logger.info(
                    f"[PostApproval] {char_name}: boost stats → "
                    + ", ".join(f"{s}=100" for s in boosted)
                )

            # ── 3. Đánh dấu cờ cực đoan ─────────────────────────────────────
            char["extreme_mode"] = True

        # Gắn cảnh báo vào payload để A1 prompt_template nhận ra
        master_payload["rewrite_extreme"] = True
        master_payload["rewrite_extreme_warning"] = (
            "REWRITE CỰC ĐOAN: Nội tâm nhân vật đã bị đẩy lên mức tối đa. "
            "Viết kịch bản drama khốc liệt nhất có thể — không che giấu, "
            "không tiết chế, mọi bí mật sâu nhất bị bộc lộ, mọi mâu thuẫn "
            "nổ bùng trực tiếp."
        )

        logger.info(
            f"[PostApproval] ✅ REWRITE_EXTREME hoàn tất: "
            f"{len(all_characters)} nhân vật đã được bơm nội tâm cực đoan."
        )
        return master_payload
