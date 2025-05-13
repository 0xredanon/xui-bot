from functools import wraps
from telebot.types import Message
from typing import Callable, Any

# Hardcoded admin IDs from main.py
ADMIN_IDS = [1709403695]

def admin_required(func: Callable) -> Callable:
    """Decorator to check if the user is an admin"""
    @wraps(func)
    def wrapper(self, message: Message, *args: Any, **kwargs: Any) -> Any:
        if not message.from_user or message.from_user.id not in ADMIN_IDS:
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
        
        return func(self, message, *args, **kwargs)
    
    return wrapper 