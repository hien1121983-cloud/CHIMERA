"""Sandbox Loop — vòng lặp giả lập sinh tồn cho 1 nhánh kịch bản."""
from __future__ import annotations
import copy
import random
from dataclasses import dataclass, field
from typing import List, Dict
from ..ingestion.entity_stats import Entity, interaction_score, betray_probability


@dataclass
class TickEvent:
    scene: int
    actor: str
    target: str | None
    kind: str           # interaction / betrayal / revive / death / npc_in
    delta: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class SandboxResult:
    entities: List[Entity]
    events: List[TickEvent]
    seed: int
    branch_id: str


def _alive(es: List[Entity]) -> List[Entity]:
    return [e for e in es if not e.is_dead and not e.is_npc_reserve]


def _reserve(es: List[Entity]) -> List[Entity]:
    return [e for e in es if e.is_npc_reserve]


def run_sandbox(entities: List[Entity], scenes: int, branch_id: str, seed: int) -> SandboxResult:
    rng = random.Random(seed)
    es = copy.deepcopy(entities)
    events: List[TickEvent] = []

    for tick in range(1, scenes + 1):
        alive = _alive(es)
        if len(alive) < 2:
            reserves = _reserve(es)
            if reserves:
                npc = reserves[0]
                npc.is_npc_reserve = False
                events.append(TickEvent(tick, npc.id, None, "npc_in", tags=["npc_in"]))
                continue
            break

        actor = rng.choice(alive)
        target = rng.choice([e for e in alive if e.id != actor.id])

        # Trừ survival mỗi tick
        actor.survival -= rng.uniform(2, 5)
        target.survival -= rng.uniform(1, 3)

        intensity = interaction_score(actor, target)
        evt_tags = ["interaction"]
        delta: Dict[str, float] = {}

        # Phản bội?
        if rng.random() < betray_probability(actor, target):
            loss = rng.uniform(200, 1500) * intensity
            target.wealth -= loss
            actor.wealth += loss * 0.6
            target.hatred = min(1.0, target.hatred + 0.15)
            actor.trust = max(0.0, actor.trust - 0.1)
            evt_tags.append("betrayal")
            delta = {"target_wealth": -loss, "actor_wealth": loss * 0.6}
            events.append(TickEvent(tick, actor.id, target.id, "betrayal",
                                    delta=delta, tags=evt_tags))
        else:
            # tương tác thường — gài bẫy / thao túng tài chính
            shift = rng.uniform(50, 400) * intensity
            if rng.random() < 0.5:
                target.wealth -= shift
                actor.wealth += shift
            evt_tags.append("power_shift")
            delta = {"shift": shift}
            events.append(TickEvent(tick, actor.id, target.id, "interaction",
                                    delta=delta, tags=evt_tags))

        # Chết?
        if target.survival <= 0:
            if target.revives_left > 0:
                target.revives_left -= 1
                target.survival = 60.0
                events.append(TickEvent(tick, target.id, None, "revive",
                                        tags=["revive"]))
            else:
                target.is_dead = True
                events.append(TickEvent(tick, target.id, None, "death",
                                        tags=["death"]))

    return SandboxResult(entities=es, events=events, seed=seed, branch_id=branch_id)
