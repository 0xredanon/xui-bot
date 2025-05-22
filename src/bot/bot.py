import os
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from telebot.util import escape_markdown
from sqlalchemy.orm import Session
from typing import Optional
import time
import traceback
import logging

logger = logging.getLogger(__name__)

from ..models.base import SessionLocal
from ..models.models import TelegramUser, UserActivity, ChatHistory, VPNClient
from ..api.xui_client import XUIClient
from proj import *

# Initialize bot with hardcoded token
BOT_TOKEN = BOT_TOKEN  # Replace with your Telegram bot token
bot = telebot.TeleBot(BOT_TOKEN)
xui_client = XUIClient()

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def save_user_activity(db: Session, user_id: int, activity_type: str, target_uuid: Optional[str] = None, details: dict = None):
    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        target_uuid=target_uuid,
        details=details or {}
    )
    db.add(activity)
    db.commit()

def save_chat_message(db: Session, user_id: int, message_id: int, message_type: str, content: str):
    chat = ChatHistory(
        user_id=user_id,
        message_id=message_id,
        message_type=message_type,
        content=content
    )
    db.add(chat)
    db.commit()

def get_or_create_user(db: Session, telegram_user) -> TelegramUser:
    user = db.query(TelegramUser).filter_by(telegram_id=telegram_user.id).first()
    if not user:
        user = TelegramUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def create_client_status_keyboard(client_uuid: str, is_admin: bool) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("🔄 بروزرسانی وضعیت", callback_data=f"refresh_{client_uuid}")
    )
    
    if is_admin:
        # Traffic control buttons
        keyboard.row(
            InlineKeyboardButton("🎯 تنظیم حجم", callback_data=f"traffic_{client_uuid}"),
            InlineKeyboardButton("♻️ ریست حجم", callback_data=f"reset_{client_uuid}")
        )
        keyboard.row(
            InlineKeyboardButton("♾️ حجم نامحدود", callback_data=f"unlimited_{client_uuid}"),
            InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"custom_traffic_{client_uuid}")
        )
        
        # Expiry control buttons
        keyboard.row(
            InlineKeyboardButton("🗓️ تنظیم تاریخ انقضا", callback_data=f"expiry_{client_uuid}")
        )
        
        # IP management buttons
        keyboard.row(
            InlineKeyboardButton("👀 مشاهده IPها", callback_data=f"ips_{client_uuid}")
        )
    
    return keyboard

def create_traffic_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    traffic_options = [10, 20, 30, 50, 100]
    
    # Create rows with two buttons each
    for i in range(0, len(traffic_options), 2):
        row = []
        row.append(InlineKeyboardButton(
            f"{traffic_options[i]}GB",
            callback_data=f"settraffic_{client_uuid}_{traffic_options[i]}"
        ))
        if i + 1 < len(traffic_options):
            row.append(InlineKeyboardButton(
                f"{traffic_options[i+1]}GB",
                callback_data=f"settraffic_{client_uuid}_{traffic_options[i+1]}"
            ))
        keyboard.row(*row)
    
    # Add custom traffic input button
    keyboard.row(
        InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"custom_traffic_{client_uuid}")
    )
    
    # Add back button
    keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}"))
    return keyboard

def create_expiry_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    days_options = [1, 2, 3, 5, 10, 30, 60, 90, 120, 180]
    
    # Create rows with three buttons each
    for i in range(0, len(days_options), 3):
        row = []
        for j in range(3):
            if i + j < len(days_options):
                row.append(InlineKeyboardButton(
                    f"{days_options[i+j]} روز",
                    callback_data=f"setexpiry_{client_uuid}_{days_options[i+j]}"
                ))
        keyboard.row(*row)
    
    # Add unlimited option
    keyboard.row(
        InlineKeyboardButton("♾️ نامحدود", callback_data=f"setexpiry_{client_uuid}_0")
    )
    
    # Add back button
    keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}"))
    return keyboard

class Bot:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.db = get_db()
        self.xui_client = xui_client
        self._register_handlers()

    def _register_handlers(self):
        """Register all command handlers"""
        try:
            logger.info("Starting handler registration")
            
            # Register global middleware
            @self.bot.middleware_handler(update_types=['message'])
            def global_middleware(bot_instance, message):
                try:
                    # Check if bot is enabled
                    if not self.db.get_bot_status():
                        # Allow admin commands even when bot is disabled
                        if message.text and message.text.startswith('/'):
                            command = message.text.split()[0][1:].lower()
                            if command in ['toggle', 'users', 'logs', 'backup', 'broadcast', 'add']:
                                return message
                        
                        # Send disabled message to non-admin users
                        if message.from_user:
                            bot_instance.reply_to(
                                message,
                                "❌ *ربات در حال حاضر غیرفعال است*\\.\nلطفاً بعداً تلاش کنید\\.",
                                parse_mode='MarkdownV2'
                            )
                        return None
                    
                    # Log message
                    if message.from_user:
                        self.db.log_event(
                            'INFO',
                            'message_received',
                            message.from_user.id,
                            f"Received message: {message.text[:100]}",
                            details={'message_id': message.message_id}
                        )
                except Exception as e:
                    logger.error(f"Error in global middleware: {str(e)}")
                return message
            
            # Register command handlers
            self.bot.message_handler(commands=['start'])(self.handle_start_cmd)
            self.bot.message_handler(commands=['help'])(self.handle_help_cmd)
            self.bot.message_handler(commands=['status'])(self.handle_status_cmd)
            self.bot.message_handler(commands=['link'])(self.handle_link_cmd)
            self.bot.message_handler(commands=['traffic'])(self.handle_traffic_cmd)
            self.bot.message_handler(commands=['expiry'])(self.handle_expiry_cmd)
            self.bot.message_handler(commands=['usage'])(self.handle_usage_cmd)
            self.bot.message_handler(commands=['settings'])(self.handle_settings_cmd)
            
            # Register callback handlers
            self.bot.callback_query_handler(func=lambda call: True)(self.handle_callback)
            
            logger.info("All handlers registered successfully")
            
        except Exception as e:
            logger.error(f"Error registering handlers: {str(e)}\n{traceback.format_exc()}")
            raise

    def _check_rate_limit(self, user_id: int) -> bool:
        # Implement rate limiting logic here
        return True  # Placeholder, actual implementation needed

    def _send_error_message(self, message: Message):
        # Implement error message sending logic here
        pass  # Placeholder, actual implementation needed

    def start(self):
        """Start the bot with proper error handling."""
        try:
            logger.info("Starting bot polling...")
            self.bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logger.error(f"Error in bot polling: {str(e)}")
            raise

    def shutdown(self):
        """Gracefully shutdown the bot."""
        try:
            logger.info("Received shutdown signal")
            logger.info("Cleaning up resources...")
            
            # Stop the bot polling
            if hasattr(self, 'bot'):
                self.bot.stop_polling()
            
            # Cleanup database
            if hasattr(self, 'db'):
                self.db.cleanup()
            
            # Cleanup panel API
            if hasattr(self, 'panel_api'):
                self.panel_api.cleanup()
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

def run_bot():
    print("Bot started...")
    bot.infinity_polling() 