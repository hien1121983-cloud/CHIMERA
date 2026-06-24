"""Sandbox Loop — V4.0.

Mỗi nhánh chỉ sinh ra một **SKELETON** (khung kịch bản 15 phân cảnh dạng beat
ngắn, không có dialogue chi tiết). Skeleton được chấm điểm bởi
``drama_evaluator`` và "Anh T" sẽ chống trùng lặp ngay trên skeleton này.
LLM Director (Trạm 3) chỉ được phép viết chi tiết SAU khi Showrunner duyệt.

Aggregator T1 cũng nằm tại đây: ghép đủ 7 khối dữ liệu đầu vào trước khi
chạy Monte Carlo (5 khối tĩnh + 2 khối động Mongo).
"""
from __future__ import annotations
import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
from ..ingestion.entity_stats import Entity, interaction_score, betray_probability
from ..utils import get_logger

log = get_logger("sandbox")

# ============================================================
# Aggregator T1 — 7 khối dữ liệu đầu vào
# ============================================================

_ROOT = Path(__file__).resolve().parents[2]
_DATA = _ROOT / "data"

# 5 khối tĩnh
_PATH_ARCHETYPES   = _DATA / "archetypes.json"
_PATH_BLUEPRINTS   = _DATA / "characters" / "blueprints.json"
_PATH_MAPPING      = _DATA / "lore" / "mapping_dictionary.json"
_PATH_HIDDEN_ITEMS = _DATA / "secrets" / "hidden_items.json"
_PATH_DICE         = _DATA / "destiny_dice.json"


def _read_json(p: Path, default):
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Đọc %s fail: %s", p, e)
    return default


def aggregate_inputs() -> Dict[str, Any]:
    """Gom đủ 7 khối dữ liệu. KHÔNG raise — thiếu khối nào trả default rỗng."""
    archetypes   = _read_json(_PATH_ARCHETYPES,   [])
    blueprints   = _read_json(_PATH_BLUEPRINTS,   [])
    mapping_dict = _read_json(_PATH_MAPPING,      {})
    hidden_items = _read_json(_PATH_HIDDEN_ITEMS, [])
    dice         = _read_json(_PATH_DICE,         [])

    # 2 khối động: Mongo URL_NO3 (đã được scraper cào lúc 6h sáng)
    news: List[Dict] = []
    memes: List[Dict] = []
    try:
        from ..storage import mongo
        try:
            news = list(mongo.fetch_recent_news(limit=30) or [])
        except Exception as e:
            log.info("Mongo news không sẵn sàng: %s", e)
        try:
            memes = list(mongo.fetch_recent_memes(limit=30) or [])
        except Exception as e:
            log.info("Mongo memes không sẵn sàng: %s", e)
    except Exception as e:
        log.warning("Aggregator: import mongo fail: %s", e)

    log.info("Aggregator T1: archetypes=%d, blueprints=%d, mapping=%d, "
             "hidden_items=%d, dice=%d, news=%d, memes=%d",
             len(archetypes), len(blueprints), len(mapping_dict),
             len(hidden_items), len(dice), len(news), len(memes))

    return {
        "archetypes":   archetypes,
        "blueprints":   blueprints,
        "mapping_dict": mapping_dict,
        "hidden_items": hidden_items,
        "destiny_dice": dice,
        "news":         news,
        "memes":        memes,
    }


# ============================================================
# Sandbox simulation (giữ logic nền tảng)
# ============================================================

@dataclass
class TickEvent:
    scene: int
    actor: str
    target: str | None
    kind: str           # interaction / betrayal / revive / death / npc_in
    delta: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class SkeletonScene:
    """1 phân cảnh trong khung kịch bản (chưa có dialogue chi tiết)."""
    scene: int
    actor: str
    target: str | None
    beat: str
    tags: List[str]
    is_glitch: bool = False


@dataclass
class SandboxResult:
    entities: List[Entity]
    events: List[TickEvent]
    seed: int
    branch_id: str
    # === V4.0: khung kịch bản tóm tắt — đầu vào cho "Anh T" & cho LLM Director ===
    skeleton: List[SkeletonScene] = field(default_factory=list)
    archetype_id: str = ""
    forced_injection: Dict[str, Any] = field(default_factory=dict)


def _alive(es: List[Entity]) -> List[Entity]:
    return [e for e in es if not e.is_dead and not e.is_npc_reserve]


def _reserve(es: List[Entity]) -> List[Entity]:
    return [e for e in es if e.is_npc_reserve]


def _beat_from_event(ev: TickEvent, actor: Entity, target: Entity | None) -> str:
    if ev.kind == "betrayal":
        loss = abs(ev.delta.get("target_wealth", 0.0))
        return f"{actor.name} phản bội {target.name if target else '?'} — thiệt hại {int(loss)}."
    if ev.kind == "interaction":
        return f"{actor.name} thao túng {target.name if target else '?'} — cán cân quyền lực dịch chuyển."
    if ev.kind == "death":
        return f"{actor.name} gục ngã, bí mật bị phơi bày."
    if ev.kind == "revive":
        return f"{actor.name} hồi sinh ngoạn mục."
    if ev.kind == "npc_in":
        return f"{actor.name} bất ngờ xuất hiện, đảo cục diện."
    return f"{actor.name} hành động."


def run_sandbox(entities: List[Entity], scenes: int, branch_id: str, seed: int,
                glitch_scene: int | None = None,
                archetype_id: str = "",
                forced_injection: Dict[str, Any] | None = None) -> SandboxResult:
    rng = random.Random(seed)
    es = copy.deepcopy(entities)
    events: List[TickEvent] = []
    skeleton: List[SkeletonScene] = []
    id2ent = {e.id: e for e in es}

    # Chọn 1 phân cảnh "is_glitch" mặc định cho tập có yếu tố xuyên không
    # (~30% nhánh; thường là scene 8 trong tập 15).
    if glitch_scene is None and rng.random() < 0.30:
        glitch_scene = scenes // 2 + 1   # 8/15

    for tick in range(1, scenes + 1):
        alive = _alive(es)
        if len(alive) < 2:
            reserves = _reserve(es)
            if reserves:
                npc = reserves[0]
                npc.is_npc_reserve = False
                ev = TickEvent(tick, npc.id, None, "npc_in", tags=["npc_in"])
                events.append(ev)
                skeleton.append(SkeletonScene(
                    scene=tick, actor=npc.name, target=None,
                    beat=_beat_from_event(ev, npc, None),
                    tags=ev.tags, is_glitch=(tick == glitch_scene),
                ))
                continue
            break

        actor = rng.choice(alive)
        target = rng.choice([e for e in alive if e.id != actor.id])
        actor.survival -= rng.uniform(2, 5)
        target.survival -= rng.uniform(1, 3)
        intensity = interaction_score(actor, target)
        evt_tags = ["interaction"]

        if rng.random() < betray_probability(actor, target):
            loss = rng.uniform(200, 1500) * intensity
            target.wealth -= loss
            actor.wealth += loss * 0.6
            target.hatred = min(1.0, target.hatred + 0.15)
            actor.trust = max(0.0, actor.trust - 0.1)
            evt_tags.append("betrayal")
            ev = TickEvent(tick, actor.id, target.id, "betrayal",
                           delta={"target_wealth": -loss, "actor_wealth": loss * 0.6},
                           tags=evt_tags)
        else:
            shift = rng.uniform(50, 400) * intensity
            if rng.random() < 0.5:
                target.wealth -= shift; actor.wealth += shift
            evt_tags.append("power_shift")
            ev = TickEvent(tick, actor.id, target.id, "interaction",
                           delta={"shift": shift}, tags=evt_tags)
        events.append(ev)
        skeleton.append(SkeletonScene(
            scene=tick, actor=actor.name, target=target.name,
            beat=_beat_from_event(ev, actor, target),
            tags=evt_tags, is_glitch=(tick == glitch_scene),
        ))

        if target.survival <= 0:
            if target.revives_left > 0:
                target.revives_left -= 1; target.survival = 60.0
                events.append(TickEvent(tick, target.id, None, "revive", tags=["revive"]))
            else:
                target.is_dead = True
                events.append(TickEvent(tick, target.id, None, "death", tags=["death"]))

    return SandboxResult(
        entities=es, events=events, seed=seed, branch_id=branch_id,
        skeleton=skeleton, archetype_id=archetype_id,
        forced_injection=forced_injection or {},
    )
