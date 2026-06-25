"""Cac ham helper dung chung trong toan pipeline."""
import os
import logging

from core.db_client import ChimeraDB

logger = logging.getLogger(__name__)

# === Singleton Telegram Bot ===
_telegram_bot = None


def _get_telegram_bot():
    global _telegram_bot
    if _telegram_bot is None:
        import telegram

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN chua duoc cau hinh")
        _telegram_bot = telegram.Bot(token=token)
    return _telegram_bot


async def send_telegram_alert(message: str):
    """Gui canh bao qua Telegram (async)."""
    bot = _get_telegram_bot()
    try:
        await bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            text=message,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"[Telegram] Khong gui duoc alert: {e}")


def send_telegram_alert_sync(message: str):
    """Wrapper sync cho send_telegram_alert (dung trong sync context)."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(send_telegram_alert(message))
        else:
            asyncio.run(send_telegram_alert(message))
    except RuntimeError:
        asyncio.run(send_telegram_alert(message))
    except Exception as e:
        logger.error(f"[Telegram Sync] Loi: {e}")


def get_current_episode() -> int:
    """Lay so tap hien tai tu Cum Nao 3 (Canon)."""
    db = ChimeraDB()
    latest = db.canon.episode_summaries.find_one(sort=[("episode_number", -1)])
    return (latest["episode_number"] + 1) if latest else 1


def _serialize_draft(draft: dict) -> str:
    """Ghep toan bo action + dialogue cua draft thanh 1 text dai."""
    parts = []
    for scene in draft.get("scenes", []):
        parts.append(scene.get("action", ""))
        for dlg in scene.get("dialogues", []):
            parts.append(f"{dlg.get('character', '')}: {dlg.get('line', '')}")
    return "\n".join(parts)


def _generate_summary(script: dict) -> str:
    """Sinh tom tat 2000 ky tu tu Master_Script de luu Canon."""
    scenes = script.get("script", {}).get("scenes", [])
    summary_parts = [script.get("script", {}).get("synopsis", "")]
    for s in scenes[:5]:
        summary_parts.append(s.get("action", ""))
    return " ".join(summary_parts)[:2000]


def _select_bgm(mood: str) -> str:
    """Chon file BGM tu thu muc assets theo mood."""
    bgm_dir = "./assets/bgm"
    mood_map = {
        "epic_tense_sad": "epic_tense_01.mp3",
        "calm_mysterious": "calm_mystery_01.mp3",
        "action_intense": "action_battle_01.mp3",
        "romantic_soft": "romantic_piano_01.mp3",
    }
    filename = mood_map.get(mood, "default.mp3")
    path = os.path.join(bgm_dir, filename)
    if not os.path.exists(path):
        logger.warning(f"[BGM] Khong tim thay {path}, dung default")
        return os.path.join(bgm_dir, "default.mp3")
    return path
