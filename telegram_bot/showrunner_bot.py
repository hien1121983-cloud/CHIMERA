"""
Showrunner Bot - Chạy ở chế độ Polling (Không cần FastAPI/Uvicorn)
"""
import os
import logging
from telegram.ext import Application, CommandHandler

# Import các handler từ file handlers.py của bạn
# (Lưu ý: Đảm bảo tên các hàm dưới đây khớp với file handlers.py thực tế của bạn)
from telegram_bot.handlers import start, status, approve, reject

logger = logging.getLogger(__name__)

def create_bot():
    """Khởi tạo và cấu hình ứng dụng Bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("[Showrunner Bot] CRITICAL: Thiếu TELEGRAM_BOT_TOKEN trong .env")
        return None
        
    # Xây dựng ứng dụng bot
    application = Application.builder().token(token).build()
    
    # Đăng ký các lệnh (Commands)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("reject", reject))
    
    return application

# Khởi tạo biến toàn cục để các file khác (như main_creative_pipeline) có thể import
bot_app = create_bot()

def start_bot():
    """Hàm khởi động chính của Bot ở chế độ Polling."""
    if not bot_app:
        logger.error("[Showrunner Bot] Không thể khởi động do thiếu Token.")
        return
        
    logger.info("=" * 50)
    logger.info("[Showrunner Bot] KHỞI ĐỘNG THÀNH CÔNG Ở CHẾ ĐỘ POLLING")
    logger.info("=" * 50)
    
    # Chạy Polling. 
    # drop_pending_updates=True giúp bot bỏ qua các tin nhắn cũ lúc nó đang tắt, tránh kẹt lệnh.
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Thiết lập log khi chạy test độc lập file này
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    start_bot()
    
