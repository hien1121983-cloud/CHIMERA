"""Monte Carlo Search — V4.0.

Sinh N nhánh skeleton song song. Bước này KHÔNG gọi LLM, chỉ là mô phỏng
toán học + lắp khung beat. Có thể được gọi lại bởi "Anh T" để sinh BÙ khi
khung bị loại do trùng lặp; khi đó nhận thêm ``forced_injection`` để ép đột
biến (ví dụ: 1 hidden_item + 1 destiny_dice).
"""
from __future__ import annotations
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from ..config import settings
from ..ingestion.entity_stats import Entity
from .sandbox_loop import run_sandbox, SandboxResult


def monte_carlo(entities: List[Entity], scenes: int,
                branches: int | None = None,
                base_seed: int | None = None,
                archetypes: Optional[List[Dict[str, Any]]] = None,
                forced_injection: Optional[Dict[str, Any]] = None) -> List[SandboxResult]:
    n = branches or settings.monte_carlo_branches
    base = base_seed if base_seed is not None else random.randint(1, 10_000_000)
    archetypes = archetypes or []
    results: List[SandboxResult] = []
    with ThreadPoolExecutor(max_workers=min(settings.max_workers, n)) as pool:
        futs = []
        for i in range(n):
            arch = archetypes[i % len(archetypes)] if archetypes else {}
            futs.append(pool.submit(
                run_sandbox, entities, scenes, f"branch_{i+1}", base + i * 9973,
                None,
                arch.get("id", "") if isinstance(arch, dict) else "",
                forced_injection or {},
            ))
        for f in as_completed(futs):
            results.append(f.result())
    return results
