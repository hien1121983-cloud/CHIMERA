"""Unit tests cho các pure functions."""
import pytest
from src.ingestion.entity_stats import Entity, interaction_score, betray_probability, power_delta
from src.processing.drama_evaluator import score_branches
from src.processing.sandbox_loop import run_sandbox
from src.utils.budget import RetryBudget, BudgetExceeded


def _e(id, **kw):
    base = {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}
    base.update(kw.get("ocean", {}))
    return Entity(id=id, name=id, role="x", ocean=base,
                  wealth=kw.get("wealth", 1000),
                  hatred=kw.get("hatred", 0.0),
                  relations=kw.get("relations", {}))


def test_interaction_score_bounds():
    a = _e("a"); b = _e("b")
    s = interaction_score(a, b)
    assert 0 <= s <= 1


def test_enemy_increases_score():
    a = _e("a", ocean={"E": 0.9}); b = _e("b", ocean={"A": 0.1}, relations={})
    a.relations = {"b": "enemy"}
    enemy_s = interaction_score(a, b)
    a.relations = {"b": "ally"}
    ally_s = interaction_score(a, b)
    assert enemy_s > ally_s


def test_betray_with_high_neuroticism():
    a = _e("a", ocean={"N": 0.9, "A": 0.1}, hatred=0.8)
    b = _e("b")
    assert betray_probability(a, b) > 0.5


def test_budget_consumes_total_and_kind():
    b = RetryBudget()
    for _ in range(3):
        b.consume("json_error")
    with pytest.raises(BudgetExceeded):
        b.consume("json_error")


def test_budget_total_cap():
    b = RetryBudget()
    for _ in range(3): b.consume("json_error")
    for _ in range(4): b.consume("duplicate")
    for _ in range(3): b.consume("content_filter")
    with pytest.raises(BudgetExceeded):
        b.consume("content_filter")


def test_sandbox_runs_deterministic():
    es = [_e("a", wealth=5000, relations={"b": "enemy"}),
          _e("b", wealth=5000, relations={"a": "enemy"})]
    r1 = run_sandbox(es, scenes=5, branch_id="t", seed=42)
    r2 = run_sandbox(es, scenes=5, branch_id="t", seed=42)
    assert len(r1.events) == len(r2.events)


def test_score_branches_topk():
    es = [_e("a", wealth=5000, relations={"b": "enemy"}),
          _e("b", wealth=5000)]
    results = [run_sandbox(es, 5, f"b{i}", seed=i) for i in range(5)]
    scored = score_branches(results)
    assert len(scored) == 5
    assert scored[0]["score"] >= scored[-1]["score"]
