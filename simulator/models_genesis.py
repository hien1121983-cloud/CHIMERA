"""Pydantic models cho WorldGenesis output (WorldMap + WorldHistory + WorldRules)."""
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── WorldMap ─────────────────────────────────────────────────────────────────

class WorldZone(BaseModel):
    zone_id: str
    name: str
    controlling_faction: str
    contested_by: List[str] = Field(default_factory=list)
    terrain_type: str  # tech_hub | underground | neutral_ground | residential | industrial
    strategic_value: int = Field(ge=0, le=100, default=50)
    description: str = ""
    control_pct: int = Field(ge=0, le=100, default=100)


class WorldMap(BaseModel):
    zones: List[WorldZone] = Field(default_factory=list)
    total_zones: int = 0
    generated_at_tick: int = 0


# ─── WorldHistory ─────────────────────────────────────────────────────────────

class WorldHistoryEntry(BaseModel):
    era: str
    tick_range: str  # ví dụ: "Before Tick 1" hoặc "Tick 1-10"
    event: str
    impact: str
    involved_factions: List[str] = Field(default_factory=list)
    significance: int = Field(ge=0, le=100, default=50)


class WorldHistory(BaseModel):
    era_name: str
    era_tagline: str = ""
    founding_events: List[WorldHistoryEntry] = Field(default_factory=list)
    generated_at_tick: int = 0


# ─── WorldRules ───────────────────────────────────────────────────────────────

class WorldRuleEffect(BaseModel):
    effect_type: str  # template_weight | stat_modifier | pressure_multiplier | narrative_tag
    target: str       # template_id | stat_name | pressure_category | tag_string
    value: float      # multiplier hoặc delta


class WorldRule(BaseModel):
    rule_id: str
    name: str
    description: str
    condition_type: str   # faction_power_gap | world_pressure_category | tick_modulo | character_count
    condition_value: str  # giá trị so sánh (chuỗi để linh hoạt)
    condition_op: str = "gte"  # gte | lte | eq | contains
    effects: List[WorldRuleEffect] = Field(default_factory=list)
    is_active: bool = True
    scope: str = "global"  # global | faction | character


class WorldRules(BaseModel):
    rules: List[WorldRule] = Field(default_factory=list)
    generated_at_tick: int = 0


# ─── GenesisOutput (toàn bộ LLM trả về) ──────────────────────────────────────

class GenesisOutput(BaseModel):
    world_map: WorldMap
    world_history: WorldHistory
    world_rules: WorldRules
