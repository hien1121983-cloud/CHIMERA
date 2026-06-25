"""Tram T7: Gui MP4 qua Telegram + don rac."""
import os
import logging

from delivery.garbage_collector import GarbageCollector

logger = logging.getLogger(__name__)


class T7Courier:
    async def deliver(self, video_paths: list, episode_number: int, report: dict) -> bool:
        """Gui video part qua Telegram, sau do don rac.

        FIX #10: Truoc day GarbageCollector.cleanup() luon chay du delivery
        thanh cong hay that bai. Khi delivery that bai, xoa thu muc tam ngay
        lap tuc khien mat toan bo vat lieu de debug (anh, audio, video parts).
        Nay chi don rac khi delivery THANH CONG. Khi that bai, giu lai thu
        muc va log ro duong dan de developer kiem tra.
        Cleanup_stale() se tu don sau 24 gio (chay qua cron job rieng).
        """
        import telegram

        bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        temp_dir = os.path.dirname(video_paths[0]) if video_paths else None

        try:
            caption = (
                f"<b>Episode {episode_number}</b> da render xong.\n"
                f"Images: {report.get('images_count')} | "
                f"Audio: {report.get('audio_count')} | "
                f"Fallback: {report.get('fallback_count')}"
            )
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")

            for i, video_path in enumerate(video_paths):
                with open(video_path, "rb") as f:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=f"Part {i + 1}/{len(video_paths)}",
                    )
            logger.info(f"[T7] Da gui {len(video_paths)} video parts")
            success = True
        except Exception as e:
            logger.critical(f"[T7] Loi gui video: {e}")
            success = False

        # FIX #10: Chi don rac khi delivery THANH CONG.
        if temp_dir:
            if success:
                await GarbageCollector.cleanup(temp_dir)
            else:
                # Giu lai thu muc de debug, cleanup_stale() se don sau 24h.
                logger.warning(
                    f"[T7] Delivery that bai - GIU LAI {temp_dir} de debug. "
                    f"Thu muc se tu dong bi xoa sau 24h boi cleanup_stale(). "
                    f"De xoa ngay: GarbageCollector.cleanup('{temp_dir}')"
                )

        return success
