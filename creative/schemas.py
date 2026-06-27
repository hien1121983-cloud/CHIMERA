"""Pydantic schemas cho A1 output (DA FIX LOI SCHEMA CUA GEMINI SDK)."""
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
    creativity_score: float = Field(
        default=0.5, 
        description="Điểm sáng tạo từ 0.0 đến 1.0"
    )


class Draft(BaseModel):
    draft_id: str
    synopsis: str = ""
    scenes: List[Scene] = Field(default_factory=list)
    creativity_score: float = Field(
        default=0.5,
        description="TỰ ĐÁNH GIÁ (từ 0.0 đến 1.0): 0.0-0.3 an toàn, 0.4-0.7 có bất ngờ, 0.8-1.0 radically different",
    )
    resolved_hooks: List[str] = Field(
        default_factory=list,
        description="Danh sách hook_id đã giải quyết (BẮT BUỘC bao gồm tất cả mandatory_tasks)",
    )
    world_state_deltas: List[Dict] = Field(
        default_factory=list,
        description="Danh sách thay đổi trạng thái thế giới sau tập này",
    )


class A1Output(BaseModel):
    drafts: List[Draft] = Field(
        default_factory=list,
        description="Danh sách chính xác 3 bản nháp (drafts). Không được ít hơn hoặc nhiều hơn 3.",
    )
