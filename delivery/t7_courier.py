"""Tram T7: Gui MP4 qua Telegram + don rac."""
import os
import logging

from delivery.garbage_collector import GarbageCollector

logger = logging.getLogger(__name__)


class T7Courier:
    async def deliver(self, video_paths: list, episode_number: int, report: dict) -> bool:
        """Gui video part qua Telegram, sau do don rac BAT BUOC."""
        import telegram

        bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

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

        # Don rac BAT BUOC
        temp_dir = os.path.dirname(video_paths[0]) if video_paths else None
        if temp_dir:
            await GarbageCollector.cleanup(temp_dir)

        return success
