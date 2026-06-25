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
        # FIX #6: Nguong "tuyet doi tu choi" - neu fallback draft van cao hon
        # nguong nay, tra ve status dac biet de caller biet phai retry.
        self.hard_reject_threshold = settings.SIMILARITY_HARD_REJECT_THRESHOLD
        # FIX #11: max_retry duoc dung trong audit() de quyet dinh status
        # "should_retry" vs "needs_review", giup caller (main_creative_pipeline)
        # biet co nen goi lai A1 hay khong.
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
        """Kiem duyet danh sach drafts. Tra ve draft pass dau tien.

        Return dict co cac fields:
          - status: "approved" | "needs_review" | "should_retry" | "rejected"
          - draft:  draft object hoac None
          - similarity: float hoac None
          - reason: mo ta ly do (cho needs_review/should_retry/rejected)

        FIX #11: Phan biet ro "needs_review" (co the duyet duoc) va
        "should_retry" (similarity qua cao, nen goi lai A1 truoc).
        Caller (main_creative_pipeline) dung max_retry de quyet dinh
        co retry hay gui thang len Showrunner.
        """
        self.refresh_embeddings_if_needed()

        passed_mandatory = []
        failed_mandatory = []

        for draft in drafts:
            # 1. Kiem tra mandatory tasks
            resolved = set(draft.get("resolved_hooks", []))
            missing = set(mandatory_tasks) - resolved
            if missing:
                logger.warning(
                    f"[Auditor] Draft {draft.get('draft_id')} thieu mandatory: {missing}"
                )
                failed_mandatory.append(draft)
                continue
            passed_mandatory.append(draft)

        # Neu khong co draft nao pass mandatory -> rejected hoan toan
        if not passed_mandatory:
            logger.error(
                f"[Auditor] Tat ca {len(drafts)} drafts deu thieu mandatory tasks. "
                f"A1 can duoc retry voi prompt nhan manh hon."
            )
            return {
                "status": "rejected",
                "draft": None,
                "similarity": None,
                "reason": f"Tat ca drafts thieu mandatory tasks: {list(set(mandatory_tasks))}",
            }

        # 2. Kiem tra trung lap cho cac draft da pass mandatory
        scored = []
        for draft in passed_mandatory:
            full_text = _serialize_draft(draft)
            max_sim, similar_text = self.check_similarity(full_text)
            draft["similarity_score"] = max_sim

            if max_sim <= self.threshold:
                logger.info(
                    f"[Auditor] Draft {draft.get('draft_id')} PASS "
                    f"(sim={max_sim:.3f} <= threshold={self.threshold:.3f})"
                )
                return {
                    "status": "approved",
                    "draft": draft,
                    "similarity": max_sim,
                    "reason": "ok",
                }

            scored.append((max_sim, draft, similar_text))

        # Fallback: tat ca drafts deu vuot nguong similarity
        scored.sort(key=lambda x: x[0])
        best_sim, best_draft, similar_text = scored[0]

        # FIX #6 + #11: Phan biet muc do nghiem trong de caller xu ly dung.
        # - should_retry: similarity > hard_reject_threshold -> A1 can viet lai hoan toan
        # - needs_review: threshold < sim <= hard_reject -> Showrunner co the tha thu
        if best_sim > self.hard_reject_threshold:
            logger.critical(
                f"[Auditor] Fallback draft co similarity={best_sim:.3f} "
                f"VUOT NGUONG CUNG ({self.hard_reject_threshold:.3f}). "
                f"Nen retry A1 (con {self.max_retry} lan). "
                f"Tuong tu voi: '{similar_text[:100]}...'"
            )
            return {
                "status": "should_retry",
                "draft": best_draft,
                "similarity": best_sim,
                "reason": (
                    f"Similarity {best_sim:.3f} > hard_reject={self.hard_reject_threshold:.3f}. "
                    f"Noi dung qua giong tap cu."
                ),
            }

        # Similarity vuot threshold nhung chua den muc cung -> gui Showrunner quyet
        logger.warning(
            f"[Auditor] Fallback: tra ve draft it trung nhat "
            f"(sim={best_sim:.3f}) de Showrunner quyet dinh."
        )
        return {
            "status": "needs_review",
            "draft": best_draft,
            "similarity": best_sim,
            "reason": (
                f"Similarity {best_sim:.3f} > threshold={self.threshold:.3f} "
                f"nhung < hard_reject={self.hard_reject_threshold:.3f}."
            ),
        }
