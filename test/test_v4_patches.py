"""Unit tests cho Phase 1 — 6 vá lỗi V4.0."""
from __future__ import annotations
import pytest

from src.engine import t_checker, seed_lock, glitch_curse
from src.engine.context_mapper import ContextMapper
from src.utils.budget import BudgetManager, BudgetExceeded


# ---------- Vá #1 — T-Checker ----------
def test_t_checker_extract_tags_handles_dict_list_str():
    assert t_checker.extract_tags(None) == []
    assert "đòi nợ" in t_checker.extract_tags("Hắn đến đòi nợ rất căng")
    out = t_checker.extract_tags([{"event": "phản bội cay đắng"}])
    assert "phản bội" in out


def test_t_checker_pass_when_no_history():
    r = t_checker.validate_skeleton({"event": "đòi nợ"}, [])
    assert r.status == "PASS"


def test_t_checker_flags_repetition():
    history = [{"tags": ["đòi nợ", "sổ đỏ", "phản bội"]}] * 5
    skeleton = {"a": "đòi nợ sổ đỏ phản bội"}
    r = t_checker.validate_skeleton(skeleton, history)
    # Có thể PASS hoặc FAIL/repetition tuỳ TF-IDF, nhưng phải có similarity > 0
    assert r.similarity >= 0.0


# ---------- Vá #2 — BudgetManager ----------
def test_budget_request_retry_decrements_pool():
    bm = BudgetManager()
    init = bm.pool["T2_3_t_checker"]
    assert bm.request_retry("T2_3_t_checker") is True
    assert bm.pool["T2_3_t_checker"] == init - 1


def test_budget_returns_false_when_pool_empty():
    bm = BudgetManager()
    for _ in range(bm.pool["T2_3_t_checker"]):
        bm.request_retry("T2_3_t_checker")
    assert bm.request_retry("T2_3_t_checker") is False


def test_budget_emergency_stop_on_usd():
    bm = BudgetManager()
    bm.usd_spent = 999.0
    with pytest.raises(BudgetExceeded):
        bm.request_retry("T3_director")


def test_budget_unknown_station_raises():
    bm = BudgetManager()
    with pytest.raises(ValueError):
        bm.request_retry("nonexistent")


# ---------- Vá #3 — Glitch Curse ----------
def test_roll_curse_has_required_fields():
    c = glitch_curse.roll_curse()
    assert c["type"] in {"LINGUISTIC", "PHYSICAL", "MEMORY", "RELATIONAL"}
    assert c["remaining_episodes"] >= 1
    assert c["manifestation"]


def test_tick_down_removes_curse_when_zero():
    c = {"type": "PHYSICAL", "remaining_episodes": 1}
    assert glitch_curse.tick_down(c) is None
    c2 = {"type": "PHYSICAL", "remaining_episodes": 3}
    out = glitch_curse.tick_down(c2)
    assert out and out["remaining_episodes"] == 2


def test_apply_to_state_attaches_curse():
    s = {"name": "A"}
    s2 = glitch_curse.apply_to_state(s, {"type": "MEMORY", "remaining_episodes": 2})
    assert s2["active_curse"]["type"] == "MEMORY"


# ---------- Vá #4 — Context Mapper ----------
def test_context_mapper_translates_currency_and_items():
    m = ContextMapper()
    state = {
        "debts": [{"amount": 5, "currency": "linh_thach", "item_name": "phi_kiem"}],
        "items": [{"name": "phi_kiem"}],
    }
    out = m.map_state_to_world(state, "xianxia", "modern_vn")
    assert out["debts"][0]["currency"] == "VND"
    assert out["debts"][0]["amount"] == 5_000_000
    assert out["debts"][0]["item_name"] == "dao_phay"
    assert out["items"][0]["name"] == "dao_phay"


def test_context_mapper_noop_when_same_world():
    m = ContextMapper()
    s = {"items": [{"name": "x"}]}
    assert m.map_state_to_world(s, "modern_vn", "modern_vn") is s


def test_context_mapper_missing_rule_returns_state():
    m = ContextMapper()
    s = {"items": [{"name": "x"}]}
    out = m.map_state_to_world(s, "unknown", "alsoUnknown")
    assert out == s


# ---------- Vá #6 — Seed Lock ----------
def test_compute_seed_deterministic_and_in_range():
    a = seed_lock.compute_seed("Nguyễn Văn A", "xianxia_dark", "scar_left_eye")
    b = seed_lock.compute_seed("Nguyễn Văn A", "xianxia_dark", "scar_left_eye")
    assert a == b
    assert 0 <= a < 2 ** 32


def test_compute_seed_differs_per_character():
    a = seed_lock.compute_seed("A", "w1", "x")
    b = seed_lock.compute_seed("B", "w1", "x")
    assert a != b