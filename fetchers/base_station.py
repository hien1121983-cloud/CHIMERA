"""BaseStation: contract chung cho moi tram T0x."""
import time
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class StationResult:
    station_id: str
    success: bool
    data: Optional[Any]
    error: Optional[str]
    fallback_used: bool
    elapsed_ms: int


class BaseStation:
    """Abstract base cho moi tram T0x."""

    station_id: str = "T0x"

    def run(self) -> StationResult:
        start = time.time()
        try:
            data = self._execute()
            self._cache_to_sqlite(data)
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[{self.station_id}] OK Thanh cong ({elapsed}ms)")
            return StationResult(self.station_id, True, data, None, False, elapsed)
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            logger.error(f"[{self.station_id}] Loi: {e}")
            fallback = self._load_sqlite_cache()
            if fallback:
                logger.warning(f"[{self.station_id}] Dung fallback SQLite")
                return StationResult(self.station_id, True, fallback, str(e), True, elapsed)
            return StationResult(self.station_id, False, None, str(e), False, elapsed)

    def _execute(self):
        """Override: logic chinh cua tram."""
        raise NotImplementedError

    def _load_sqlite_cache(self):
        """Override: doc cache khi fail."""
        from core.db_client import ChimeraDB

        db = ChimeraDB()
        return db._read_from_sqlite(self.station_id)

    def _cache_to_sqlite(self, data):
        """Override: ghi cache khi success."""
        from core.db_client import ChimeraDB

        db = ChimeraDB()
        try:
            db._cache_to_sqlite(
                self.station_id, data if isinstance(data, list) else [data]
            )
        except Exception as e:
            logger.debug(f"[{self.station_id}] Bo qua cache: {e}")
