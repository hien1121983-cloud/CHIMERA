"""T0i - World State Simulator (Va M-09: router cho deltas)."""
import random
import logging
from datetime import datetime
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
from simulator.engines.world_map_engine import WorldMapEngine
from simulator.engines.world_history_engine import WorldHistoryEngine
from simulator.engines.world_rules_engine import WorldRulesEngine

logger = logging.getLogger(__name__)


class WorldStateSimulator:
    """Trai tim cua Ban 1: Mo phong the gioi Chimera."""

    def __init__(self, db: ChimeraDB):
        self.db = db
        self.character_engine   = CharacterEngine(db)
        self.relationship_graph = RelationshipGraph(db)
        self.faction_engine     = FactionEngine(db)
        self.economy_engine     = EconomyEngine(db)
        self.consequence_engine = ConsequenceEngine(db)
        self.pressure_engine    = PressureEngine(db)
        # ── WorldGenesis engines ──────────────────────────────────────────
        self.world_map_engine     = WorldMapEngine(db)
        self.world_history_engine = WorldHistoryEngine(db)
        self.world_rules_engine   = WorldRulesEngine(db)

    # ── Public API ────────────────────────────────────────────────────────

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

        # Ghi lịch sử tick vào WorldHistory
        self._append_tick_to_history(episode_number, deltas)

        self._persist_to_permanent(episode_number)
        logger.info(
            f"[T0i] Da ap dung {len(deltas)} deltas cho episode {episode_number}"
        )

    def generate_context_slice_v2(self) -> ContextSliceV2:
        """Soan Context Slice V2 cho A1 (Ban 2) — bao gồm 3 layer WorldGenesis."""
        self._check_genesis_prerequisite()

        # World context cho rules evaluation
        faction_powers = {
            fid: data.get("power", 50)
            for fid, data in self.faction_engine.get_all().items()
        }
        alive_count = self.db.permanent.character_states.count_documents(
            {"status": "alive"}
        )
        world_context = {
            "faction_powers": faction_powers,
            "alive_character_count": alive_count,
            "pressure_categories": [
                p.get("category", "") for p in self.pressure_engine.get_active()
            ],
            "tick": get_current_episode(),
        }

        return ContextSliceV2(
            layer_1_lore=self._get_immutable_lore(),
            layer_2_character_states=self.character_engine.get_all(),
            layer_3_relationships=self.relationship_graph.get_hot_edges(),
            layer_4_world_pressures=self.pressure_engine.get_active(),
            layer_5_ongoing_consequences=self.consequence_engine.get_active(),
            layer_6_mandatory_tasks=self._get_mandatory_resolutions(),
            layer_7_ticking_bombs=self.pressure_engine.get_above_threshold(),
            layer_8_overdue_hooks=self._get_overdue_hooks(),
            # ── WorldGenesis layers ──────────────────────────────────────
            layer_9_world_map=self.world_map_engine.get_strategic_map_summary(),
            layer_10_world_history=self.world_history_engine.get_full_timeline_summary(),
            layer_11_active_rules=self.world_rules_engine.get_active_rules_summary(
                world_context
            ),
        )

    # ── Internal ──────────────────────────────────────────────────────────

    def _check_genesis_prerequisite(self):
        """Cảnh báo nếu WorldGenesis chưa chạy (không block — chỉ log)."""
        doc = self.db.permanent["world_info"].find_one(
            {"genesis_completed": True}, {"_id": 0}
        )
        if not doc:
            logger.warning(
                "[T0i] ⚠️  WorldGenesis chưa chạy! "
                "Layer 9/10/11 sẽ trống. "
                "Chạy: python world_genesis_runner.py"
            )

    def _append_tick_to_history(self, episode_number: int, deltas: List[Dict]):
        """Ghi tóm tắt tick vào WorldHistory."""
        try:
            involved_chars = list({
                d.get("id") for d in deltas
                if d.get("target_type") == "character" and d.get("id")
            })
            involved_factions = list({
                d.get("id") for d in deltas
                if d.get("target_type") == "faction" and d.get("id")
            })

            significance = min(100, len(deltas) * 5 + len(involved_chars) * 3)

            self.world_history_engine.append_tick_event(
                tick=episode_number,
                event_type="episode_deltas",
                description=(
                    f"Episode {episode_number}: "
                    f"{len(deltas)} deltas, "
                    f"{len(involved_chars)} nhân vật bị ảnh hưởng."
                ),
                involved_chars=involved_chars,
                involved_factions=involved_factions,
                significance=significance,
            )
        except Exception as e:
            logger.warning(f"[T0i] Không ghi được history tick {episode_number}: {e}")

    def _run_world_tick(self, tick: int):
        """The gioi tu van hanh, khong can nhan vat chinh.

        FIX #8: Truoc day dung random.randint() khong co seed -> moi lan chay
        cho cung episode cho ket qua khac nhau, khong the reproduce bug hoac
        audit lich su. Nay dung seed = tick XOR hash(faction_id) de:
        - Cung tap + cung faction luon cho cung delta (reproducible).
        - Faction khac nhau trong cung tap van cho delta khac nhau.
        - Log chi tiet tat ca thay doi de debug world state bat thuong.
        """
        factions = list(self.db.permanent.faction_states.find({}))
        tick_summary = []

        for faction in factions:
            faction_id = faction.get("faction_id", "unknown")
            seed = tick ^ (hash(faction_id) & 0xFFFFFFFF)
            rng = random.Random(seed)
            delta = rng.randint(-2, 3)

            self.db.permanent.faction_states.update_one(
                {"faction_id": faction_id},
                {"$inc": {"power": delta}},
            )
            tick_summary.append(f"{faction_id}:{delta:+d}")

        logger.info(
            f"[T0i] World tick {tick} hoan tat "
            f"({len(factions)} factions). "
            f"Power deltas: {', '.join(tick_summary) if tick_summary else 'none'}"
        )

    def _get_immutable_lore(self) -> str:
        lore = self.db.permanent.world_info.find_one({})
        return lore.get("immutable_lore", "") if lore else ""

    def _get_mandatory_resolutions(self) -> List[str]:
        bombs = self.pressure_engine.get_above_threshold()
        current_ep = get_current_episode()
        overdue = [
            s for s in self.db.permanent.secret_pressures.find({})
            if (current_ep - s.get("planted_at_episode", 0)) > 10
        ]
        return list({s["secret_id"] for s in bombs + overdue if "secret_id" in s})

    def _get_overdue_hooks(self) -> List[str]:
        current_ep = get_current_episode()
        hooks = self.db.permanent.story_hooks.find({
            "resolved": False,
            "planted_at_episode": {"$lt": current_ep - 10},
        })
        return [h["hook_id"] for h in hooks if "hook_id" in h]

    def _persist_to_permanent(self, episode_number: int):
        """Lưu snapshot world state sau world_tick vào MongoDB permanent."""
        logger.info(f"[T0i] Persist world snapshot cho episode {episode_number}...")
        try:
            faction_states = list(
                self.db.permanent.faction_states.find({}, {"_id": 0})
            )
            alive_count = self.db.permanent.character_states.count_documents(
                {"status": "alive"}
            )
            active_pressures   = self.pressure_engine.get_active()
            active_consequences = self.consequence_engine.get_active()

            snapshot = {
                "episode_number": episode_number,
                "snapshot_at": datetime.utcnow().isoformat() + "Z",
                "alive_character_count": alive_count,
                "faction_states": faction_states,
                "active_pressure_count": len(active_pressures),
                "active_pressures": active_pressures,
                "active_consequence_count": len(active_consequences),
                "active_consequences": active_consequences,
            }

            self.db.permanent.world_snapshots.update_one(
                {"episode_number": episode_number},
                {"$set": snapshot},
                upsert=True,
            )
            logger.info(
                f"[T0i] ✅ World snapshot episode {episode_number} đã lưu — "
                f"{alive_count} nhân vật sống, "
                f"{len(faction_states)} faction, "
                f"{len(active_pressures)} áp lực, "
                f"{len(active_consequences)} hậu quả."
            )
        except Exception as e:
            logger.error(
                f"[T0i] ❌ Lỗi _persist_to_permanent episode {episode_number}: {e}"
            )
