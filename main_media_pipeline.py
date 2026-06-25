"""Orchestrator cho Giai doan 3 (Media, Render & Delivery)."""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from core.logger import setup_logging
from dispatcher.a2_dispatcher import A2Dispatcher
from media_factory.t5_postman import T5Postman
from media_factory.audio_merger import AudioMerger
from render_engine.t6_ffmpeg import T6FFmpeg
from delivery.t7_courier import T7Courier
from delivery.report_generator import generate_report

logger = logging.getLogger(__name__)


async def run_stage_3(master_script: dict) -> dict:
    logger.info("=== BAT DAU GIAI DOAN 3: MEDIA, RENDER & DELIVERY ===")

    episode_number = master_script["meta"]["episode_number"]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    temp_dir = f"./temp/episode_{episode_number}_{timestamp}"
    Path(temp_dir).mkdir(parents=True, exist_ok=True)

    execution_log = {
        "images_count": 0,
        "audio_count": 0,
        "fallback_count": 0,
        "errors": [],
        "scene_timings": [],
    }

    # Buoc 1: A2 boc tach script -> execution json
    logger.info("[Stage3] Buoc 1: A2 boc tach script...")
    dispatcher = A2Dispatcher()
    execution_json = dispatcher.decompose_script(master_script)

    # Buoc 2: T5 sinh anh + audio
    logger.info("[Stage3] Buoc 2: T5 sinh media...")
    postman = T5Postman()
    execution_log = await postman.process(execution_json, temp_dir, execution_log)

    # Buoc 3: Merge audio
    logger.info("[Stage3] Buoc 3: Merge audio...")
    merged_audio = AudioMerger.merge(temp_dir)

    # Buoc 4 & 5: T6 render FFmpeg
    logger.info("[Stage3] Buoc 4/5: T6 render FFmpeg...")
    renderer = T6FFmpeg(execution_json, temp_dir)
    video_paths = renderer.render(merged_audio, execution_log)

    # Bao cao
    report = generate_report(execution_log, episode_number, temp_dir, video_paths)

    # Buoc 6: T7 giao hang qua Telegram (+ don rac)
    logger.info("[Stage3] Buoc 6: T7 giao hang...")
    courier = T7Courier()
    success = await courier.deliver(video_paths, episode_number, report)
    report["delivered"] = success

    logger.info(f"[Stage3] Hoan tat episode {episode_number} (delivered={success})")
    return report


async def main():
    script_path = "cache/master_script_latest.json"
    if not Path(script_path).exists():
        logger.error("Chua co Master_Script. Chay Ban 2 va duyet truoc.")
        return

    with open(script_path, "r", encoding="utf-8") as f:
        master_script = json.load(f)

    if not master_script.get("meta", {}).get("approved"):
        logger.error("Script chua duoc duyet. Chay Ban 2 va duyet truoc.")
        return

    try:
        report = await run_stage_3(master_script)
        print(f"\nOK Giai doan 3 thanh cong. Report: {report}")
    except Exception as e:
        print(f"\nFAIL Giai doan 3 that bai: {e}")
        raise


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
