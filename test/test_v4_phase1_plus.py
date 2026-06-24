"""Tests cho 4 hướng update Phase 1+ (Monte Carlo 20, video_brief, comic SFX, transitions)."""
from __future__ import annotations
from pathlib import Path
import tempfile

from src.config import settings
from src.engine import comic_overlay, timeline_mapper, llm_reader


def test_monte_carlo_branches_is_20():
    assert settings.monte_carlo_branches == 20


def test_scene_schema_has_new_fields():
    props = llm_reader.SCENE_SCHEMA["properties"]
    assert "video_brief" in props
    assert "comic_text" in props


def test_scene_prompt_hook_includes_video_brief():
    p = llm_reader._scene_prompt({"episode_title": "x", "emotion_tag": "y"},
                                  {"scene": 1, "actor": "A", "beat": "b", "tags": []},
                                  scene_index=0)
    assert "video_brief" in p


def test_scene_prompt_non_hook_no_video_brief():
    p = llm_reader._scene_prompt({"episode_title": "x", "emotion_tag": "y"},
                                  {"scene": 2, "actor": "A", "beat": "b", "tags": []},
                                  scene_index=1)
    # Field xuất hiện trong schema JSON ở cuối prompt, nhưng phần INSTRUCTION
    # (trước "TRẢ VỀ JSON") không được nhắc đến video_brief khi không phải hook.
    instruction = p.split("TRẢ VỀ JSON")[0]
    assert "video_brief" not in instruction


def test_comic_overlay_resolve_text_priority():
    assert comic_overlay.resolve_text("calm") is None
    cfg = comic_overlay.resolve_text("dramatic")
    assert cfg and cfg["text"] == "BANG!"
    override = comic_overlay.resolve_text("calm", comic_text="OOPS!")
    assert override and override["text"] == "OOPS!"


def test_comic_overlay_render_png(tmp_path: Path):
    out = tmp_path / "sfx.png"
    p = comic_overlay.render_overlay("dramatic", (1080, 1920), out)
    assert p is not None and p.exists() and p.stat().st_size > 0


def test_comic_overlay_skip_when_calm(tmp_path: Path):
    out = tmp_path / "sfx.png"
    assert comic_overlay.render_overlay("calm", (1080, 1920), out) is None


def test_select_transition_no_file_returns_none():
    # Chưa có file mp4 trong data/transitions/, helper phải trả None.
    result = timeline_mapper.select_transition(
        {"scene": 3, "sfx_tag": "calm"},
        {"scene": 4, "sfx_tag": "dramatic"},
    )
    assert result is None