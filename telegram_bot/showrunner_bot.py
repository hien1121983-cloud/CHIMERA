"""FastAPI webhook + asyncio.Event de cho Showrunner duyet (Va M-07)."""
import os
import json
import asyncio
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

# === Trang thai cho duyet (cung event loop) ===
_approval_event = asyncio.Event()
_approval_decision = None


def _get_bot():
    import telegram

    return telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[ShowrunnerBot] Khoi dong webhook server")
    yield
    logger.info("[ShowrunnerBot] Dung webhook server")


app = FastAPI(title="Chimera Showrunner Bot", lifespan=lifespan)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    global _approval_decision
    update = await request.json()

    callback = update.get("callback_query")
    if callback:
        data = callback.get("data")
        logger.info(f"[ShowrunnerBot] Nhan callback: {data}")
        _approval_decision = data
        _approval_event.set()
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}


def start_webhook_server(host: str = "0.0.0.0", port: int = 8443):
    """Chay FastAPI trong thread rieng."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def launch_webhook_in_background(host: str = "0.0.0.0", port: int = 8443):
    thread = threading.Thread(
        target=start_webhook_server, args=(host, port), daemon=True
    )
    thread.start()
    logger.info(f"[ShowrunnerBot] Webhook server chay nen tai {host}:{port}")
    return thread


async def send_approval_request(text: str, video_summary: dict = None):
    """Gui yeu cau duyet kem inline keyboard."""
    import telegram
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    bot = _get_bot()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("DUYET & RENDER", callback_data="APPROVE"),
            InlineKeyboardButton("TU CHOI", callback_data="REJECT"),
        ],
        [
            InlineKeyboardButton(
                "VIET LAI (Bom noi tam cuc doan)",
                callback_data="REWRITE_EXTREME",
            )
        ],
    ])
    _approval_event.clear()
    await bot.send_message(
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def wait_for_showrunner(timeout: float = None) -> str:
    """Ngu cho den khi Showrunner bam nut (Va M-07: cung event loop)."""
    global _approval_decision
    if timeout:
        await asyncio.wait_for(_approval_event.wait(), timeout=timeout)
    else:
        await _approval_event.wait()
    return _approval_decision
