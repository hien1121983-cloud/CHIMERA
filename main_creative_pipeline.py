"""Orchestrator cho Giai doan 2 (Sang tao + Kiem duyet + Showrunner)."""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from core.logger import setup_logging
from config.settings import settings
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

    mandatory = (
        master_payload.get("context_slice_v2", {}).get("layer_6_mandatory_tasks", [])
    )

    alchemist = A1Alchemist()
    auditor = T3Auditor()

    # FIX #11: Vong lap retry su dung AUDITOR_MAX_RETRY.
    # Truoc day chi goi A1 mot lan, neu all 3 drafts fail similarity
    # thi van gui len Showrunner ma khong co co hoi viet lai.
    # Nay: neu audit tra ve "should_retry", goi lai A1 toi da max_retry lan
    # truoc khi de Showrunner quyet dinh tren draft tot nhat con lai.
    best_draft = None
    last_audit_result = None

    for attempt in range(1, settings.AUDITOR_MAX_RETRY + 1):
        logger.info(f"[Stage2] A1 + Audit attempt {attempt}/{settings.AUDITOR_MAX_RETRY}")

        # 1. A1 sinh 3 drafts
        drafts = alchemist.generate_3_drafts(master_payload)

        # 2. Auditor kiem duyet
        audit_result = auditor.audit(drafts, mandatory)
        last_audit_result = audit_result
        status = audit_result.get("status")

        logger.info(
            f"[Stage2] Audit attempt {attempt}: status={status}, "
            f"similarity={audit_result.get('similarity')}"
        )

        if status == "approved":
            # Draft tot: thoat khoi vong lap ngay
            best_draft = audit_result.get("draft")
            logger.info(f"[Stage2] Audit PASS o attempt {attempt}.")
            break
        elif status == "needs_review":
            # Similarity cao nhung co the duyet duoc -> Showrunner quyet dinh
            best_draft = audit_result.get("draft")
            logger.warning(
                f"[Stage2] Audit needs_review (attempt {attempt}). "
                f"Reason: {audit_result.get('reason')}. "
                f"Gui len Showrunner."
            )
            break
        elif status == "should_retry" and attempt < settings.AUDITOR_MAX_RETRY:
            # Similarity qua cao -> retry A1
            logger.warning(
                f"[Stage2] Audit should_retry (attempt {attempt}). "
                f"Reason: {audit_result.get('reason')}. "
                f"Goi lai A1..."
            )
            continue
        elif status == "rejected":
            # Tat ca drafts thieu mandatory tasks -> khong the tiep tuc
            raise RuntimeError(
                f"[Stage2] Audit rejected hoan toan. "
                f"Reason: {audit_result.get('reason')}"
            )
        else:
            # should_retry nhung da het luot -> dung draft tot nhat
            best_draft = audit_result.get("draft")
            logger.critical(
                f"[Stage2] Het {settings.AUDITOR_MAX_RETRY} lan retry. "
                f"Dung draft tot nhat con lai de Showrunner quyet dinh. "
                f"Similarity={audit_result.get('similarity'):.3f}"
            )
            break

    if best_draft is None:
        raise RuntimeError("[Stage2] Khong co draft nao kha dung sau khi audit.")

    # 3. Map voice cho nhan vat
    voice_mapper = VoiceMapper()
    all_characters = (
        master_payload.get("protagonists", []) + master_payload.get("supporting_cast", [])
    )
    char_names = [
        c.get("name") for c in all_characters if isinstance(c, dict) and c.get("name")
    ]
    voice_mapping = voice_mapper.build_mapping(char_names)

    # 4. Dong goi Master_Script
    master_script = {
        "meta": {
            "pipeline_version": "5.0.1",
            "episode_number": master_payload.get("meta", {}).get("episode_number"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "similarity_score": last_audit_result.get("similarity"),
            "audit_status": last_audit_result.get("status"),
            "audit_reason": last_audit_result.get("reason"),
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

    # 5. Khoi dong webhook + gui yeu cau duyet
    launch_webhook_in_background()
    stats = format_world_stats(master_payload)
    summary = format_script_summary(master_script)

    # Them canh bao similarity neu can
    audit_warning = ""
    if last_audit_result.get("status") in ("needs_review", "should_retry"):
        sim = last_audit_result.get("similarity", 0)
        audit_warning = f"\n\n⚠️ <b>Canh bao:</b> Similarity={sim:.3f} (cao hon nguong {settings.SIMILARITY_THRESHOLD:.2f}). {last_audit_result.get('reason', '')}"

    await send_approval_request(
        f"{summary}{audit_warning}\n\n<b>World stats:</b> {json.dumps(stats, ensure_ascii=False)}"
    )

    # 6. Ngu cho Showrunner (FIX #2: co timeout tu settings)
    logger.info("[Stage2] Cho Showrunner duyet...")
    try:
        raw_decision = await wait_for_showrunner()
    except TimeoutError as e:
        logger.critical(f"[Stage2] {e}")
        raise RuntimeError(str(e))

    decision = parse_callback(raw_decision)

    # 7. Xu ly quyet dinh
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

    # 8. Luu Master_Script
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
