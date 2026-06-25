"""Cac ham helper dung chung trong toan pipeline."""
import os
import logging
import threading

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
    """Wrapper sync cho send_telegram_alert.

    FIX #7: Phien ban cu dung asyncio.create_task() khi co event loop dang
    chay, tao ra fire-and-forget task khong duoc await. Task co the bi mat
    neu event loop dong truoc khi task chay xong (vi du: pipeline crash
    ngay sau khi goi ham nay).

    Phien ban moi:
    - Khong co event loop (sync context, pho bien nhat): asyncio.run() truc tiep.
    - Co event loop dang chay (trong async context): chay asyncio.run() trong
      thread rieng voi join(timeout=10) de dam bao message duoc gui truoc khi
      tiep tuc. Tranh deadlock vi asyncio.run() tao loop moi, khong chung
      voi loop hien tai.
    """
    import asyncio

    try:
        # Kiem tra xem co event loop dang chay khong
        asyncio.get_running_loop()
        # Co loop dang chay -> chay trong thread rieng de tranh deadlock
        _send_in_thread(message)
    except RuntimeError:
        # Khong co loop dang chay -> chay truc tiep (pho bien trong sync context)
        try:
            asyncio.run(send_telegram_alert(message))
        except Exception as e:
            logger.error(f"[Telegram Sync] Loi: {e}")


def _send_in_thread(message: str):
    """Chay send_telegram_alert trong thread rieng, cho toi da 10 giay."""
    import asyncio

    result = {"error": None}

    def _run():
        try:
            asyncio.run(send_telegram_alert(message))
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=10)
    if t.is_alive():
        logger.warning("[Telegram Sync] Timeout sau 10s, message co the chua duoc gui.")
    elif result["error"]:
        logger.error(f"[Telegram Sync] Loi tu thread: {result['error']}")


def get_current_episode() -> int:
    """Lay so tap hien tai tu Cum Nao 3 (Canon)."""
    db = ChimeraDB()
    latest = db.canon.episode_summaries.find_one(sort=[("episode_number", -1)])
    return (latest["episode_number"] + 1) if latest else 1


def _serialize_draft(draft: dict) -> str:
    """Ghep toan bo action + dialogue cua draft thanh 1 text dai.

    FIX #9: Them fallback cho truong hop key cua scene khac voi schema A1
    (vi du data cu trong MongoDB dung "description" thay vi "action").
    Them synopsis vao dau de tang chat luong so sanh embedding.
    """
    parts = []

    # Them synopsis neu co
    synopsis = draft.get("synopsis", "")
    if synopsis:
        parts.append(synopsis)

    for scene in draft.get("scenes", []):
        # FIX #9: Ho tro ca "action" (schema hien tai) lan "description" (legacy)
        action_text = scene.get("action") or scene.get("description") or ""
        if action_text:
            parts.append(action_text)

        for dlg in scene.get("dialogues", []):
            character = dlg.get("character", "")
            line = dlg.get("line", "")
            if character and line:
                parts.append(f"{character}: {line}")

    return "\n".join(parts)


def _generate_summary(script: dict) -> str:
    """Sinh tom tat 2000 ky tu tu Master_Script de luu Canon."""
    scenes = script.get("script", {}).get("scenes", [])
    summary_parts = [script.get("script", {}).get("synopsis", "")]
    for s in scenes[:5]:
        action = s.get("action") or s.get("description") or ""
        if action:
            summary_parts.append(action)
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
