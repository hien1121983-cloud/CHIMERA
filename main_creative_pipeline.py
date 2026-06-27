"""Orchestrator cho Giai doan 2 (Sang tao + Kiem duyet + Showrunner)."""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from core.logger import setup_logging
from config.settings import settings
from creative.a0_character_artist import A0CharacterArtist
from creative.a1_alchemist import A1Alchemist
from creative.voice_mapping import VoiceMapper
from audit.t3_auditor import T3Auditor
from telegram_bot.showrunner_bot import (
    launch_webhook_in_background,
    send_approval_request,
    wait_for_showrunner,
)
from telegram_bot.message_formatter import format_world_stats, export_drafts_to_txt
from telegram_bot.handlers import parse_callback
from post_approval.world_updater import PostApprovalHandler

logger = logging.getLogger(__name__)

async def run_stage_2(master_payload: dict) -> dict:
    logger.info("=== BAT DAU GIAI DOAN 2: SANG TAO & KIEM DUYET ===")

    # 0. KÍCH HOẠT A0 (VẼ VÀ KHÓA HÌNH ẢNH BẰNG AI + DB PYTHON)
    logger.info("[Stage2] Khoi dong A0 de kiem tra va ve ngoai hinh nhan vat...")
    artist = A0CharacterArtist()
    master_payload = artist.process_payload_characters(master_payload)

    # 1. Chuan bi context cho A1
    mandatory = master_payload.get("context_slice_v2", {}).get("layer_6_mandatory_tasks", [])
    alchemist = A1Alchemist()
    auditor = T3Auditor()

    last_audit_result = None
    warning_msg = None
    drafts = []

    for attempt in range(1, settings.AUDITOR_MAX_RETRY + 1):
        logger.info(f"[Stage2] A1 + Audit attempt {attempt}/{settings.AUDITOR_MAX_RETRY}")
        if warning_msg:
            drafts = alchemist.generate_3_drafts_with_warning(master_payload, warning_msg)
        else:
            drafts = alchemist.generate_3_drafts(master_payload)

        audit_result = auditor.audit(drafts, mandatory)
        last_audit_result = audit_result
        status = audit_result.get("status")

        logger.info(f"[Stage2] Audit attempt {attempt}: status={status}, similarity={audit_result.get('similarity')}")

        if status in ("approved", "needs_review"):
            break
        elif status == "should_retry" and attempt < settings.AUDITOR_MAX_RETRY:
            warning_msg = audit_result.get('reason')
            continue
        elif status == "rejected":
            raise RuntimeError(f"[Stage2] Audit rejected hoan toan. Reason: {audit_result.get('reason')}")
        else:
            break

    if not drafts:
        raise RuntimeError("[Stage2] Khong co drafts nao duoc tao ra sau Audit.")

    # 3. Map voice cho nhan vat
    voice_mapper = VoiceMapper()
    all_characters = master_payload.get("protagonists", []) + master_payload.get("supporting_cast", [])
    
    char_names = []
    for c in all_characters:
        if isinstance(c, dict) and c.get("name"):
            char_names.append(c.get("name"))

    voice_mapping = voice_mapper.build_mapping(char_names)

    # 4. Xuat file 3 ban nhap de doc 
    drafts_file = export_drafts_to_txt(drafts, "cache/all_drafts.txt")

    # 5. Khoi dong webhook + gui yeu cau duyet
    launch_webhook_in_background()
    stats = format_world_stats(master_payload)

    audit_warning = ""
    if last_audit_result.get("status") in ("needs_review", "should_retry"):
        sim = last_audit_result.get("similarity", 0)
        audit_warning = f"\n\n⚠️ <b>Cảnh báo:</b> Similarity={sim:.3f} (cao hon nguong). {last_audit_result.get('reason', '')}"

    caption = (
        f"🎬 <b>Tập {master_payload.get('meta', {}).get('episode_number', '?')} ĐÃ CÓ 3 BẢN NHÁP</b>\n"
        f"Trạng thái kiểm duyệt: {last_audit_result.get('status')}{audit_warning}\n"
        f"⚠️ HỆ THỐNG ĐANG Ở CHẾ ĐỘ AUTO-TEST: Sẽ tự động duyệt Bản 1 và chuyển thẳng qua Xưởng Media để Render.\n"
        f"<b>World stats:</b> {json.dumps(stats, ensure_ascii=False)}"
    )

    await send_approval_request(caption, document_path=drafts_file)

    # 6. [CHẾ ĐỘ TEST] BỎ QUA VIỆC CHỜ TELEGRAM, TỰ ĐỘNG CHỌN BẢN 1
    logger.info("[Stage2] CHE DO TEST: Tu dong chon ban nhap so 1 (APPROVE_0) de chuyen sang Ban 3.")
    decision = "APPROVE_0"

    # 7. Xu ly quyet dinh va Dong goi Kich ban
    post_handler = PostApprovalHandler()
    master_script = None

    if decision.startswith("APPROVE_"):
        draft_idx = int(decision.split("_")[1])
        selected_draft = drafts[draft_idx]
        logger.info(f"[Stage2] He thong tu dong CHON BAN SO {draft_idx + 1}")

        master_script = {
            "meta": {
                "pipeline_version": "5.0.1",
                "episode_number": master_payload.get("meta", {}).get("episode_number"),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "similarity_score": last_audit_result.get("similarity"),
                "audit_status": last_audit_result.get("status"),
                "audit_reason": last_audit_result.get("reason"),
                "approved": True,
                "approved_at": datetime.utcnow().isoformat() + "Z",
            },
            "script": {
                "synopsis": selected_draft.get("synopsis", ""),
                "scenes": selected_draft.get("scenes", []),
            },
            "voice_mapping": voice_mapping,
            "resolved_hooks": selected_draft.get("resolved_hooks", []),
            "world_state_deltas": selected_draft.get("world_state_deltas", []),
        }

        post_handler.process_approval(master_script)

        Path("cache").mkdir(exist_ok=True)
        with open("cache/master_script_latest.json", "w", encoding="utf-8") as f:
            json.dump(master_script, f, ensure_ascii=False, indent=2, default=str)

        return master_script

    else:
        raise RuntimeError("Khong the xy ly lenh Auto-Test.")

async def main():
    payload_path = "cache/master_payload_latest.json"
    if not Path(payload_path).exists():
        logger.error("Chua co Master_Payload. Chay Ban 1 (main_pipeline.py) truoc.")
        return

    with open(payload_path, "r", encoding="utf-8") as f:
        master_payload = json.load(f)

    try:
        master_script = await run_stage_2(master_payload)
        print(f"\nOK Giai doan 2 thanh cong. Episode: {master_script['meta']['episode_number']}")
    except Exception as e:
        print(f"\nFAIL Giai doan 2 that bai: {e}")
        raise

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
