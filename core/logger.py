"""Structured logging cho toan pipeline."""
import logging
import os


def setup_logging(level: str = None) -> None:
    """Cau hinh logging chuan cho toan he thong."""
    level = level or os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
