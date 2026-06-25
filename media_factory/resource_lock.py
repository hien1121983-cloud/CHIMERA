"""Semaphore + RAM monitor (Va C-05: vong lap, khong de quy)."""
import asyncio
import logging

from config.settings import settings

logger = logging.getLogger(__name__)


class ResourceLock:
    """Gioi han tai nguyen de chong tran RAM khi tai media."""

    MAX_WAIT_ITERATIONS = 60  # 60 x 5s = 5 phut

    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.RESOURCE_LOCK_MAX_CONCURRENT)
        self.max_ram_percent = settings.RESOURCE_LOCK_MAX_RAM_PERCENT

    def _ram_ok(self) -> bool:
        try:
            import psutil

            return psutil.virtual_memory().percent < self.max_ram_percent
        except Exception:
            return True

    async def acquire(self):
        await self.semaphore.acquire()
        # Va C-05: vong lap, KHONG de quy
        iterations = 0
        while not self._ram_ok():
            if iterations >= self.MAX_WAIT_ITERATIONS:
                logger.warning(
                    f"[ResourceLock] RAM van cao suot "
                    f"{self.MAX_WAIT_ITERATIONS * 5}s. Huy tac vu."
                )
                self.semaphore.release()
                raise RuntimeError("[ResourceLock] RAM qua tai, huy tac vu.")
            logger.warning(
                f"[ResourceLock] RAM > {self.max_ram_percent}%, cho 5s "
                f"(iter {iterations + 1})"
            )
            await asyncio.sleep(5)
            iterations += 1

    def release(self):
        self.semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.release()
