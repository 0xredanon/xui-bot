from telebot import TeleBot
from telebot.types import Message
from typing import Dict, List
from ..utils.formatting import escape_markdown
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
import traceback
from functools import wraps

# Initialize custom logger
logger = CustomLogger("HelpHandler")

def handle_help_errors(func):
    """Decorator for handling errors in help handler methods"""
    @wraps(func)
    def wrapper(self, message: Message, *args, **kwargs):
        try:
            return func(self, message, *args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation Error in {func.__name__}: {str(e)}")
            self.bot.reply_to(
                message,
                f"❌ {escape_markdown(str(e))}",
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطای غیرمنتظره\\. لطفاً بعداً تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )
    return wrapper

class HelpHandler:
    def __init__(self, bot: TeleBot):
        self.bot = bot
        self.commands = {
            "👤 دستورات کاربر": {
                "/start": "شروع کار با ربات",
                "/help": "نمایش این راهنما",
                "/usage": "نمایش میزان مصرف - نمونه: /usage vless://... یا ارسال مستقیم لینک",
                "/info": "نمایش اطلاعات سیستم و کاربر",
            },
            "🛡️ دستورات ادمین": {
                "/add": "افزودن کاربر جدید - `/add email GB days`",
                "/update": "بروزرسانی کاربر - `/update email GB days`",
                "/reset": "ریست ترافیک - `/reset email`",
                "/users": "لیست کاربران",
                "/logs": "نمایش لاگ‌ها - `/logs [count]`",
                "/broadcast": "ارسال پیام به همه - `/broadcast message`",
                "/backup": "تهیه نسخه پشتیبان",
            }
        }
        logger.info("HelpHandler initialized")
        # Register handlers in constructor
        self.register_handlers()

    @handle_help_errors
    def handle_help(self, message: Message):
        """Handle the /help command"""
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.info(f"Handling help command from user {user_id}")
        
        try:
            # Build help text with proper error handling for each section
            help_text = f"""
*🤖 راهنمای جامع ربات*
━━━━━━━━━━━━━━━

👤 *دستورات عمومی*:
• \\`/start\\` \\- شروع کار با ربات
• \\`/help\\` \\- نمایش این راهنما
• \\`/usage\\` \\- نمایش میزان مصرف
• \\`/info\\` \\- اطلاعات سیستم

🛡 *دستورات مدیریتی*:
• \\`/users\\` \\- مشاهده کاربران آنلاین
• \\`/logs\\` \\- مشاهده گزارشات
• \\`/system\\` \\- اطلاعات سیستم
• \\`/backup\\` \\- تهیه نسخه پشتیبان
• \\`/broadcast\\` \\- ارسال پیام به همه

📝 *نکات مهم*:
• برای مشاهده وضعیت، لینک اشتراک را ارسال کنید
• فرمت لینک باید با vless:// شروع شود
• حجم‌ها به صورت گیگابایت نمایش داده می‌شوند
• تاریخ‌ها به صورت شمسی نمایش داده می‌شوند

💡 *مثال استفاده*:
\\`/usage vless://uuid@host\\:port\\`

🔔 برای دریافت پشتیبانی با ادمین در ارتباط باشید
"""
            
            # Send help message with proper formatting
            self.bot.reply_to(message, help_text, parse_mode='MarkdownV2')
            logger.info(f"Help message sent successfully to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error formatting help message: {str(e)}\n{traceback.format_exc()}")
            
            try:
                # Fallback to plain text if markdown formatting fails
                plain_text = (
                    "🤖 راهنمای دستورات ربات\n\n"
                    "👤 دستورات کاربر:\n"
                    "• /start - شروع کار با ربات\n"
                    "• /help - نمایش این راهنما\n"
                    "• /usage - نمایش میزان مصرف\n\n"
                    "📝 برای اطلاعات بیشتر، دستورات را بدون پارامتر وارد کنید."
                )
                self.bot.reply_to(message, plain_text)
                logger.info(f"Fallback plain text help sent to user {user_id}")
            except Exception as e2:
                logger.error(f"Error sending fallback help message: {str(e2)}\n{traceback.format_exc()}")
                raise

    def register_handlers(self):
        """Register all help command handlers"""
        try:
            logger.info("Registering help command handler")
            self.bot.message_handler(commands=['help'])(self.handle_help)
            logger.info("Help command handler registered successfully")
        except Exception as e:
            logger.error(f"Failed to register help handler: {str(e)}\n{traceback.format_exc()}")
            raise 