"""History FIFO — giữ 50 file kịch bản gần nhất trong thư mục history/.

Dùng làm dữ liệu đối chiếu cho Anh T (chống trùng) và làm "Chính sử".
Chạy CLI: `python -m src.storage.history_fifo --episode ep_001 --version 2`
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from ..utils import get_logger

log = get_logger("history_fifo")
HISTORY = Path("history")
MAX_KEEP = 50


def commit(episode_id: str, version: int) -> Path:
    """Đọc canon từ Mongo và ghi vào history/<episode>.json. FIFO 50."""
    from .mongo import get_canon
    HISTORY.mkdir(parents=True, exist_ok=True)
    canon = get_canon(episode_id)
    if not canon:
        log.error("Canon %s không tồn tại trong Mongo.", episode_id)
        sys.exit(1)
    target = HISTORY / f"{episode_id}.json"
    target.write_text(json.dumps({
        "episode_id": episode_id,
        "version": version,
        "script": canon.get("script", {}),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote %s", target)
    enforce_fifo()
    return target


def enforce_fifo(max_keep: int = MAX_KEEP) -> None:
    files = sorted(HISTORY.glob("*.json"), key=lambda p: p.stat().st_mtime)
    excess = len(files) - max_keep
    for f in files[:max(0, excess)]:
        f.unlink(missing_ok=True)
        log.info("FIFO removed %s", f.name)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--episode", required=True)
    p.add_argument("--version", type=int, required=True)
    a = p.parse_args()
    commit(a.episode, a.version)
