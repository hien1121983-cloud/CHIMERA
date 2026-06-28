"""FastAPI Webhook Server kết nối đa máy chủ qua MongoDB."""
import os
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.db_client import ChimeraDB
from config.settings import settings

logger = logging.getLogger(__name__)

def _get_bot():
    return telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[ShowrunnerBot] Khoi dong Webhook Server tren Cloud")
    yield
    logger.info("[ShowrunnerBot] Dung Webhook Server")

app = FastAPI(title="Chimera Showrunner Bot", lifespan=lifespan)

# =====================================================================
# PHẦN 1: DÀNH CHO RENDER (WEBHOOK SERVER)
# =====================================================================
@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Render nhận tín hiệu từ Telegram và lưu vào MongoDB."""
    try:
        update = await request.json()
        bot = _get_bot()
        
        # 1. Xử lý nút bấm (Callback Query)
        callback = update.get("callback_query")
        if callback:
            data = callback.get("data")
            logger.info(f"[ShowrunnerBot] Render nhan callback tu Telegram: {data}")
            
            # Lưu quyết định vào DB để GitHub Actions có thể đọc được
            db = ChimeraDB()
            db.permanent.system_state.update_one(
                {"_id": "latest_approval"},
                {"$set": {"decision": data, "status": "pending"}},
                upsert=True
            )
            
            # Phản hồi lại cho user trên app Telegram
            await bot.answer_callback_query(
                callback_query_id=callback["id"], 
                text=f"Đã ghi nhận lệnh: {data}"
            )
            return {"ok": True}
            
        # 2. Xử lý tin nhắn văn bản (như /start, /status)
        message = update.get("message")
        if message and message.get("text"):
            text = message.get("text")
            chat_id = message.get("chat", {}).get("id")
            
            if text.startswith("/start"):
                await bot.send_message(
                    chat_id=chat_id, 
                    text="👋 Hệ thống CHIMERA Webhook (Render) đã kết nối thành công!\n\nBạn hãy bấm Run Workflow Bản 2 trên GitHub Actions, tôi đang chờ nhận kịch bản ở đây."
                )
            elif text.startswith("/status"):
                await bot.send_message(
                    chat_id=chat_id, 
                    text="🟢 Máy chủ Render đang trực tuyến và lắng nghe 24/7."
                )
                
    except Exception as e:
        logger.error(f"[Webhook] Loi: {e}")
        
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Chimera Webhook Server is running!"}

# =====================================================================
# PHẦN 2: DÀNH CHO GITHUB ACTIONS (PIPELINE WORKER)
# =====================================================================
def launch_webhook_in_background(host: str = "0.0.0.0", port: int = 8443):
    """Giữ nguyên tên hàm để main_creative_pipeline.py không bị lỗi ImportError."""
    logger.info("[ShowrunnerBot] Bỏ qua local webhook vì đã triển khai trên Render.")
    return None

async def send_approval_request(text: str, document_path: str = None):
    """GitHub Actions gửi tin nhắn báo cáo lên Telegram."""
    # Reset trạng thái DB trước khi gửi
    db = ChimeraDB()
    db.permanent.system_state.update_one(
        {"_id": "latest_approval"},
        {"$set": {"decision": None, "status": "waiting"}},
        upsert=True
    )

    bot = _get_bot()
    # Giao dien ban phim moi: 3 lua chon draft o hang 1
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("CHỌN BẢN 1", callback_data="APPROVE_0"),
            InlineKeyboardButton("CHỌN BẢN 2", callback_data="APPROVE_1"),
            InlineKeyboardButton("CHỌN BẢN 3", callback_data="APPROVE_2"),
        ],
        [
            InlineKeyboardButton("TỪ CHỐI", callback_data="REJECT"),
            InlineKeyboardButton("VIẾT LẠI (Cực đoan)", callback_data="REWRITE_EXTREME"),
        ],
    ])

    if document_path and os.path.exists(document_path):
        # Gui file dinh kem
        try:
            with open(document_path, "rb") as doc:
                await bot.send_document(
                    chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                    document=doc,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        except telegram.error.BadRequest as e:
            logger.warning(
                f"[ShowrunnerBot] Telegram bị lỗi parse HTML trong caption ({e}). "
                f"Gửi lại ở dạng plain text để không làm sập pipeline."
            )
            with open(document_path, "rb") as doc:
                await bot.send_document(
                    chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                    document=doc,
                    caption=text,
                    parse_mode=None,
                    reply_markup=keyboard,
                )
    else:
        # Gui tin nhan thong thuong neu khong co file
        try:
            await bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except telegram.error.BadRequest as e:
            logger.warning(
                f"[ShowrunnerBot] Telegram bị lỗi parse HTML trong text ({e}). "
                f"Gửi lại ở dạng plain text để không làm sập pipeline."
            )
            await bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=text,
                parse_mode=None,
                reply_markup=keyboard,
            )


async def wait_for_showrunner(timeout: float = None) -> str:
    """GitHub Actions liên tục kiểm tra MongoDB xem Render đã nhận lệnh chưa."""
    effective_timeout = timeout if timeout is not None else (settings.SHOWRUNNER_TIMEOUT_HOURS * 3600)
    logger.info(f"[ShowrunnerBot] Cho Render xac nhan (poll DB, timeout={effective_timeout/3600:.1f}h)...")

    db = ChimeraDB()
    start_time = asyncio.get_event_loop().time()

    while True:
        current_time = asyncio.get_event_loop().time()
        if current_time - start_time > effective_timeout:
            logger.critical("[ShowrunnerBot] Timeout cho duyet.")
            raise TimeoutError("Showrunner timeout.")

        # Đọc Database xem có lệnh mới từ Render không
        record = db.permanent.system_state.find_one({"_id": "latest_approval"})
        if record and record.get("decision") and record.get("status") == "pending":
            decision = record["decision"]
            
            # Đánh dấu đã xử lý xong
            db.permanent.system_state.update_one(
                {"_id": "latest_approval"},
                {"$set": {"status": "processed"}}
            )
            
            logger.info(f"[ShowrunnerBot] Da bat duoc tin hieu tu Render: {decision}")
            return decision

        await asyncio.sleep(5)  # Chờ 5 giây rồi kiểm tra lại DB
