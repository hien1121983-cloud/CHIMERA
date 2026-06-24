"""T2.3 — T-Checker (Vá #1).

Trạm kiểm tra "độ mòn" của skeleton trước khi đẩy lên T3 (LLM lõi).
Re-run T2 (Monte Carlo) rẻ hơn re-run T3 ~10×, nên gate ở đây.

Logic:
  1. extract_tags(skeleton)  — tag sự kiện/macguffin/archetype
  2. tfidf_compare vs 50 tập history
  3. similarity > repetition_threshold  → FAIL/repetition  → suggest "inject_macguffin"
     similarity < novelty_threshold     → FAIL/novelty     → suggest "inject_callback_to_past"
     ngược lại                          → PASS

Hết budget retry → force PASS + inject macguffin.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from ..config import settings
from ..utils import get_logger

log = get_logger("t_checker")


@dataclass
class ValidationResult:
    status: str               # "PASS" | "FAIL"
    reason: str = ""
    suggestion: str = ""      # "inject_macguffin" | "inject_callback_to_past" | ""
    similarity: float = 0.0


# --------------------------------------------------------------------
# Tag extraction
# --------------------------------------------------------------------
_KEYWORDS = (
    "đòi nợ", "sổ đỏ", "phản bội", "trả thù", "chia tay", "kết hôn",
    "bí mật", "lừa đảo", "ám sát", "tu luyện", "đột phá", "phi thăng",
    "ly hôn", "macguffin", "ngộ độc", "thanh trừng", "lừa tình",
    "công an", "ngân hàng", "linh thạch", "tiền vàng",
)


def extract_tags(skeleton) -> List[str]:
    """Lấy tag từ skeleton (dict|list|str). Robust với mọi shape."""
    if skeleton is None:
        return []
    if isinstance(skeleton, str):
        text = skeleton.lower()
    elif isinstance(skeleton, dict):
        text = " ".join(str(v) for v in skeleton.values()).lower()
    elif isinstance(skeleton, Iterable):
        parts = []
        for ev in skeleton:
            if isinstance(ev, dict):
                parts.append(" ".join(str(v) for v in ev.values()))
            else:
                parts.append(str(ev))
        text = " ".join(parts).lower()
    else:
        text = str(skeleton).lower()

    tags = [kw for kw in _KEYWORDS if kw in text]
    # Bổ sung 5 token dài nhất để tạo signature đa dạng hơn
    long_tokens = sorted({t for t in text.split() if len(t) > 6}, key=len, reverse=True)[:5]
    return tags + long_tokens


# --------------------------------------------------------------------
# TF-IDF compare
# --------------------------------------------------------------------
def tfidf_max_similarity(query_tags: Sequence[str], history_tag_lists: Sequence[Sequence[str]]) -> float:
    if not query_tags or not history_tag_lists:
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception as e:  # pragma: no cover
        log.warning("sklearn unavailable: %s — skip t-checker", e)
        return 0.0

    docs = [" ".join(query_tags)] + [" ".join(h) for h in history_tag_lists if h]
    if len(docs) < 2:
        return 0.0
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    matrix = vec.fit_transform(docs)
    sims = cosine_similarity(matrix[0:1], matrix[1:])
    return float(sims.max()) if sims.size else 0.0


# --------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------
def validate_skeleton(skeleton, history_episodes: Sequence[dict]) -> ValidationResult:
    """history_episodes: list các canon doc (mỗi doc có 'script' hoặc 'tags')."""
    tags = extract_tags(skeleton)
    history_tags = []
    for ep in history_episodes[: settings.t_checker_history_window]:
        if "tags" in ep and ep["tags"]:
            history_tags.append(list(ep["tags"]))
        else:
            history_tags.append(extract_tags(ep.get("script") or ep))

    sim = tfidf_max_similarity(tags, history_tags)
    log.info("T-Checker similarity=%.3f tags=%d hist=%d", sim, len(tags), len(history_tags))

    if sim > settings.t_checker_repetition_threshold:
        return ValidationResult(
            status="FAIL",
            reason=f"QUÁ GIỐNG tập trước (similarity={sim:.2f})",
            suggestion="inject_macguffin",
            similarity=sim,
        )
    if history_tags and sim < settings.t_checker_novelty_threshold:
        return ValidationResult(
            status="FAIL",
            reason=f"QUÁ LẠ, khán giả mất phương hướng (similarity={sim:.2f})",
            suggestion="inject_callback_to_past",
            similarity=sim,
        )
    return ValidationResult(status="PASS", similarity=sim)


def gate(skeleton, history_episodes: Sequence[dict], budget) -> ValidationResult:
    """Vòng lặp gate với BudgetManager. Trả ValidationResult cuối cùng (luôn PASS sau khi hết retry)."""
    result = validate_skeleton(skeleton, history_episodes)
    while result.status == "FAIL":
        if not budget.request_retry("T2_3_t_checker"):
            log.warning("Hết retry T2.3 → force PASS với suggestion=%s", result.suggestion)
            return ValidationResult(status="PASS", reason="force_pass", suggestion=result.suggestion,
                                    similarity=result.similarity)
        # Caller chịu trách nhiệm re-roll skeleton & gọi lại; trả về result để caller xử lý.
        return result
    return result