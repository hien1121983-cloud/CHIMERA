"""Async health check cho cac pool API key."""
import asyncio
import logging

import aiohttp

from core.credential_manager import GEMINI_POOL, GROQ_POOL

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


async def ping_groq(key: str, session: aiohttp.ClientSession) -> bool:
    """Kiem tra mot Groq key voi timeout 5 giay."""
    url = "https://api.groq.com/openai/v1/models"
    try:
        async with session.get(
            url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"[HealthCheck] Groq key {key[:10]}... loi: {e}")
        return False


async def run_startup_health_check() -> dict:
    """Chay health check khi pipeline khoi dong."""
    report = {"gemini": {"alive": 0, "dead": 0}, "groq": {"alive": 0, "dead": 0}}

    async with aiohttp.ClientSession() as session:
        gemini_tasks = [ping_gemini(k, session) for k in GEMINI_POOL.keys]
        gemini_results = await asyncio.gather(*gemini_tasks, return_exceptions=True)
        for key, ok in zip(GEMINI_POOL.keys, gemini_results):
            if ok is True:
                report["gemini"]["alive"] += 1
            else:
                report["gemini"]["dead"] += 1
                GEMINI_POOL.mark_failed(key)

        groq_tasks = [ping_groq(k, session) for k in GROQ_POOL.keys]
        groq_results = await asyncio.gather(*groq_tasks, return_exceptions=True)
        for key, ok in zip(GROQ_POOL.keys, groq_results):
            if ok is True:
                report["groq"]["alive"] += 1
            else:
                report["groq"]["dead"] += 1
                GROQ_POOL.mark_failed(key)

    if GEMINI_POOL.active_count == 0:
        raise RuntimeError("[HealthCheck] CRITICAL: Toan bo Gemini key dead.")
    if GROQ_POOL.active_count == 0:
        raise RuntimeError("[HealthCheck] CRITICAL: Toan bo Groq key dead.")

    logger.info(f"[HealthCheck] Ket qua: {report}")
    return report
