"""Unit tests cho Phase 2 — Meta Layer V4.0."""
from __future__ import annotations
import random

import pytest

from src.meta import entropy_monitor, soft_reboot, plot_armor, spinoff_engine, co_creation
from src.config import settings as _settings


def _set_flag(name: str, value: bool) -> bool:
    """Settings là frozen dataclass — bypass bằng __dict__ trực tiếp."""
    prev = getattr(_settings, name)
    _settings.__dict__[name] = value
    return prev


# ---------- Entropy Monitor ----------
def test_entropy_low_when_diverse_and_fresh():
    r = entropy_monitor.compute_entropy_from_data(
        contradictions_in_window=0, window_size=50,
        archetype_tags=[f"a{i}" for i in range(10)],
        plot_armor_avg=3.0, drama_trend_delta=0.0,
        trending_today=["x", "y"], trending_at_episode=["x", "y"],
        view_drop_ratio=0.0,
    )
    assert r["total_entropy"] < 20
    assert r["recommended_action"] == "CONTINUE_NORMAL"


def test_entropy_high_triggers_soft_reboot():
    r = entropy_monitor.compute_entropy_from_data(
        contradictions_in_window=50, window_size=50,
        archetype_tags=["a"] * 20,
        plot_armor_avg=0.0, drama_trend_delta=1.0,
        trending_today=["a"], trending_at_episode=["z"],
        view_drop_ratio=1.0,
    )
    assert r["total_entropy"] >= 80
    assert r["recommended_action"] == "SOFT_REBOOT"


def test_entropy_anti_pattern_when_repetition_high():
    r = entropy_monitor.compute_entropy_from_data(
        contradictions_in_window=0, window_size=50,
        archetype_tags=["a"] * 30,           # 0 diversity -> rep 1.0
        plot_armor_avg=3.0, drama_trend_delta=0.0,
        trending_today=["x"], trending_at_episode=["x"],
        view_drop_ratio=0.0,
    )
    assert r["recommended_action"] in {"INJECT_ANTI_PATTERN", "SOFT_REBOOT"}


# ---------- Soft Reboot ----------
def test_should_reboot_interval():
    prev = _set_flag("enable_soft_reboot", True)
    try:
        assert soft_reboot.should_reboot(100) is True
        assert soft_reboot.should_reboot(101) is False
        assert soft_reboot.should_reboot(0) is False
    finally:
        _set_flag("enable_soft_reboot", prev)


def test_should_reboot_on_entropy_action():
    prev = _set_flag("enable_soft_reboot", True)
    try:
        assert soft_reboot.should_reboot(42, "SOFT_REBOOT") is True
    finally:
        _set_flag("enable_soft_reboot", prev)


def test_extract_core_soul_keeps_keys():
    e = {"id": "e1", "name": "An", "root_traumas": ["X"], "core_belief": "Y",
         "plot_armor_tokens": 2, "irrelevant": "drop_me"}
    soul = soft_reboot.extract_core_soul(e)
    assert soul["entity_id"] == "e1"
    assert soul["core_soul"]["root_traumas"] == ["X"]
    assert "irrelevant" not in soul["core_soul"]
    assert soul["plot_armor_tokens"] == 2


def test_roll_reboot_event_returns_named_event():
    ev = soft_reboot.roll_reboot_event(random.Random(0))
    assert "name" in ev and ev["name"]


# ---------- Plot Armor ----------
def test_predict_death_zero_when_name_absent():
    assert plot_armor.predict_death_in_skeleton("anh ấy đi chợ", "Bob") == 0.0


def test_predict_death_high_with_keywords():
    text = "Bob bị giết. Bob hy sinh. Bob chết."
    p = plot_armor.predict_death_in_skeleton(text, "Bob")
    assert p >= 0.8


def test_plot_armor_consumes_token():
    prev = _set_flag("enable_plot_armor", True)
    try:
        chars = [{"name": "Bob", "plot_armor_tokens": 2}]
        r = plot_armor.evaluate("Bob chết.", chars, random.Random(1))
        assert r["decisions"][0]["action"] == "INJECT_MACGUFFIN"
        assert chars[0]["plot_armor_tokens"] == 1
    finally:
        _set_flag("enable_plot_armor", prev)


def test_plot_armor_allows_death_when_empty():
    prev = _set_flag("enable_plot_armor", True)
    try:
        chars = [{"name": "Bob", "plot_armor_tokens": 0}]
        r = plot_armor.evaluate("Bob chết. Bob hy sinh.", chars, random.Random(1))
        assert r["decisions"][0]["action"] == "ALLOW_DEATH"
    finally:
        _set_flag("enable_plot_armor", prev)


def test_plot_armor_skipped_when_flag_off():
    prev = _set_flag("enable_plot_armor", False)
    try:
        r = plot_armor.evaluate("Bob chết.", [{"name": "Bob"}])
        assert r["skipped"] is True
    finally:
        _set_flag("enable_plot_armor", prev)


# ---------- Spin-off ----------
def test_score_character_pure():
    assert spinoff_engine.score_character(10, 0.5) == 5.0
    assert spinoff_engine.score_character(0, 1.0) == 0.0


def test_analyze_popularity_orders_by_score():
    canon = [
        {"episode_id": "e1", "script": {"character_mentions": ["A", "A", "B"]}},
        {"episode_id": "e2", "script": {"character_mentions": ["A", "B"]}},
    ]
    ranking = spinoff_engine.analyze_popularity(canon)
    assert ranking[0][0] == "A"
    assert ranking[0][1] >= ranking[1][1]


# ---------- Co-creation ----------
def test_pick_unused_worlds_excludes_recent():
    out = co_creation.pick_unused_worlds(["xianxia"], k=2, rng=random.Random(0))
    assert "xianxia" not in out
    assert len(out) == 2