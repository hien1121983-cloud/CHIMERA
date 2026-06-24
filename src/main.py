"""Project Chimera — orchestrator (V4.0 Phase-1 fix, 2 stages).

Stage A (``--stage produce_script``):
  - Ingestion -> Monte Carlo -> Top-K -> sinh 3 phiên bản KỊCH BẢN (chưa render).
  - Lưu purgatory + gửi Telegram approval (in đậm cinematic_video_prompt Scene 1).
  - Kết thúc -> máy ảo TẮT (không chờ user).

Stage B (``--stage assemble --episode-id ... --version ...``):
  - Kéo script đã duyệt từ Mongo + blob ``scene_01.mp4`` user upload.
  - Sinh ảnh 2..N + TTS (ElevenLabs Round-Robin -> fallback edge-tts).
  - Ghép FFmpeg (có glitch transition tĩnh) -> MP4 -> gửi Telegram.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import shutil
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Optional

from .config import settings, SCENES
from .utils import get_logger, RetryBudget, BudgetExceeded
from .ingestion import (
    load_entities, fetch_trending, pick_bgm, Entity,
)
from .processing import monte_carlo, top_k
from .engine import (
    build_alchemy_prompt, generate_script, vet_script,
    render_all, build_timeline, build_video, gemini_pool,
)
from .storage import mongo
from .delivery import telegram_bot

log = get_logger("main")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ADS = ROOT / "ads"


def _install_soft_timeout(seconds: int) -> None:
    def _h(signum, frame):
        log.error("Soft timeout %ds — abort.", seconds)
        sys.exit(124)
    signal.signal(signal.SIGALRM, _h)
    signal.alarm(seconds)


def _episode_id() -> str:
    return "ep_" + dt.datetime.utcnow().strftime("%Y%m%d_%H%M")


def _load_or_seed_entities() -> List[Entity]:
    try:
        state = mongo.load_current_state()
    except Exception as e:
        log.warning("Mongo load fail: %s", e)
        state = []
    if state:
        return [Entity(**{k: v for k, v in s.items() if k not in ("character_id", "_id")}) for s in state]
    return load_entities(DATA / "entities.json")


# =====================================================================
# STAGE A — produce_script
# =====================================================================

def run_produce_script() -> int:
    _install_soft_timeout(settings.soft_timeout_sec)
    log.info("=== STAGE A: produce_script | scenes=%d ===", SCENES)

    alive = gemini_pool.ensure_pool()
    log.info("Gemini pool: %d/%d.", len(alive), len(settings.gemini_keys))

    episode_id = _episode_id()
    entities = _load_or_seed_entities()
    trending = fetch_trending(cache_path=DATA / "_trending_cache.json")
    contexts = json.loads((DATA / "contexts.json").read_text(encoding="utf-8"))
    try: mongo.save_keywords(trending)
    except Exception as e: log.warning("save_keywords fail: %s", e)

    branches = monte_carlo(entities, scenes=SCENES)
    top3 = top_k(branches, k=settings.top_k_branches)
    log.info("Top-%d drama: %s", len(top3), [round(b["score"], 3) for b in top3])

    budget = RetryBudget()
    versions: List[Dict] = []
    for i, br in enumerate(top3, 1):
        branch = br["result"]
        try:
            alchemy = build_alchemy_prompt(branch, trending, contexts, SCENES)
            script = generate_script(alchemy, SCENES, budget)
            script = vet_script(script, budget,
                                regen=lambda extra: generate_script(alchemy + "\n" + extra, SCENES, budget))
            versions.append({
                "version": i,
                "script": script,
                "drama_score": br["score"],
                "title": script.get("episode_title", ""),
                "character_state": [asdict(e) for e in branch.entities],
            })
        except BudgetExceeded as e:
            log.error("Budget hết khi sinh v%d: %s", i, e); break
        except Exception as e:
            log.exception("v%d fail: %s", i, e)

    if not versions:
        log.error("Không sinh được phiên bản nào."); return 1

    # Lưu purgatory
    try:
        mongo.save_purgatory(episode_id, versions)
    except Exception as e:
        log.warning("save_purgatory fail: %s", e)

    # Telegram approval — gửi cả 3 phiên bản (in đậm cinematic_video_prompt Scene 1)
    for v in versions:
        try:
            telegram_bot.send_script_for_approval(episode_id, v["version"], v["script"])
        except Exception as e:
            log.error("send_script_for_approval v%d fail: %s", v["version"], e)

    try:
        mongo.set_episode_state(episode_id, {
            "state": "awaiting_approval",
            "version_pending": None,
        })
    except Exception as e:
        log.warning("set_episode_state fail: %s", e)

    log.info("=== STAGE A done. Đã gửi %d kịch bản chờ duyệt. ===", len(versions))
    return 0


# =====================================================================
# STAGE B — assemble (sau khi user upload scene_01.mp4)
# =====================================================================

def run_assemble(episode_id: str, version: int) -> int:
    _install_soft_timeout(settings.soft_timeout_sec)
    log.info("=== STAGE B: assemble | %s v%d ===", episode_id, version)

    # 1. Lấy script đã duyệt
    drafts = mongo.get_purgatory(episode_id)
    chosen = next((d for d in drafts if d["version"] == version), None)
    if not chosen:
        log.error("Không thấy draft v%d của %s.", version, episode_id); return 2
    script: dict = chosen["script"]

    out_root = ROOT / f"tap_phim_nay_{episode_id}"
    if out_root.exists():
        shutil.rmtree(out_root)
    ver_dir = out_root / f"version_{version}"
    ver_dir.mkdir(parents=True, exist_ok=True)

    # 2. Lấy scene_01.mp4 user đã upload
    try:
        blob = mongo.load_scene1_blob(episode_id, version)
    except Exception as e:
        log.error("load_scene1_blob fail: %s", e); return 3
    if not blob:
        log.error("scene_01.mp4 không có trong Mongo blob store."); return 3
    (ver_dir / "scene_01.mp4").write_bytes(blob)
    log.info("Đã ghi scene_01.mp4 (%d KB).", len(blob)//1024)

    # 3. Sinh ảnh Scene 2..N + TTS (renderer mới tự BỎ QUA Scene 1)
    media = render_all(script, ver_dir)

    # 4. BGM + timeline
    bgm = pick_bgm(script.get("emotion_tag", "neutral"))
    summary = build_timeline(script, media, ver_dir, bgm_path=bgm, ads_dir=ADS)

    # 5. FFmpeg ghép (có glitch transition tĩnh)
    video_path = build_video(
        ver_dir,
        bgm_path=Path(bgm) if bgm else None,
        scenes_meta=script.get("scenes") or [],
    )
    if not video_path:
        log.error("build_video fail — xem ffmpeg_error.log"); return 4

    # 6. Gửi Telegram
    try:
        telegram_bot.deliver_videos([{
            "version": version,
            "drama_score": chosen.get("drama_score", 0.0),
            "title": chosen.get("title", ""),
            "path": video_path,
        }], episode_id)
    except Exception as e:
        log.error("Telegram deliver fail: %s", e)

    # 7. Update state
    try:
        mongo.set_episode_state(episode_id, {
            "state": "assembled",
            "version_pending": version,
        })
    except Exception:
        pass

    log.info("=== STAGE B done ==="); return 0


# =====================================================================
# CLI
# =====================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("chimera")
    p.add_argument("--stage", choices=["produce_script", "assemble"], required=False,
                   default="produce_script")
    p.add_argument("--episode-id", default=None)
    p.add_argument("--version", type=int, default=1)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.stage == "produce_script":
        return run_produce_script()
    if args.stage == "assemble":
        if not args.episode_id:
            log.error("--episode-id bắt buộc cho stage=assemble"); return 64
        return run_assemble(args.episode_id, args.version)
    return 64


# tương thích ngược với entrypoint cũ ``python -m src.main``
def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
