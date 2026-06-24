"""Drama Evaluator — chấm điểm các nhánh, giữ Top-K.

Drama Score = w1*scaled_delta_power + w2*scaled_count_betrayal + w3*scaled_max_single_loss
Min-max scaling trên TẤT CẢ các nhánh (so sánh tương đối)."""
from __future__ import annotations
from typing import List, Dict
from ..config import settings
from .sandbox_loop import SandboxResult


def _metrics(r: SandboxResult) -> Dict[str, float]:
    delta_power = 0.0
    betrayals = 0
    max_loss = 0.0
    for ev in r.events:
        if "betrayal" in ev.tags:
            betrayals += 1
            loss = abs(ev.delta.get("target_wealth", 0.0))
            max_loss = max(max_loss, loss)
            delta_power += loss
        elif "power_shift" in ev.tags:
            delta_power += abs(ev.delta.get("shift", 0.0))
    return {"delta_power": delta_power, "betrayals": float(betrayals), "max_loss": max_loss}


def _minmax(vals: List[float]) -> List[float]:
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


def score_branches(results: List[SandboxResult]) -> List[Dict]:
    metrics = [_metrics(r) for r in results]
    s_power = _minmax([m["delta_power"] for m in metrics])
    s_betray = _minmax([m["betrayals"] for m in metrics])
    s_loss = _minmax([m["max_loss"] for m in metrics])
    w = settings.drama_weights

    out = []
    for r, m, sp, sb, sl in zip(results, metrics, s_power, s_betray, s_loss):
        score = (sp * w["w1_delta_power"]
                 + sb * w["w2_betrayal"]
                 + sl * w["w3_max_loss"])
        out.append({"result": r, "metrics": m, "score": round(score, 4)})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def top_k(results: List[SandboxResult], k: int | None = None) -> List[Dict]:
    k = k or settings.top_k_branches
    return score_branches(results)[:k]
