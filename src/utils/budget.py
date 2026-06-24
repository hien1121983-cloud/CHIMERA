"""Global Retry Budget. 10 tổng cộng, chia nhỏ theo loại lỗi để 1 loại không vắt cạn quota."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
from .. config import settings


class BudgetExceeded(Exception):
    pass


@dataclass
class RetryBudget:
    limits: Dict[str, int] = field(default_factory=lambda: dict(settings.retry_budget))
    used: Dict[str, int] = field(default_factory=dict)

    def consume(self, kind: str) -> None:
        """Tăng counter cho 1 loại + tổng. Ném BudgetExceeded khi vượt."""
        if kind not in self.limits:
            raise ValueError(f"Unknown budget kind: {kind}")
        self.used[kind] = self.used.get(kind, 0) + 1
        self.used["total"] = self.used.get("total", 0) + 1
        if self.used[kind] > self.limits[kind]:
            raise BudgetExceeded(f"Budget cho '{kind}' đã hết ({self.limits[kind]}).")
        if self.used["total"] > self.limits["total"]:
            raise BudgetExceeded("Global retry budget đã hết.")

    def remaining(self, kind: str) -> int:
        return self.limits[kind] - self.used.get(kind, 0)

    def snapshot(self) -> Dict[str, int]:
        return dict(self.used)


# ============================================================
# V4.0 — BudgetManager đa-trạm (Vá #2)
# ============================================================
@dataclass
class BudgetManager:
    """Quản lý retry-pool + USD cap cho từng trạm pipeline.

    - request_retry(station): xin retry, trả False nếu hết pool/usd.
    - charge(station_short): cộng USD theo cost_table.
    - emergency_stop(): raise BudgetExceeded.
    """
    pool: Dict[str, int] = field(default_factory=lambda: dict(settings.budget_pool))
    cost_table: Dict[str, float] = field(default_factory=lambda: dict(settings.budget_cost_table))
    usd_spent: float = 0.0
    llm_calls: int = 0
    force_inject_callback: Optional[callable] = None

    def request_retry(self, station: str) -> bool:
        if station not in self.pool:
            raise ValueError(f"Unknown station: {station}")
        if self.pool[station] <= 0:
            if self.force_inject_callback:
                try:
                    self.force_inject_callback(station)
                except Exception:
                    pass
            return False
        if self.usd_spent >= settings.budget_usd_hard_cap:
            self.emergency_stop()
        if self.llm_calls >= settings.budget_llm_calls_hard_cap:
            self.emergency_stop()
        self.pool[station] -= 1
        return True

    def charge(self, station_short: str, calls: int = 1) -> None:
        cost = self.cost_table.get(station_short, 0.0) * calls
        self.usd_spent += cost
        self.llm_calls += calls

    def emergency_stop(self) -> None:
        raise BudgetExceeded(
            f"USD={self.usd_spent:.3f}/{settings.budget_usd_hard_cap} "
            f"calls={self.llm_calls}/{settings.budget_llm_calls_hard_cap}"
        )

    def snapshot(self) -> Dict:
        return {
            "pool_remaining": dict(self.pool),
            "usd_spent": round(self.usd_spent, 4),
            "llm_calls": self.llm_calls,
        }
