"""
Các hàm xử lý lệnh (Handlers) cho Showrunner Bot
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    user = update.effective_user
    logger.info(f"User {user.first_name} ({user.id}) đa bat dau bot.")
    await update.message.reply_text(
        f"👋 Xin chào Showrunner {user.first_name}!\n"
        f"Hệ thống CHIMERA (Chế độ Polling) đã sẵn sàng nhận lệnh."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /status"""
    await update.message.reply_text(
        "🟢 Hệ thống CHIMERA đang trực tuyến và chờ kịch bản từ Bản 2."
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /approve (Phê duyệt kịch bản)"""
    # Logic phê duyệt sẽ được kết nối với Cụm Não Số 3 sau
    await update.message.reply_text(
        "✅ Đã ghi nhận lệnh PHÊ DUYỆT. Kịch bản sẽ được đẩy vào Cụm Canon!"
    )

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /reject (Từ chối kịch bản)"""
    # Logic từ chối và yêu cầu viết lại
    await update.message.reply_text(
        "❌ Đã ghi nhận lệnh TỪ CHỐI. Hệ thống sẽ bỏ qua kịch bản này."
    )
