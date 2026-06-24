"""Retry helper với exponential backoff + jittering."""
from __future__ import annotations
import time
import random
from typing import Callable, TypeVar
from .logger import get_logger

T = TypeVar("T")
log = get_logger("retry")


def retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 1.0, label: str = "task") -> T:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            wait = base_delay * (2 ** i) + random.uniform(0, 0.5)
            log.warning("[%s] attempt %d/%d failed: %s — retry sau %.1fs",
                        label, i + 1, attempts, e, wait)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc
