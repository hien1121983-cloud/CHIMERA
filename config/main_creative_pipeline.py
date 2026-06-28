"""Orchestrator cho Giai đoạn 2 (Sáng tạo + Kiểm duyệt + Showrunner).

Luồng nhân vật mới:
  [CharacterFactory] Đúc nhân vật mới cho tập
       ↓ (mỗi nhân vật: T0a dice → A0 lock → MongoDB)
  [A1 Alchemist] Viết kịch bản dựa trên nhân vật ĐÃ KHÓA
       ↓
  [T3 Auditor] Kiểm tra similarity
       ↓
  [Showrunner Bot] Duyệt qua Telegram
       ↓
  [PostApprovalHandler] Cập nhật World State
"""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from core.logger import setup_logging
from config.settings import settings
from fetchers.character_factory import CharacterFactory
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
    logger.info("=" * 60)
    logger.info("=== BẮT ĐẦU GIAI ĐOẠN 2: SÁNG TẠO & KIỂM DUYỆT ===")
    logger.info("=" * 60)

    # ══════════════════════════════════════════════════════════════════════════
    # BƯỚC 0A: CharacterFactory — Đúc dàn nhân vật cho tập này
    # (T0a dice roll → randomize stats → tên VN → A0 inline → MongoDB)
    # Đảm bảo A1 KHÔNG bao giờ tự ý tạo nhân vật.
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("[Stage2] Bước 0A: CharacterFactory đúc dàn nhân vật...")
    factory = CharacterFactory()
    episode_cast = factory.mint_episode_cast(
        n_protagonists=2,
        n_supporting=3,
    )

    # Inject vào payload — ghi đè bất kỳ nhân vật nào Stage 1 đưa vào
    master_payload["protagonists"] = episode_cast["protagonists"]
    master_payload["supporting_cast"] = episode_cast["supporting_cast"]

    logger.info(
        f"[Stage2] Dàn nhân vật tập {master_payload.get('meta', {}).get('episode_number', '?')}: "
        + ", ".join(
            f"{c['name']} ({c['blueprint_id']})"
            for c in episode_cast["protagonists"] + episode_cast["supporting_cast"]
        )
    )

    # ══════════════════════════════════════════════════════════════════════════
    # BƯỚC 0B: A0 Safety Net — Khóa bất kỳ nhân vật sót nào chưa có visual
    # (NPC từ world state, nhân vật lịch sử trong context_slice, v.v.)
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("[Stage2] Bước 0B: A0 safety-net scan nhân vật sót...")
    artist = A0CharacterArtist()
    master_payload = artist.process_payload_characters(master_payload)

    # ══════════════════════════════════════════════════════════════════════════
    # BƯỚC 1: A1 Alchemist — Viết 3 bản nháp kịch bản
    # Lúc này A1 nhận nhân vật ĐÃ CÓ ĐẦY ĐỦ DNA: archetype, philosophy,
    # inner_conflicts, fatal_flaw, micro_habits, stats đã roll, visual đã khóa.
    # ══════════════════════════════════════════════════════════════════════════
    mandatory = (
        master_payload.get("context_slice_v2", {})
        .get("layer_6_mandatory_tasks", [])
    )
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

        logger.info(
            f"[Stage2] Audit attempt {attempt}: "
            f"status={status}, similarity={audit_result.get('similarity')}"
        )

        if status in ("approved", "needs_review"):
            break
        elif status == "should_retry" and attempt < settings.AUDITOR_MAX_RETRY:
            warning_msg = audit_result.get("reason")
            continue
        elif status == "rejected":
            raise RuntimeError(
                f"[Stage2] Audit rejected hoàn toàn. Reason: {audit_result.get('reason')}"
            )
        else:
            break

    if not drafts:
        raise RuntimeError("[Stage2] Không có drafts nào được tạo ra sau Audit.")

    # BƯỚC 2: Map voice cho nhân vật (truyền full dict để VoiceMapper khớp archetype)
    voice_mapper = VoiceMapper()
    all_characters = (
        master_payload.get("protagonists", []) +
        master_payload.get("supporting_cast", [])
    )
    voice_mapping = voice_mapper.build_mapping(all_characters)

    # BƯỚC 3: Xuất file 3 bản nháp để đọc
    drafts_file = export_drafts_to_txt(drafts, "cache/all_drafts.txt")

    # BƯỚC 4: Khởi động webhook + gửi yêu cầu duyệt
    launch_webhook_in_background()
    stats = format_world_stats(master_payload)

    audit_warning = ""
    if last_audit_result.get("status") in ("needs_review", "should_retry"):
        sim = last_audit_result.get("similarity", 0)
        audit_warning = (
            f"\n\n⚠️ <b>Cảnh báo:</b> Similarity={sim:.3f} (cao hơn ngưỡng). "
            f"{last_audit_result.get('reason', '')}"
        )

    # Build danh sách nhân vật để hiển thị trong caption Telegram
    cast_summary = " | ".join(
        f"{c['name']} [{c.get('archetype_name', '').split('(')[0].strip()}]"
        for c in all_characters
    )

    test_mode_notice = (
        "⚠️ CHẾ ĐỘ AUTO-TEST: Tự động duyệt Bản 1 (TEST_MODE=True).\n"
        if settings.TEST_MODE
        else "✅ PRODUCTION: Vui lòng bấm nút bên dưới để duyệt kịch bản.\n"
    )
    caption = (
        f"🎬 <b>Tập {master_payload.get('meta', {}).get('episode_number', '?')} "
        f"ĐÃ CÓ 3 BẢN NHÁP</b>\n"
        f"🎭 <b>Dàn nhân vật:</b> {cast_summary}\n"
        f"Trạng thái kiểm duyệt: {last_audit_result.get('status')}{audit_warning}\n"
        f"{test_mode_notice}"
        f"<b>World stats:</b> {json.dumps(stats, ensure_ascii=False)}"
    )

    await send_approval_request(caption, document_path=drafts_file)

    # BƯỚC 5: Lấy quyết định — TEST_MODE tự động, Production hỏi Showrunner thật
    post_handler = PostApprovalHandler()

    if settings.TEST_MODE:
        logger.info("[Stage2] TEST_MODE=True → Tự động chọn bản nháp số 1 (APPROVE_0).")
        decision = "APPROVE_0"
    else:
        logger.info("[Stage2] Chờ Showrunner duyệt qua Telegram (poll MongoDB)...")
        decision = await wait_for_showrunner()
        logger.info(f"[Stage2] Showrunner quyết định: {decision}")

    # BƯỚC 6: Xử lý quyết định và đóng gói Kịch bản
    master_script = None

    if decision == "REJECT":
        raise RuntimeError("[Stage2] Showrunner đã TỪ CHỐI toàn bộ kịch bản. Pipeline dừng.")

    elif decision == "REWRITE_EXTREME":
        logger.warning("[Stage2] Showrunner yêu cầu VIẾT LẠI (Cực đoan) — bơm nội tâm và dừng.")
        updated_payload = post_handler.handle_rewrite_extreme(master_payload)
        # Lưu payload đã escalate để lần chạy lại Stage 2 kế tiếp dùng
        Path("cache").mkdir(exist_ok=True)
        with open("cache/master_payload_latest.json", "w", encoding="utf-8") as f:
            import json as _json
            _json.dump(updated_payload, f, ensure_ascii=False, indent=2, default=str)
        raise RuntimeError(
            "[Stage2] REWRITE_EXTREME: Payload đã được bơm nội tâm cực đoan. "
            "Chạy lại Stage 2 để sinh kịch bản mới."
        )

    elif decision.startswith("APPROVE_"):
        draft_idx = int(decision.split("_")[1])
        selected_draft = drafts[draft_idx]
        logger.info(f"[Stage2] {'Tự động' if settings.TEST_MODE else 'Showrunner'} CHỌN BẢN SỐ {draft_idx + 1}")

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
                # Lưu thông tin dàn nhân vật vào meta để audit trail
                "episode_cast": [
                    {
                        "character_id": c.get("character_id"),
                        "name": c.get("name"),
                        "blueprint_id": c.get("blueprint_id"),
                        "role": c.get("role"),
                    }
                    for c in all_characters
                ],
            },
            "script": {
                "synopsis": selected_draft.get("synopsis", ""),
                "scenes": selected_draft.get("scenes", []),
            },
            "voice_mapping": voice_mapping,
            "resolved_hooks": selected_draft.get("resolved_hooks", []),
            "world_state_deltas": selected_draft.get("world_state_deltas", []),
            # Truyền sang Stage 3 để A2/VisualLock dùng
            "protagonists": master_payload.get("protagonists", []),
            "supporting_cast": master_payload.get("supporting_cast", []),
        }

        post_handler.process_approval(master_script)

        Path("cache").mkdir(exist_ok=True)
        with open("cache/master_script_latest.json", "w", encoding="utf-8") as f:
            json.dump(master_script, f, ensure_ascii=False, indent=2, default=str)

        logger.info(
            f"[Stage2] ✅ Kịch bản tập {master_script['meta']['episode_number']} "
            f"đã được duyệt và lưu."
        )
        return master_script

    else:
        raise RuntimeError(f"[Stage2] Lệnh không xác định từ Showrunner: '{decision}'")


async def main():
    payload_path = "cache/master_payload_latest.json"
    if not Path(payload_path).exists():
        logger.error("Chưa có Master_Payload. Chạy Bản 1 (main_pipeline.py) trước.")
        return

    with open(payload_path, "r", encoding="utf-8") as f:
        master_payload = json.load(f)

    try:
        master_script = await run_stage_2(master_payload)
        print(f"\nOK Giai đoạn 2 thành công. Episode: {master_script['meta']['episode_number']}")
    except Exception as e:
        print(f"\nFAIL Giai đoạn 2 thất bại: {e}")
        raise


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
