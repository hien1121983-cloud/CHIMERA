"""Entity Stats — hệ OCEAN + công thức tương tác (pure functions, dễ unit-test)."""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Literal


Relation = Literal["enemy", "ally", "neutral"]


@dataclass
class Entity:
    id: str
    name: str
    role: str                          # protagonist / antagonist / npc
    ocean: Dict[str, float]            # O, C, E, A, N ∈ [0,1]
    wealth: float = 1000.0
    trust: float = 0.5                 # độ tin cậy với phe chính
    hatred: float = 0.0
    survival: float = 100.0
    revives_left: int = 2
    relations: Dict[str, Relation] = field(default_factory=dict)
    is_npc_reserve: bool = False
    is_dead: bool = False


# --- Pure functions ---

def interaction_score(a: Entity, b: Entity) -> float:
    """Cường độ xung đột tiềm năng giữa 2 nhân vật.

    Công thức (kết quả ∈ [0,1]):
      base = |E_a - A_b| + |N_a - C_b|
      rel_mod = {enemy: 1.4, neutral: 1.0, ally: 0.6}
      wealth_gap = sigmoid(|wealth_a - wealth_b| / 5000)
      score = clamp01( (base + wealth_gap) / 3 * rel_mod )
    """
    base = abs(a.ocean["E"] - b.ocean["A"]) + abs(a.ocean["N"] - b.ocean["C"])
    rel = a.relations.get(b.id, "neutral")
    mod = {"enemy": 1.4, "neutral": 1.0, "ally": 0.6}[rel]
    wealth_gap = 1 / (1 + math.exp(-abs(a.wealth - b.wealth) / 5000))
    return max(0.0, min(1.0, (base + wealth_gap) / 3.0 * mod))


def power_delta(before: Entity, after: Entity) -> float:
    """Chênh lệch power (wealth + trust*1000 - hatred*500)."""
    def p(e: Entity) -> float:
        return e.wealth + e.trust * 1000 - e.hatred * 500
    return p(after) - p(before)


def betray_probability(actor: Entity, victim: Entity) -> float:
    """Xác suất phản bội — tỉ lệ thuận với N (Neuroticism) và hatred, nghịch với A (Agreeableness)."""
    raw = 0.5 * actor.ocean["N"] + 0.3 * actor.hatred + 0.2 * (1 - actor.ocean["A"])
    if actor.relations.get(victim.id) == "ally":
        raw *= 1.5
    return max(0.0, min(1.0, raw))


# --- IO ---

def load_entities(path: str | Path) -> List[Entity]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Entity(**e) for e in raw]


def dump_entities(entities: List[Entity], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps([asdict(e) for e in entities], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
