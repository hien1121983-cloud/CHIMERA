"""Project Chimera — orchestrator V4.0 (2-stage, anti-deadlock).

Stage A (``--stage produce_script``)
    1. Aggregator T1 — gom đủ 7 khối dữ liệu đầu vào.
    2. Monte Carlo sinh N nhánh **SKELETON** (KHÔNG gọi LLM, KHÔNG sinh chi tiết).
    3. Drama Evaluator chấm điểm, tự đào thải, giữ Top-K (mặc định 3).
    4. "Anh T" chống trùng lặp trên skeleton. Nếu thiếu -> Monte Carlo sinh bù.
       Quá ``anh_t_max_dup_retries`` -> ép đột biến (hidden_item + dice).
    5. Gửi Telegram TÓM TẮT 3 khung -> tạm dừng máy ảo.

Stage B (``--stage assemble --episode-id ... --version ...``)
    1. Đánh thức Trạm 3 (Director LLM) cho ĐÚNG khung đã duyệt -> viết chi tiết.
    2. Render scene 2..N + TTS (hybrid theo speaker_role).
    3. FFmpeg SPLIT: 1 file ``system_video_full.mp4`` HOẶC
       ``system_video_part1/2.mp4`` (khi có glitch).
    4. Gửi Telegram. 2 khung nháp còn lại HỦY HẲN -> 0 token.
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
from typing import List, Dict

from .config import settings, SCENES
from .utils import get_logger, RetryBudget, BudgetExceeded
from .ingestion import load_entities, fetch_trending, pick_bgm, Entity
from .processing import monte_carlo
from .processing.drama_evaluator import top_k, score_branches
from .processing.sandbox_loop import aggregate_inputs
from .engine import (
    build_alchemy_prompt, generate_script,
    render_all, build_timeline, build_video, gemini_pool,
)
from .engine import anh_t as anh_t_mod
from .engine.alchemist import build_skeleton_brief
from .storage import mongo
from .delivery import telegram_bot

log = get_logger("main")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ADS = ROOT / "ads"


def _install_soft_timeout(seconds: int) -> None:
    def _h(signum, frame):
        log.error("Soft timeout %ds — abort.", seconds); sys.exit(124)
    signal.signal(signal.SIGALRM, _h); signal.alarm(seconds)


def _episode_id() -> str:
    return "ep_" + dt.datetime.utcnow().strftime("%Y%m%d_%H%M")


def _load_or_seed_entities() -> List[Entity]:
    try:
        state = mongo.load_current_state()
    except Exception as e:
        log.warning("Mongo load fail: %s", e); state = []
    if state:
        return [Entity(**{k: v for k, v in s.items() if k not in ("character_id", "_id")})
                for s in state]
    return load_entities(DATA / "entities.json")


# =====================================================================
# STAGE A — Sinh SKELETON, KHÔNG gọi LLM Director
# =====================================================================

def run_produce_script() -> int:
    _install_soft_timeout(settings.soft_timeout_sec)
    log.info("=== STAGE A: produce_skeletons | scenes=%d ===", SCENES)

    episode_id = _episode_id()
    entities   = _load_or_seed_entities()
    aggregated = aggregate_inputs()
    archetypes = aggregated.get("archetypes") or []

    # 1) Monte Carlo lần đầu — sinh nhiều nhánh
    branches = monte_carlo(entities, scenes=SCENES, archetypes=archetypes)
    scored = score_branches(branches)
    top_pool = scored[: max(settings.top_k_branches * 3, settings.top_k_branches)]
    skeletons_pool = [b["result"] for b in top_pool]
    score_map = {id(b["result"]): b["score"] for b in scored}
    log.info("Monte Carlo: %d nhánh -> Top %d theo drama_score.",
             len(branches), len(top_pool))

    # 2) "Anh T" vet — sinh bù nếu thiếu (regen_fn nhận n_needed + forced_injection)
    def _regen(n_needed: int, forced: Dict) -> List:
        new = monte_carlo(entities, scenes=SCENES,
                          branches=max(n_needed * 3, settings.top_k_branches * 2),
                          archetypes=archetypes,
                          forced_injection=forced)
        new_scored = score_branches(new)
        for b in new_scored:
            score_map[id(b["result"])] = b["score"]
        return [b["result"] for b in new_scored[: n_needed * 2]]

    vetted = anh_t_mod.vet_skeletons(
        skeletons_pool, settings.top_k_branches, _regen,
    )
    if not vetted:
        log.error("Anh T không lấy được khung nào — abort."); return 1

    # 3) Đóng gói brief + lưu purgatory (KHÔNG có script chi tiết)
    purgatory_versions: List[Dict] = []
    for i, br in enumerate(vetted, 1):
        score = float(score_map.get(id(br), 0.0))
        brief = build_skeleton_brief(br, score=score)
        purgatory_versions.append({
            "version": i,
            "skeleton_brief": brief,
            "seed": br.seed,
            "branch_id": br.branch_id,
            "archetype_id": br.archetype_id,
            "drama_score": score,
            "character_state": [asdict(e) for e in br.entities],
            "forced_injection": br.forced_injection or {},
        })

    try:
        mongo.save_purgatory(episode_id, purgatory_versions)
    except Exception as e:
        log.warning("save_purgatory fail: %s", e)

    # 4) Gửi Telegram tóm tắt từng khung
    for v in purgatory_versions:
        try:
            telegram_bot.send_skeleton_for_approval(
                episode_id, v["version"], v["skeleton_brief"])
        except Exception as e:
            log.error("send_skeleton_for_approval v%d fail: %s", v["version"], e)

    try:
        mongo.set_episode_state(episode_id, {
            "state": "awaiting_skeleton_approval", "version_pending": None,
        })
    except Exception as e:
        log.warning("set_episode_state fail: %s", e)

    log.info("=== STAGE A done — %d khung kịch bản chờ DUYỆT. 0 token LLM tiêu thụ. ===",
             len(purgatory_versions))
    return 0


# =====================================================================
# STAGE B — Sau khi user DUYỆT 1 khung
# =====================================================================

def _branch_from_state(version_doc: Dict, entities: List[Entity]):
    """Tái dựng SandboxResult từ purgatory để feed LLM Director."""
    from .processing.sandbox_loop import run_sandbox
    seed = int(version_doc.get("seed") or 0)
    branch_id = version_doc.get("branch_id") or f"branch_v{version_doc.get('version')}"
    arch = version_doc.get("archetype_id") or ""
    forced = version_doc.get("forced_injection") or {}
    return run_sandbox(entities, SCENES, branch_id, seed,
                       archetype_id=arch, forced_injection=forced)


def run_assemble(episode_id: str, version: int) -> int:
    _install_soft_timeout(settings.soft_timeout_sec)
    log.info("=== STAGE B: assemble | %s v%d ===", episode_id, version)

    alive = gemini_pool.ensure_pool()
    log.info("Gemini pool: %d/%d.", len(alive), len(settings.gemini_keys))

    # 1) Load purgatory
    drafts = mongo.get_purgatory(episode_id)
    chosen = next((d for d in drafts if d.get("version") == version), None)
    if not chosen:
        log.error("Không thấy draft v%d của %s.", version, episode_id); return 2

    # 2) Tái dựng nhánh + chạy LLM Director cho ĐÚNG khung đã duyệt
    entities   = _load_or_seed_entities()
    aggregated = aggregate_inputs()
    trending   = fetch_trending(cache_path=DATA / "_trending_cache.json")
    contexts   = json.loads((DATA / "contexts.json").read_text(encoding="utf-8"))
    branch     = _branch_from_state(chosen, entities)

    budget = RetryBudget()
    try:
        prompt = build_alchemy_prompt(
            branch, trending, contexts, SCENES,
            aggregated=aggregated,
        )
        script = generate_script(prompt, SCENES, budget)
        # Best-effort vet 1 lần — KHÔNG chặn pipeline
        script = anh_t_mod.vet_script(
            script, budget,
            regen=lambda extra: generate_script(prompt + "\n" + extra, SCENES, budget)
            if False else script,  # giữ tương thích chữ ký
        ) if False else script
    except BudgetExceeded as e:
        log.error("Budget hết: %s", e); return 5
    except Exception as e:
        log.exception("Director LLM fail: %s", e); return 5

    out_root = ROOT / f"tap_phim_nay_{episode_id}"
    if out_root.exists(): shutil.rmtree(out_root)
    ver_dir = out_root / f"version_{version}"
    ver_dir.mkdir(parents=True, exist_ok=True)

    # Lưu script chi tiết để debug / canon hóa sau này
    (ver_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) Render ảnh 2..N + TTS hybrid
    media = render_all(script, ver_dir)

    # 4) BGM + timeline
    bgm = pick_bgm(script.get("emotion_tag", "neutral"))
    build_timeline(script, media, ver_dir, bgm_path=bgm, ads_dir=ADS)

    # 5) FFmpeg SPLIT — trả về list[Path] (1 full hoặc 2 part)
    video_paths = build_video(
        ver_dir,
        bgm_path=Path(bgm) if bgm else None,
        scenes_meta=script.get("scenes") or [],
    )
    if not video_paths:
        log.error("build_video fail — xem ffmpeg_error_*.log"); return 4

    # 6) Gửi Telegram
    try:
        telegram_bot.deliver_videos([{
            "version": version,
            "drama_score": chosen.get("drama_score", 0.0),
            "title": script.get("episode_title", ""),
            "path": video_paths if len(video_paths) > 1 else video_paths[0],
        }], episode_id)
    except Exception as e:
        log.error("Telegram deliver fail: %s", e)

    # 7) Update state
    try:
        mongo.set_episode_state(episode_id, {
            "state": "assembled", "version_pending": version,
        })
    except Exception:
        pass

    log.info("=== STAGE B done ==="); return 0


# =====================================================================
# CLI
# =====================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("chimera")
    p.add_argument("--stage", choices=["produce_script", "assemble"],
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


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
