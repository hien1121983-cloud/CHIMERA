"""Alchemist — V4.0.

Hai chế độ:
  1. ``build_skeleton_brief``: dựng prompt TIẾNG VIỆT TÓM TẮT 1 khung kịch bản
     (cho Telegram approval). KHÔNG gọi LLM.
  2. ``build_alchemy_prompt``: dựng prompt FULL cho LLM Director (Trạm 3),
     bao gồm Tone Calibration Layer + 7 khối dữ liệu đầu vào (truyền vào qua
     ``aggregated``: archetypes/blueprints/mapping/hidden_items/dice/news/memes).
"""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import List, Dict, Any
from ..processing.sandbox_loop import SandboxResult

TONE_CALIBRATION = (
    "BẮT BUỘC TUÂN THỦ:\n"
    "- TUYỆT ĐỐI KHÔNG mô tả hành vi sát thương vật lý, máu me, vũ khí.\n"
    "- Thay thế xung đột bằng: đấu tranh tâm lý, thao túng, gài bẫy tài chính, "
    "bẽ mặt xã hội, vạch trần bí mật.\n"
    "- Ngôn ngữ Việt Nam tự nhiên, drama nhưng không phản cảm.\n"
    "- Mỗi scene đúng 1-3 câu thoại.\n"
)


def _summarize_events(events) -> List[Dict]:
    return [{"scene": e.scene, "actor": e.actor, "target": e.target,
             "kind": e.kind, "tags": e.tags, "delta": e.delta} for e in events]


def _skeleton_to_dicts(branch: SandboxResult) -> List[Dict]:
    out = []
    for sc in branch.skeleton or []:
        out.append({
            "scene": sc.scene, "actor": sc.actor, "target": sc.target,
            "beat": sc.beat, "tags": list(sc.tags), "is_glitch": bool(sc.is_glitch),
        })
    return out


# ---------------------------------------------------------------
# (1) BRIEF cho Showrunner (Telegram) — không gọi LLM
# ---------------------------------------------------------------

def build_skeleton_brief(branch: SandboxResult, score: float = 0.0) -> Dict[str, Any]:
    sk = _skeleton_to_dicts(branch)
    glitch_at = next((s["scene"] for s in sk if s.get("is_glitch")), None)
    return {
        "branch_id": branch.branch_id,
        "archetype": branch.archetype_id or "n/a",
        "drama_score": round(float(score), 3),
        "glitch_at": glitch_at,
        "scenes": sk,
        "forced_injection": branch.forced_injection or {},
    }


# ---------------------------------------------------------------
# (2) PROMPT FULL cho LLM Director (chỉ chạy SAU khi duyệt)
# ---------------------------------------------------------------

def build_alchemy_prompt(
    branch: SandboxResult,
    trending: List[str],
    contexts: List[str],
    scenes: int,
    extra_directive: str = "",
    aggregated: Dict[str, Any] | None = None,
) -> str:
    aggregated = aggregated or {}

    # Context Mapper (best-effort)
    try:
        from ..config import settings as _settings
        if getattr(_settings, "enable_context_mapper", False):
            from .context_mapper import apply_context
            for _e in branch.entities:
                _from = getattr(_e, "world", None)
                _to = getattr(_e, "target_world", None) or _from
                if _from and _to and _from != _to:
                    _mapped = apply_context({
                        "debts":   getattr(_e, "debts", []) or [],
                        "items":   getattr(_e, "items", []) or [],
                        "secrets": getattr(_e, "secrets", []) or [],
                    }, _from, _to)
                    for _k, _v in _mapped.items():
                        if hasattr(_e, _k):
                            try: setattr(_e, _k, _v)
                            except Exception: pass
    except Exception:
        pass

    events_brief   = _summarize_events(branch.events)
    skeleton_brief = _skeleton_to_dicts(branch)
    entities_brief = [
        {"id": e.id, "name": e.name, "role": e.role, "wealth": round(e.wealth, 1),
         "hatred": round(e.hatred, 2), "trust": round(e.trust, 2),
         "alive": not e.is_dead}
        for e in branch.entities
    ]

    # 7 khối dữ liệu
    archetypes   = aggregated.get("archetypes")   or []
    blueprints   = aggregated.get("blueprints")   or []
    mapping_dict = aggregated.get("mapping_dict") or {}
    hidden_items = aggregated.get("hidden_items") or []
    dice         = aggregated.get("destiny_dice") or []
    news         = aggregated.get("news")         or []
    memes        = aggregated.get("memes")        or []
    forced       = branch.forced_injection or {}

    extra_block = ""
    if forced:
        extra_block = (
            "\nÉP ĐỘT BIẾN (BẮT BUỘC nhồi vào kịch bản):\n"
            + json.dumps(forced, ensure_ascii=False) + "\n"
        )

    return f"""Bạn là biên kịch một series truyện tranh có thoại đang lên trend trên TikTok.

{TONE_CALIBRATION}

KHUNG KỊCH BẢN ĐÃ ĐƯỢC SHOWRUNNER DUYỆT (giữ ĐÚNG tuần tự beat):
{json.dumps(skeleton_brief, ensure_ascii=False)}

DỮ LIỆU NGUỒN (đã được mô phỏng toán học — KHÔNG được mâu thuẫn):
- Nhân vật & trạng thái cuối: {json.dumps(entities_brief, ensure_ascii=False)}
- Chuỗi sự kiện đã xảy ra:   {json.dumps(events_brief, ensure_ascii=False)}

7 KHỐI DỮ LIỆU NỀN (tham khảo & nhồi tự nhiên):
- archetypes ({len(archetypes)} mẫu): {json.dumps(archetypes[:3], ensure_ascii=False)}
- blueprints ({len(blueprints)} nhân vật): {json.dumps(blueprints[:3], ensure_ascii=False)}
- mapping_dictionary keys: {list(mapping_dict.keys())[:8]}
- hidden_items (sample): {json.dumps(hidden_items[:2], ensure_ascii=False)}
- destiny_dice (sample): {json.dumps(dice[:2], ensure_ascii=False)}
- news (top 3): {json.dumps(news[:3], ensure_ascii=False)}
- memes (top 3): {json.dumps(memes[:3], ensure_ascii=False)}

TỪ KHÓA TRENDING: {', '.join((trending or [])[:5])}
BỐI CẢNH GỢI Ý: {', '.join((contexts or [])[:3])}
{extra_block}
NHIỆM VỤ:
Viết kịch bản đúng {scenes} phân cảnh theo khung trên.
{extra_directive}
"""
