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

    def handle_rewrite_extreme(self, master_payload: dict):
        """Bom noi tam cuc doan va viet lai."""
        logger.warning("[PostApproval] Bom noi tam cuc doan va viet lai")
        # TODO: Goi T0a de bom noi tam cuc doan vao Master_Payload,
        # sau do goi lai alchemist + auditor.
        return master_payload
