"""Jittering để chống rate-limit (chủ yếu cho Pollinations/HF — IP Azure)."""
import random
import time
from .. config import settings


def jitter_sleep() -> None:
    ms = random.randint(settings.jitter_min_ms, settings.jitter_max_ms)
    time.sleep(ms / 1000.0)
