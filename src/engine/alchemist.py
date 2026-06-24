"""Alchemist — nhào nặn prompt cuối cùng gửi cho LLM.

Trộn: biên bản toán học (sandbox) + trending + bối cảnh + Tone Calibration Layer.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import List, Dict
from ..processing.sandbox_loop import SandboxResult

# Content Moderation Adapter (System Prompt cố định)
TONE_CALIBRATION = (
    "BẮT BUỘC TUÂN THỦ:\n"
    "- TUYỆT ĐỐI KHÔNG mô tả hành vi sát thương vật lý, máu me, vũ khí.\n"
    "- Thay thế xung đột bằng: đấu tranh tâm lý, thao túng, gài bẫy tài chính, "
    "bẽ mặt xã hội, vạch trần bí mật.\n"
    "- Ngôn ngữ Việt Nam tự nhiên, drama nhưng không phản cảm.\n"
    "- Mỗi scene đúng 1-3 câu thoại.\n"
)


def _summarize_events(events) -> List[Dict]:
    return [
        {"scene": e.scene, "actor": e.actor, "target": e.target,
         "kind": e.kind, "tags": e.tags, "delta": e.delta}
        for e in events
    ]


def build_alchemy_prompt(
    branch: SandboxResult,
    trending: List[str],
    contexts: List[str],
    scenes: int,
    extra_directive: str = "",
) -> str:
    """Trả về prompt văn bản đầy đủ. Output Schema enforce ở tầng LLM Reader."""
    # BP-1: Nếu Context Mapper bật, dịch state nhân vật theo cặp (world → target_world).
    try:
        from ..config import settings as _settings
        if getattr(_settings, "enable_context_mapper", False):
            from .context_mapper import apply_context
            for _e in branch.entities:
                _from = getattr(_e, "world", None)
                _to = getattr(_e, "target_world", None) or _from
                if _from and _to and _from != _to:
                    _mapped = apply_context(
                        {"debts": getattr(_e, "debts", []) or [],
                         "items": getattr(_e, "items", []) or [],
                         "secrets": getattr(_e, "secrets", []) or []},
                        _from, _to,
                    )
                    for _k, _v in _mapped.items():
                        if hasattr(_e, _k):
                            try: setattr(_e, _k, _v)
                            except Exception: pass
    except Exception:
        # Context enrichment là best-effort, không được làm crash Stage A.
        pass

    events_brief = _summarize_events(branch.events)
    entities_brief = [
        {"id": e.id, "name": e.name, "role": e.role, "wealth": round(e.wealth, 1),
         "hatred": round(e.hatred, 2), "trust": round(e.trust, 2),
         "alive": not e.is_dead}
        for e in branch.entities
    ]

    return f"""Bạn là biên kịch một series truyện tranh có thoại đang lên trend trên TikTok.

{TONE_CALIBRATION}

DỮ LIỆU NGUỒN (đã được mô phỏng toán học, KHÔNG được mâu thuẫn):
- Nhân vật & trạng thái cuối: {json.dumps(entities_brief, ensure_ascii=False)}
- Chuỗi sự kiện đã xảy ra: {json.dumps(events_brief, ensure_ascii=False)}

TỪ KHÓA TRENDING ĐƯỢC LỒNG GHÉP TỰ NHIÊN:
{', '.join(trending[:5])}

BỐI CẢNH GỢI Ý: {', '.join(contexts[:3])}

NHIỆM VỤ:
Viết kịch bản đúng {scenes} phân cảnh dựa trên dữ liệu trên.
{extra_directive}
"""
