"""Pydantic schemas cho A1 output."""
from typing import Dict, List

from pydantic import BaseModel, Field


class Dialogue(BaseModel):
    character: str
    line: str
    emotion: str = "neutral"
    voice_id: str = ""


class Scene(BaseModel):
    scene_id: str
    action: str = ""
    visual_prompt_en: str
    dialogues: List[Dialogue] = Field(default_factory=list)
    bgm_mood: str = "neutral"
    camera_angle: str = "medium_shot"
    creativity_score: float = Field(ge=0.0, le=1.0, default=0.5)


class Draft(BaseModel):
    draft_id: str
    synopsis: str = ""
    scenes: List[Scene] = Field(default_factory=list)
    creativity_score: float = Field(
        ge=0.0, le=1.0, default=0.5,
        description="TU DANH GIA: 0.0-0.3 an toan, 0.4-0.7 co bat ngo, 0.8-1.0 radically different",
    )
    resolved_hooks: List[str] = Field(
        default_factory=list,
        description="Danh sach hook_id da giai quyet (BAT BUOC bao gom tat ca mandatory_tasks)",
    )
    world_state_deltas: List[Dict] = Field(
        default_factory=list,
        description="Danh sach thay doi trang thai the gioi sau tap nay",
    )


class A1Output(BaseModel):
    """Schema dau ra BAT BUOC cua A1."""
    drafts: List[Draft] = Field(min_length=3, max_length=3)
    metadata: Dict = Field(default_factory=dict)
