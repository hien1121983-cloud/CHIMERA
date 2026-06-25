"""Bao cao san xuat cuoi cung."""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_report(execution_log: dict, episode_number: int, temp_dir: str,
                    video_paths=None) -> dict:
    """Tao bao cao san xuat tu execution_log."""
    report = {
        "episode_number": episode_number,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "images_count": execution_log.get("images_count", 0),
        "audio_count": execution_log.get("audio_count", 0),
        "fallback_count": execution_log.get("fallback_count", 0),
        "errors": execution_log.get("errors", []),
        "video_parts": len(video_paths) if video_paths else 0,
        "total_size_bytes": sum(
            os.path.getsize(p) for p in (video_paths or []) if os.path.exists(p)
        ),
    }
    try:
        report_path = f"{temp_dir}/production_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[Report] Khong luu duoc bao cao: {e}")
    return report


def find_video_outputs(temp_dir: str, episode_number: int) -> list:
    """Tim cac file mp4 dau ra (final hoac cac part)."""
    candidates = []
    final_path = f"{temp_dir}/episode_{episode_number}_final.mp4"
    if os.path.exists(final_path):
        candidates.append(final_path)
    for part_num in range(1, 20):
        part_path = f"{temp_dir}/episode_{episode_number}_part{part_num}.mp4"
        if os.path.exists(part_path):
            candidates.append(part_path)
    return candidates
