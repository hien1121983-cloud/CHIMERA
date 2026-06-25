"""Orchestrator cho Giai doan 2 (Sang tao + Kiem duyet + Showrunner)."""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from core.logger import setup_logging
from creative.a1_alchemist import A1Alchemist
from creative.voice_mapping import VoiceMapper
from audit.t3_auditor import T3Auditor
from telegram_bot.showrunner_bot import (
    launch_webhook_in_background,
    send_approval_request,
    wait_for_showrunner,
)
from telegram_bot.message_formatter import format_world_stats, format_script_summary
from telegram_bot.handlers import parse_callback
from post_approval.world_updater import PostApprovalHandler

logger = logging.getLogger(__name__)


async def run_stage_2(master_payload: dict) -> dict:
    logger.info("=== BAT DAU GIAI DOAN 2: SANG TAO & KIEM DUYET ===")

    # 1. A1 sinh 3 drafts
    alchemist = A1Alchemist()
    drafts = alchemist.generate_3_drafts(master_payload)

    # 2. Auditor kiem duyet
    mandatory = (
        master_payload.get("context_slice_v2", {}).get("layer_6_mandatory_tasks", [])
    )
    auditor = T3Auditor()
    audit_result = auditor.audit(drafts, mandatory)
    best_draft = audit_result.get("draft")

    # 3. Kiem tra ket qua audit
    if best_draft is None:
        raise RuntimeError("[Stage2] Khong co draft nao pass audit.")

    # 4. Map voice cho nhan vat
    voice_mapper = VoiceMapper()
    all_characters = (
        master_payload.get("protagonists", []) + master_payload.get("supporting_cast", [])
    )
    char_names = [
        c.get("name") for c in all_characters if isinstance(c, dict) and c.get("name")
    ]
    voice_mapping = voice_mapper.build_mapping(char_names)

    # 5. Dong goi Master_Script
    master_script = {
        "meta": {
            "pipeline_version": "5.0.1",
            "episode_number": master_payload.get("meta", {}).get("episode_number"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "similarity_score": audit_result.get("similarity"),
            "approved": False,
        },
        "script": {
            "synopsis": best_draft.get("synopsis", ""),
            "scenes": best_draft.get("scenes", []),
        },
        "voice_mapping": voice_mapping,
        "resolved_hooks": best_draft.get("resolved_hooks", []),
        "world_state_deltas": best_draft.get("world_state_deltas", []),
    }

    # 6. Khoi dong webhook + gui yeu cau duyet
    launch_webhook_in_background()
    stats = format_world_stats(master_payload)
    summary = format_script_summary(master_script)
    await send_approval_request(
        f"{summary}\n\n<b>World stats:</b> {json.dumps(stats, ensure_ascii=False)}"
    )

    # 7. Ngu cho Showrunner
    logger.info("[Stage2] Cho Showrunner duyet...")
    raw_decision = await wait_for_showrunner()
    decision = parse_callback(raw_decision)

    # 8. Xu ly quyet dinh
    post_handler = PostApprovalHandler()
    if decision == "APPROVE":
        logger.info("[Stage2] Showrunner DUYET")
        master_script["meta"]["approved"] = True
        master_script["meta"]["approved_at"] = datetime.utcnow().isoformat() + "Z"
        post_handler.process_approval(master_script)
    elif decision == "REWRITE_EXTREME":
        logger.info("[Stage2] Showrunner yeu cau viet lai")
        post_handler.handle_rewrite_extreme(master_payload)
    else:
        logger.info("[Stage2] Showrunner TU CHOI")

    # 9. Luu Master_Script
    Path("cache").mkdir(exist_ok=True)
    with open("cache/master_script_latest.json", "w", encoding="utf-8") as f:
        json.dump(master_script, f, ensure_ascii=False, indent=2, default=str)

    return master_script


async def main():
    payload_path = "cache/master_payload_latest.json"
    if not Path(payload_path).exists():
        logger.error("Chua co Master_Payload. Chay Ban 1 (main_pipeline.py) truoc.")
        return

    with open(payload_path, "r", encoding="utf-8") as f:
        master_payload = json.load(f)

    try:
        master_script = await run_stage_2(master_payload)
        print(
            f"\nOK Giai doan 2 thanh cong. "
            f"Episode: {master_script['meta']['episode_number']}"
        )
    except Exception as e:
        print(f"\nFAIL Giai doan 2 that bai: {e}")
        raise


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
