"""Xoa thu muc tam BAT BUOC (async) sau khi giao hang."""
import os
import time
import shutil
import logging

logger = logging.getLogger(__name__)


class GarbageCollector:
    @staticmethod
    async def cleanup(temp_dir: str) -> bool:
        """Xoa sach thu muc tam. Neu fail -> log CRITICAL + Telegram."""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            logger.info(f"[GC] Da xoa {temp_dir}")
            return True
        except Exception as e:
            logger.critical(f"[GC] KHONG xoa duoc {temp_dir}: {e}")
            try:
                from core.helpers import send_telegram_alert

                await send_telegram_alert(f"[GC] CRITICAL: khong xoa duoc {temp_dir}: {e}")
            except Exception:
                pass
            return False

    @staticmethod
    def cleanup_stale(base_temp_dir: str = "./temp", max_age_hours: float = 24):
        """Xoa cac thu muc tam cu (cron)."""
        if not os.path.exists(base_temp_dir):
            return

        now = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned = 0
        for name in os.listdir(base_temp_dir):
            path = os.path.join(base_temp_dir, name)
            if os.path.isdir(path) and (now - os.path.getmtime(path)) > max_age_seconds:
                try:
                    shutil.rmtree(path)
                    cleaned += 1
                except Exception as e:
                    logger.error(f"[GC] Khong xoa duoc {path}: {e}")
        logger.info(f"[GC] Don {cleaned} thu muc cu")
