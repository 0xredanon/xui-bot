from functools import wraps
from telebot.types import Message
from typing import Callable, Any
from src.database.db import Database
from src.models.models import TelegramUser
from sqlalchemy.orm import Session
from src.models.base import SessionLocal
from proj import ADMIN_IDS


def admin_required(func: Callable) -> Callable:
    """Decorator to check if the user is an admin"""
    @wraps(func)
    def wrapper(self, message: Message, *args: Any, **kwargs: Any) -> Any:
        if not message.from_user:
            return None

        # Check hardcoded admin list
        if message.from_user.id in ADMIN_IDS:
            return func(self, message, *args, **kwargs)

        # Check database admin status
        try:
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if user and user.is_admin:
                    return func(self, message, *args, **kwargs)
        except Exception as e:
            print(f"Error checking admin status: {str(e)}")

        # If not admin, send error message
        self.bot.reply_to(
            message,
            "❌ این دستور فقط برای ادمین‌ها در دسترس است\\.",
            parse_mode='MarkdownV2'
        )
        
        # Log unauthorized access attempt
        if hasattr(self, 'db'):
            self.db.log_event(
                'WARNING',
                'unauthorized_access',
                message.from_user.id if message.from_user else None,
                f"Attempted to use admin command: {message.text}"
            )
        return None
    
    return wrapper 