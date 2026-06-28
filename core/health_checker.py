"""Async health check cho cac pool API key."""
import asyncio
import logging

import aiohttp

from core.credential_manager import GEMINI_POOL, CLAUDE_POOL

logger = logging.getLogger(__name__)


async def ping_gemini(key: str, session: aiohttp.ClientSession) -> bool:
    """Kiem tra mot Gemini key voi timeout 5 giay."""
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        async with session.get(
            url,
            headers={"x-goog-api-key": key},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"[HealthCheck] Gemini key {key[:10]}... loi: {e}")
        return False


async def ping_claude(key: str, session: aiohttp.ClientSession) -> bool:
    """Kiem tra mot Claude key voi timeout 5 giay."""
    url = "https://api.anthropic.com/v1/models"
    try:
        async with session.get(
            url,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01"
            },
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            # Voi Anthropic, chi can ma loi khac 401 (Unauthorized) la key con hoat dong.
            return resp.status != 401
    except Exception as e:
        logger.error(f"[HealthCheck] Claude key {key[:10]}... loi: {e}")
        return False


async def run_startup_health_check() -> dict:
    """Chay health check khi pipeline khoi dong."""
    report = {"gemini": {"alive": 0, "dead": 0}, "claude": {"alive": 0, "dead": 0}}

    async with aiohttp.ClientSession() as session:
        # 1. Kiem tra Gemini Pool
        gemini_tasks = [ping_gemini(k, session) for k in GEMINI_POOL.keys]
        gemini_results = await asyncio.gather(*gemini_tasks, return_exceptions=True)
        for key, ok in zip(GEMINI_POOL.keys, gemini_results):
            if ok is True:
                report["gemini"]["alive"] += 1
            else:
                report["gemini"]["dead"] += 1
                GEMINI_POOL.mark_failed(key)

        # 2. Kiem tra Claude Pool
        claude_tasks = [ping_claude(k, session) for k in CLAUDE_POOL.keys]
        claude_results = await asyncio.gather(*claude_tasks, return_exceptions=True)
        for key, ok in zip(CLAUDE_POOL.keys, claude_results):
            if ok is True:
                report["claude"]["alive"] += 1
            else:
                report["claude"]["dead"] += 1
                CLAUDE_POOL.mark_failed(key)

    if GEMINI_POOL.active_count == 0:
        raise RuntimeError("[HealthCheck] CRITICAL: Toan bo Gemini key dead.")
    if CLAUDE_POOL.active_count == 0:
        raise RuntimeError("[HealthCheck] CRITICAL: Toan bo Claude key dead.")

    logger.info(f"[HealthCheck] Ket qua: {report}")
    return report
