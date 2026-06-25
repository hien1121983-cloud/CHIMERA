"""Tram T3 Auditor (Va M-03): kiem duyet bang Cosine Similarity."""
import logging

from core.db_client import ChimeraDB
from core.helpers import _serialize_draft
from config.settings import settings
from audit.vector_cache import VectorCache

logger = logging.getLogger(__name__)


class T3Auditor:
    """Tram T3: Kiem duyet kich ban bang Vector Similarity. KHONG dung LLM."""

    def __init__(self):
        self.db = ChimeraDB()
        self.threshold = settings.SIMILARITY_THRESHOLD
        self.max_retry = settings.AUDITOR_MAX_RETRY
        self.cache = VectorCache()
        self._model = None
        self._last_loaded_episode = -1

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def _get_latest_canon_episode(self) -> int:
        latest = self.db.canon.episode_summaries.find_one(
            sort=[("episode_number", -1)]
        )
        return latest["episode_number"] if latest else 0

    def refresh_embeddings_if_needed(self):
        """Va M-03: Refresh embeddings neu co tap moi duoc duyet."""
        current_latest = self._get_latest_canon_episode()
        if current_latest > self._last_loaded_episode:
            logger.info(
                f"[Auditor] Refresh embeddings: "
                f"{self._last_loaded_episode} -> {current_latest}"
            )
            self.cache.load_recent()
            self._last_loaded_episode = current_latest

    def check_similarity(self, text: str):
        """Tra ve (max_similarity, similar_text)."""
        import numpy as np

        if not self.cache.embeddings:
            return 0.0, ""

        new_vec = self.model.encode([text])[0]
        old = np.array(self.cache.embeddings)
        new = np.array(new_vec)

        dots = old @ new
        norms = (np.linalg.norm(old, axis=1) * np.linalg.norm(new)) + 1e-8
        sims = dots / norms
        idx = int(np.argmax(sims))
        return float(sims[idx]), self.cache.texts[idx] if self.cache.texts else ""

    def audit(self, drafts: list, mandatory_tasks: list) -> dict:
        """Kiem duyet danh sach drafts. Tra ve draft pass dau tien."""
        self.refresh_embeddings_if_needed()

        scored = []
        for draft in drafts:
            # 1. Kiem tra mandatory tasks
            resolved = set(draft.get("resolved_hooks", []))
            missing = set(mandatory_tasks) - resolved
            if missing:
                logger.warning(
                    f"[Auditor] Draft {draft.get('draft_id')} thieu mandatory: {missing}"
                )
                continue

            # 2. Kiem tra trung lap
            full_text = _serialize_draft(draft)
            max_sim, similar_text = self.check_similarity(full_text)
            draft["similarity_score"] = max_sim

            if max_sim <= self.threshold:
                logger.info(
                    f"[Auditor] Draft {draft.get('draft_id')} PASS "
                    f"(sim={max_sim:.3f})"
                )
                return {"status": "approved", "draft": draft, "similarity": max_sim}

            scored.append((max_sim, draft))

        # Fallback cuoi cung: tra ve draft co similarity thap nhat
        if scored:
            scored.sort(key=lambda x: x[0])
            logger.critical(
                "[Auditor] Het retry. Tra ve draft it trung nhat de Showrunner quyet dinh."
            )
            return {
                "status": "needs_review",
                "draft": scored[0][1],
                "similarity": scored[0][0],
            }

        return {"status": "rejected", "draft": None, "similarity": None}
