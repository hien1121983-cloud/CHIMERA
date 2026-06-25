"""Pydantic models cho world state va Master_Payload."""
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class CharacterState(BaseModel):
    character_id: str
    hp: int = Field(ge=0, le=100, default=100)
    reputation: int = Field(ge=0, le=100, default=50)
    wealth: int = Field(ge=0, default=0)
    trauma: int = Field(ge=0, le=100, default=0)
    political_power: int = Field(ge=0, le=100, default=0)
    status: str = "alive"  # alive | dead | missing


class RelationshipEdge(BaseModel):
    trust: int = Field(ge=0, le=100, default=50)
    love: int = Field(ge=0, le=100, default=0)
    fear: int = Field(ge=0, le=100, default=0)
    debt: int = Field(ge=0, default=0)
    hatred: int = Field(ge=0, le=100, default=0)


class FactionState(BaseModel):
    faction_id: str
    power: int = Field(ge=0, le=100, default=50)
    wealth: int = Field(ge=0, default=0)
    territory: int = Field(ge=0, le=100, default=50)
    public_support: int = Field(ge=0, le=100, default=50)


class SecretPressure(BaseModel):
    secret_id: str
    content: str
    pressure: int = Field(ge=0, le=100, default=0)
    holder_id: str
    planted_at_episode: int
    threshold: int = 80


class Consequence(BaseModel):
    event_id: str
    primary: str
    secondary: List[str] = []
    tertiary: List[str] = []
    affected_factions: List[str] = []


class ContextSliceV2(BaseModel):
    layer_1_lore: str = ""
    layer_2_character_states: Dict[str, Any] = Field(default_factory=dict)
    layer_3_relationships: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    layer_4_world_pressures: List[Dict] = Field(default_factory=list)
    layer_5_ongoing_consequences: List[Any] = Field(default_factory=list)
    layer_6_mandatory_tasks: List[str] = Field(default_factory=list)
    layer_7_ticking_bombs: List[Any] = Field(default_factory=list)
    layer_8_overdue_hooks: List[str] = Field(default_factory=list)


class PayloadMeta(BaseModel):
    pipeline_version: str = "5.0.1"
    episode_number: int
    generated_at: str
    fallback_used: bool = False


class MasterPayload(BaseModel):
    """Dau ra cua Ban 1 -> dau vao cho Ban 2."""
    meta: PayloadMeta
    archetypes: Any = Field(default_factory=list)
    protagonists: List[Dict] = Field(default_factory=list)
    locations: List[Dict] = Field(default_factory=list)
    platform_rules: Dict = Field(default_factory=dict)
    world_pressures: Optional[Any] = None
    trend_phrase: Dict = Field(default_factory=dict)
    world_rules: List[str] = Field(default_factory=list)
    secret_item: Optional[Any] = None
    supporting_cast: List[Dict] = Field(default_factory=list)
    context_slice_v2: ContextSliceV2
