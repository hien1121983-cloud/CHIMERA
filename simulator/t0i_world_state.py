"""T0i - World State Simulator (Va M-09: router cho deltas)."""
import random
import logging
from typing import List, Dict

from core.db_client import ChimeraDB
from core.helpers import get_current_episode
from simulator.models import ContextSliceV2
from simulator.engines.character_engine import CharacterEngine
from simulator.engines.relationship_graph import RelationshipGraph
from simulator.engines.faction_engine import FactionEngine
from simulator.engines.economy_engine import EconomyEngine
from simulator.engines.consequence_engine import ConsequenceEngine
from simulator.engines.pressure_engine import PressureEngine

logger = logging.getLogger(__name__)


class WorldStateSimulator:
    """Trai tim cua Ban 1: Mo phong the gioi Chimera."""

    def __init__(self, db: ChimeraDB):
        self.db = db
        self.character_engine = CharacterEngine(db)
        self.relationship_graph = RelationshipGraph(db)
        self.faction_engine = FactionEngine(db)
        self.economy_engine = EconomyEngine(db)
        self.consequence_engine = ConsequenceEngine(db)
        self.pressure_engine = PressureEngine(db)

    def apply_episode_events(self, episode_number: int, deltas: List[Dict]):
        """Ap dung danh sach deltas tu Master_Script.json (Va M-09: router)."""
        for delta in deltas:
            target_type = delta.get("target_type")
            if target_type == "character":
                self.character_engine.apply(delta)
            elif target_type == "relationship":
                self.relationship_graph.apply(delta)
            elif target_type == "faction":
                self.faction_engine.apply(delta)
            elif target_type == "economy":
                self.economy_engine.apply(delta)
            elif target_type == "secret_pressure":
                self.pressure_engine.apply_pressure_change(delta)
            else:
                logger.warning(f"[T0i] Unknown delta type: {target_type}")

        self._run_world_tick(episode_number)
        self.pressure_engine.tick_all()
        self._persist_to_permanent(episode_number)

        logger.info(
            f"[T0i] Da ap dung {len(deltas)} deltas cho episode {episode_number}"
        )

    def _run_world_tick(self, tick: int):
        """The gioi tu van hanh, khong can nhan vat chinh."""
        factions = list(self.db.permanent.faction_states.find({}))
        for faction in factions:
            delta = random.randint(-2, 3)
            self.db.permanent.faction_states.update_one(
                {"faction_id": faction["faction_id"]},
                {"$inc": {"power": delta}},
            )
        logger.info(f"[T0i] World tick {tick} hoan tat")

    def generate_context_slice_v2(self) -> ContextSliceV2:
        """Soan Context Slice V2 cho A1 (Ban 2)."""
        return ContextSliceV2(
            layer_1_lore=self._get_immutable_lore(),
            layer_2_character_states=self.character_engine.get_all(),
            layer_3_relationships=self.relationship_graph.get_hot_edges(),
            layer_4_world_pressures=self.pressure_engine.get_active(),
            layer_5_ongoing_consequences=self.consequence_engine.get_active(),
            layer_6_mandatory_tasks=self._get_mandatory_resolutions(),
            layer_7_ticking_bombs=self.pressure_engine.get_above_threshold(),
            layer_8_overdue_hooks=self._get_overdue_hooks(),
        )

    def _get_immutable_lore(self) -> str:
        lore = self.db.permanent.world_info.find_one({})
        return lore.get("immutable_lore", "") if lore else ""

    def _get_mandatory_resolutions(self) -> List[str]:
        """Tra ve danh sach secret_id bat buoc A1 phai giai quyet."""
        bombs = self.pressure_engine.get_above_threshold()
        current_ep = get_current_episode()
        overdue = [
            s for s in self.db.permanent.secret_pressures.find({})
            if (current_ep - s.get("planted_at_episode", 0)) > 10
        ]
        return list({s["secret_id"] for s in bombs + overdue if "secret_id" in s})

    def _get_overdue_hooks(self) -> List[str]:
        """Lay cac hook qua han (>10 tap chua giai)."""
        current_ep = get_current_episode()
        hooks = self.db.permanent.story_hooks.find({
            "resolved": False,
            "planted_at_episode": {"$lt": current_ep - 10},
        })
        return [h["hook_id"] for h in hooks if "hook_id" in h]

    def _persist_to_permanent(self, episode_number: int):
        logger.info(f"[T0i] Persist state for episode {episode_number}")
