"""Trạm kiểm duyệt "Anh T" — chống trùng lặp.

- So khớp trên TAGS bằng TF-IDF + cosine, không so văn bản thô.
- Đối chiếu với history/ (50 tập gần nhất).
- Vượt threshold => duplicate. Quá 3 lần dup trong 1 tập => ép macguffin vào prompt và bắt LLM viết lại.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ..config import settings
from ..utils import get_logger

log = get_logger("anh_t")

HISTORY_DIR = Path("history")
MACGUFFIN_PATH = Path("data/macguffin_events.json")


def _script_to_tag_doc(script: dict) -> str:
    """Tạo 1 document chỉ chứa tags + emotion để vector hóa."""
    tags: List[str] = [script.get("emotion_tag", "")]
    for s in script.get("scenes", []):
        tags += list(s.get("tags", []))
    return " ".join(t for t in tags if t)


def _load_history_docs() -> List[str]:
    docs: List[str] = []
    # 1) Ưu tiên Mongo NO3 (50 tập canon)
    try:
        from ..storage import mongo
        for item in mongo.list_canon_recent(limit=50):
            scr = item.get("script") or {}
            docs.append(_script_to_tag_doc(scr))
    except Exception as e:
        log.warning("Đọc history từ Mongo NO3 fail: %s — fallback file.", e)
    # 2) Fallback: thư mục history/
    if not docs and HISTORY_DIR.exists():
        for f in sorted(HISTORY_DIR.glob("*.json"))[-50:]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                docs.append(_script_to_tag_doc(data))
            except Exception:
                pass
    return docs


def is_duplicate(script: dict) -> tuple[bool, float]:
    candidate = _script_to_tag_doc(script)
    history = _load_history_docs()
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


def pick_macguffin() -> Dict:
    if not MACGUFFIN_PATH.exists():
        return {"name": "twist bất ngờ", "description": "Một nhân chứng mới xuất hiện với bằng chứng phá vỡ thế cờ."}
    pool = json.loads(MACGUFFIN_PATH.read_text(encoding="utf-8"))
    import random
    return random.choice(pool)


def vet_script(script: dict, budget, regen_fn) -> dict:
    """
    Lặp:
      - Nếu script duplicate => budget.consume('duplicate'); regen.
      - Sau anh_t_max_dup_retries => ép macguffin vào prompt, KHÔNG fail.

    regen_fn(extra_directive: str) -> script  (callback gọi lại LLM)
    """
    dup_count = 0
    current = script
    while True:
        dup, peak = is_duplicate(current)
        if not dup:
            log.info("anh_t PASS (similarity=%.3f)", peak)
            return current
        log.warning("anh_t DUPLICATE (peak=%.3f, dup#%d)", peak, dup_count + 1)
        dup_count += 1
        try:
            budget.consume("duplicate")
        except Exception as e:
            log.error("hết budget duplicate: %s — chấp nhận script", e)
            return current
        if dup_count >= settings.anh_t_max_dup_retries:
            mac = pick_macguffin()
            extra = (
                f"\nLƯU Ý: Bẻ lái kịch bản theo hướng MỚI HOÀN TOÀN bằng sự kiện sau:\n"
                f"- Tên: {mac.get('name')}\n- Mô tả: {mac.get('description')}\n"
            )
            log.warning("Ép macguffin: %s", mac.get("name"))
            current = regen_fn(extra)
            return current  # accept, không lặp nữa
        current = regen_fn("")
