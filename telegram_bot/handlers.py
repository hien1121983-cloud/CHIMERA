"""Xu ly callback queries tu Telegram."""
import logging

logger = logging.getLogger(__name__)

# Thay doi quyet dinh de chap nhan 1 trong 3 ban
VALID_DECISIONS = {"APPROVE_0", "APPROVE_1", "APPROVE_2", "REJECT", "REWRITE_EXTREME"}

def parse_callback(callback_data: str) -> str:
    """Chuan hoa callback data thanh quyet dinh hop le."""
    decision = (callback_data or "").strip().upper()
    if decision not in VALID_DECISIONS:
        logger.warning(f"[Handlers] Callback khong hop le: {callback_data}")
        return "REJECT"
    return decision
