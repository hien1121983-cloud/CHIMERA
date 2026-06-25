"""Orchestrator cho Giai doan 1 (Va C-04, I-01)."""
import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from core.logger import setup_logging
from core.health_checker import run_startup_health_check
from core.db_client import ChimeraDB
from core.helpers import get_current_episode, send_telegram_alert_sync
from fetchers.t0_archetypes import T0Archetypes
from fetchers.t0a_blueprints import T0aBlueprints
from fetchers.t0b_locations import T0bLocations
from fetchers.t0c_platform_rules import T0cPlatformRules
from fetchers.t0d_rde import T0dRDE
from fetchers.t0e_trends import T0eTrends
from fetchers.t0f_world_rules import T0fWorldRules
from fetchers.t0g_secret_items import T0gSecretItems
from fetchers.t0h_wildcards import T0hWildcards
from simulator.t0i_world_state import WorldStateSimulator
from simulator.models import MasterPayload, PayloadMeta

logger = logging.getLogger(__name__)

# Va I-01: Map ten tram -> class
STATION_MAP = {
    "T0": T0Archetypes,
    "T0a": T0aBlueprints,
    "T0b": T0bLocations,
    "T0c": T0cPlatformRules,
    "T0d": T0dRDE,
    "T0e": T0eTrends,
    "T0f": T0fWorldRules,
    "T0g": T0gSecretItems,
    "T0h": T0hWildcards,
}

# Cac tram bat buoc phai thanh cong
CRITICAL_STATIONS = {"T0a", "T0g", "T0h"}


def run_stage_1() -> MasterPayload:
    """Chay toan bo Giai doan 1. Tra ve Master_Payload cho Ban 2."""
    logger.info("=" * 60)
    logger.info("=== BAT DAU GIAI DOAN 1: LOGIC & MO PHONG ===")
    logger.info("=" * 60)

    # 1. Health check
    health = asyncio.run(run_startup_health_check())
    logger.info(f"[Stage1] Health check: {health}")

    # 2. Chay song song cac tram T0x (Va I-01)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            name: pool.submit(cls().run) for name, cls in STATION_MAP.items()
        }
        results: Dict[str, any] = {name: f.result() for name, f in futures.items()}

    # 3. Kiem tra tram critical
    for name, r in results.items():
        if not r.success and name in CRITICAL_STATIONS:
            error_msg = f"[{name}] That bai: {r.error}. Pipeline dung."
            logger.critical(error_msg)
            send_telegram_alert_sync(error_msg)
            raise RuntimeError(error_msg)

    # 4. T0i tong hop Context Slice V2
    db = ChimeraDB()
    simulator = WorldStateSimulator(db)
    context_slice = simulator.generate_context_slice_v2()

    # 5. Dong goi Master_Payload (Va C-04)
    payload = MasterPayload(
        meta=PayloadMeta(
            pipeline_version="5.0.1",
            episode_number=get_current_episode(),
            generated_at=datetime.utcnow().isoformat() + "Z",
            fallback_used=any(r.fallback_used for r in results.values()),
        ),
        archetypes=results["T0"].data or [],
        protagonists=results["T0a"].data or [],
        locations=results["T0b"].data or [],
        platform_rules=results["T0c"].data or {},
        world_pressures=results["T0d"].data,
        trend_phrase=results["T0e"].data or {},
        world_rules=results["T0f"].data or [],
        secret_item=results["T0g"].data,
        supporting_cast=results["T0h"].data or [],
        context_slice_v2=context_slice,
    )

    # 6. Luu tam de recovery
    payload_path = "cache/master_payload_latest.json"
    Path("cache").mkdir(exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    payload_size = os.path.getsize(payload_path)
    logger.info(f"[Stage1] Hoan tat. Payload: {payload_size} bytes -> {payload_path}")
    return payload


if __name__ == "__main__":
    setup_logging()
    try:
        payload = run_stage_1()
        print(f"\nOK Giai doan 1 thanh cong. Episode: {payload.meta.episode_number}")
    except Exception as e:
        print(f"\nFAIL Giai doan 1 that bai: {e}")
        raise
