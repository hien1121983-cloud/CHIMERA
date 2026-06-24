"""Monte Carlo Search — chạy N nhánh sandbox song song bằng ThreadPoolExecutor."""
from __future__ import annotations
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from ..config import settings
from ..ingestion.entity_stats import Entity
from .sandbox_loop import run_sandbox, SandboxResult


def monte_carlo(entities: List[Entity], scenes: int,
                branches: int | None = None,
                base_seed: int | None = None) -> List[SandboxResult]:
    n = branches or settings.monte_carlo_branches
    base = base_seed if base_seed is not None else random.randint(1, 10_000_000)
    results: List[SandboxResult] = []
    with ThreadPoolExecutor(max_workers=min(settings.max_workers, n)) as pool:
        futs = [
            pool.submit(run_sandbox, entities, scenes, f"branch_{i+1}", base + i * 9973)
            for i in range(n)
        ]
        for f in as_completed(futs):
            results.append(f.result())
    return results
