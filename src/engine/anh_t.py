"""Trạm "Anh T" — V4.0.

Hoạt động trên **SKELETON** (khung kịch bản) chứ không phải script chi tiết:
- TF-IDF + cosine so sánh tag-document của 3 khung mới với 50 khung gần nhất
  trong Mongo (``episodes_50``). Vượt threshold => duplicate.
- Cơ chế ÉP ĐỘT BIẾN: nếu sau ``anh_t_max_dup_retries`` lần Monte Carlo vẫn
  không đủ 3 khung khác biệt, "Anh T" sẽ bốc cực đoan 1 ``hidden_item`` + 1
  ``destiny_dice`` rồi gọi Monte Carlo BÙ với ``forced_injection``.
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List, Dict, Any, Callable
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ..config import settings
from ..utils import get_logger

log = get_logger("anh_t")

_ROOT = Path(__file__).resolve().parents[2]
_HIDDEN_ITEMS = _ROOT / "data" / "secrets" / "hidden_items.json"
_DESTINY_DICE = _ROOT / "data" / "destiny_dice.json"
_HISTORY_DIR  = Path("history")


# ---------- Tài liệu hoá skeleton để TF-IDF ----------

def _skeleton_to_tagdoc(sk: Any) -> str:
    """``sk`` có thể là list[SkeletonScene] hoặc list[dict] (đã serialize)."""
    tags: List[str] = []
    for sc in (sk or []):
        if hasattr(sc, "tags"):
            tags += [str(t) for t in (sc.tags or [])]
            if getattr(sc, "actor", None):  tags.append(sc.actor)
            if getattr(sc, "target", None): tags.append(sc.target)
            if getattr(sc, "beat", None):   tags.append(sc.beat)
        elif isinstance(sc, dict):
            tags += [str(t) for t in (sc.get("tags") or [])]
            for k in ("actor", "target", "beat"):
                if sc.get(k): tags.append(str(sc[k]))
    return " ".join(t for t in tags if t)


def _load_history_docs() -> List[str]:
    docs: List[str] = []
    try:
        from ..storage import mongo
        for item in mongo.list_canon_recent(limit=50):
            scr = item.get("script") or {}
            sk = scr.get("skeleton") or scr.get("scenes") or []
            docs.append(_skeleton_to_tagdoc(sk))
    except Exception as e:
        log.warning("History Mongo NO3 fail: %s — fallback file.", e)
    if not docs and _HISTORY_DIR.exists():
        for f in sorted(_HISTORY_DIR.glob("*.json"))[-50:]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                docs.append(_skeleton_to_tagdoc(data.get("skeleton") or data.get("scenes") or []))
            except Exception:
                pass
    return [d for d in docs if d.strip()]


# ---------- Dedup 1 skeleton ----------

def _is_duplicate_doc(candidate: str, history: List[str]) -> tuple[bool, float]:
    if not history or not candidate.strip():
        return False, 0.0
    try:
        vec = TfidfVectorizer().fit(history + [candidate])
        mat = vec.transform(history + [candidate])
        sims = cosine_similarity(mat[-1], mat[:-1])[0]
        peak = float(sims.max())
    except ValueError:
        return False, 0.0
    return peak >= settings.anh_t_dup_threshold, peak


# ---------- Cơ chế ép đột biến ----------

def _pick_extreme_injection() -> Dict[str, Any]:
    """Bốc 1 hidden_item + 1 destiny_dice. Fallback nội bộ nếu file thiếu."""
    item = {"name": "Bằng chứng bị niêm phong",
            "description": "Một USB chứa bí mật quá khứ bất ngờ rơi vào tay nhân vật."}
    dice = {"name": "Xúc xắc Định Mệnh: ĐẢO NGÔI",
            "description": "Kẻ yếu nhất bỗng nắm quyền, cán cân quyền lực lật úp."}
    try:
        if _HIDDEN_ITEMS.exists():
            pool = json.loads(_HIDDEN_ITEMS.read_text(encoding="utf-8"))
            if pool: item = random.choice(pool)
    except Exception as e:
        log.warning("hidden_items.json fail: %s", e)
    try:
        if _DESTINY_DICE.exists():
            pool = json.loads(_DESTINY_DICE.read_text(encoding="utf-8"))
            if pool: dice = random.choice(pool)
    except Exception as e:
        log.warning("destiny_dice.json fail: %s", e)
    return {"hidden_item": item, "destiny_dice": dice}


# ---------- API chính: vet 3 skeleton ----------

def vet_skeletons(
    skeletons: List[Any],
    target_count: int,
    regen_fn: Callable[[int, Dict[str, Any]], List[Any]],
) -> List[Any]:
    """Lọc các skeleton trùng lặp. Sinh bù qua ``regen_fn`` cho đến khi đủ
    ``target_count`` khung khác biệt, hoặc đạt ngưỡng ép đột biến.

    ``regen_fn(n_needed, forced_injection_dict) -> list[skeleton]``.
    """
    history = _load_history_docs()
    kept: List[Any] = []
    seen_docs: List[str] = list(history)

    def _accept(cand: Any) -> bool:
        doc = _skeleton_to_tagdoc(cand)
        dup, peak = _is_duplicate_doc(doc, seen_docs)
        if dup:
            log.warning("anh_t DUP (peak=%.3f) — loại.", peak)
            return False
        seen_docs.append(doc)
        kept.append(cand)
        log.info("anh_t PASS (peak=%.3f). %d/%d.", peak, len(kept), target_count)
        return True

    for c in skeletons:
        if len(kept) >= target_count: break
        _accept(c)

    attempts = 0
    while len(kept) < target_count and attempts < settings.anh_t_max_dup_retries:
        attempts += 1
        need = target_count - len(kept)
        log.warning("anh_t thiếu %d — Monte Carlo sinh bù lần %d.", need, attempts)
        new_batch = regen_fn(need, {})
        for c in new_batch:
            if len(kept) >= target_count: break
            _accept(c)

    if len(kept) < target_count:
        injection = _pick_extreme_injection()
        log.warning("anh_t ÉP ĐỘT BIẾN: %s + %s",
                    injection["hidden_item"].get("name"),
                    injection["destiny_dice"].get("name"))
        forced_batch = regen_fn(target_count - len(kept), injection)
        for c in forced_batch:
            if len(kept) >= target_count: break
            # ép-đột-biến: chấp nhận luôn (cuối cùng), nhưng vẫn ưu tiên non-dup
            doc = _skeleton_to_tagdoc(c)
            dup, _ = _is_duplicate_doc(doc, seen_docs)
            if dup and len(kept) + (len(forced_batch) - forced_batch.index(c)) > target_count:
                continue
            seen_docs.append(doc); kept.append(c)

    return kept[:target_count]


# ---------- Backwards-compat: vet 1 script chi tiết (giữ cho code cũ) ----------

def is_duplicate(script: dict) -> tuple[bool, float]:
    cand = _skeleton_to_tagdoc(script.get("skeleton") or script.get("scenes") or [])
    return _is_duplicate_doc(cand, _load_history_docs())


def vet_script(script: dict, budget, regen_fn) -> dict:
    dup, peak = is_duplicate(script)
    if not dup:
        log.info("anh_t (script-level) PASS (sim=%.3f)", peak)
        return script
    log.warning("anh_t (script-level) DUP (peak=%.3f) — gọi regen 1 lần.", peak)
    try: budget.consume("duplicate")
    except Exception: pass
    return regen_fn("Bẻ lái kịch bản theo hướng mới hoàn toàn.")
