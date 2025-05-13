import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import telebot
from telebot.types import Message, BotCommand
import sys
import time
import signal
import traceback
from telebot import apihelper
from datetime import datetime

# Add src to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database.db import Database
from src.handlers.admin_handlers import AdminHandler
from src.handlers.help_handler import HelpHandler
from src.handlers.user_handlers import UserHandler
from src.utils.formatting import escape_markdown
from src.utils.panel_api import PanelAPI
from src.utils.logger import CustomLogger
from src.utils.exceptions import *

# Enable middleware
apihelper.ENABLE_MIDDLEWARE = True

# Bot Configuration
BOT_TOKEN = '7131562124:AAE_IRcN0UJHXSrChUCfD0e7TZvLg_7s5mk'
ADMIN_IDS = [1709403695]

# Panel Configuration
PANEL_URL = "http://iran.olympusm.ir:7886"
PANEL_USERNAME = "mahdiaria"
PANEL_PASSWORD = "mahdiaria9531"

# Initialize custom logger
logger = CustomLogger("XUIBot")

class XUIBot:
    def __init__(self):
        try:
            # Ensure required directories exist
            for directory in ['backups', 'data', 'logs']:
                Path(directory).mkdir(exist_ok=True)
            
            self.bot_token = BOT_TOKEN
            if not self.bot_token:
                raise ConfigError("Bot token is not set")
            
            # Initialize bot with parse_mode and exception handler
            self.bot = telebot.TeleBot(self.bot_token, parse_mode='MarkdownV2')
            self.bot.exception_handler = self._handle_telegram_exceptions
            
            # Test the token by getting bot info
            bot_info = self.bot.get_me()
            logger.info(f"Connected to bot: @{bot_info.username}")
            
            # Initialize components with error handling
            self._init_components()
            
            # Register all handlers
            self._register_handlers()
            
            # Set bot commands
            self._set_bot_commands()
            
            logger.info("Bot initialized successfully")
            
        except Exception as e:
            logger.critical(f"Critical error during bot initialization: {str(e)}\n{traceback.format_exc()}")
            raise

    def _init_components(self):
        """Initialize bot components with error handling"""
        try:
            # Initialize database
            self.db = Database()
            logger.info("Database initialized successfully")
            
            # Initialize panel API with retry mechanism
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    self.panel_api = PanelAPI(PANEL_URL, PANEL_USERNAME, PANEL_PASSWORD)
                    if self.panel_api.login():
                        logger.info("Panel API initialized successfully")
                        break
                    retry_count += 1
                    if retry_count == max_retries:
                        raise APIError("Failed to authenticate with panel")
                    logger.warning(f"Panel API authentication attempt {retry_count} failed")
                    time.sleep(2 ** retry_count)  # Exponential backoff
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise APIError(f"Failed to initialize Panel API: {str(e)}")
                    logger.warning(f"Panel API initialization attempt {retry_count} failed: {str(e)}")
                    time.sleep(2 ** retry_count)  # Exponential backoff
            
            # Initialize handlers
            self.help_handler = HelpHandler(self.bot)
            self.admin_handler = AdminHandler(self.bot, self.db, self.panel_api)
            self.user_handler = UserHandler(self.bot, self.db, self.panel_api)
            logger.info("All handlers initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing components: {str(e)}\n{traceback.format_exc()}")
            raise

    @staticmethod
    def _handle_telegram_exceptions(exception_instance):
        """Handle Telegram API exceptions"""
        logger.error(f"Telegram API Error: {str(exception_instance)}\n{traceback.format_exc()}")
        if hasattr(exception_instance, 'result'):
            error_code = exception_instance.result.status_code
            if error_code == 429:  # Too Many Requests
                retry_after = exception_instance.result.headers.get('Retry-After', 60)
                logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds")
                time.sleep(int(retry_after))
            elif error_code in [401, 404]:  # Unauthorized or Not Found
                logger.critical("Bot token is invalid or bot was blocked by user")
            elif error_code >= 500:  # Telegram server error
                logger.error("Telegram server error. Retrying in 60 seconds")
                time.sleep(60)

    def _register_handlers(self):
        """Register all message handlers with error handling"""
        try:
            logger.info("Starting handler registration")
            
            # Register middleware for logging and error handling
            @self.bot.middleware_handler(update_types=['message'])
            def global_middleware(bot_instance, message):
                try:
                    # Log incoming message
                    if message.from_user:
                        user_info = {
                            'user_id': message.from_user.id,
                            'username': message.from_user.username,
                            'first_name': message.from_user.first_name,
                            'last_name': message.from_user.last_name,
                            'language_code': message.from_user.language_code
                        }
                        
                        self.db.log_event(
                            'INFO',
                            'message_received',
                            message.from_user.id,
                            f"Message: {message.text}",
                            details=user_info
                        )
                    
                    # Rate limiting check
                    user_id = message.from_user.id if message.from_user else None
                    if user_id and not self._check_rate_limit(user_id):
                        raise RateLimitError("Too many requests")
                    
                except Exception as e:
                    logger.error(f"Middleware error: {str(e)}\n{traceback.format_exc()}")
                    raise

            # Register start command handler
            @self.bot.message_handler(commands=['start'])
            def handle_start_cmd(message: Message):
                try:
                    logger.info(f"Handling start command from user {message.from_user.id}")
                    user = message.from_user
                    user_name = user.first_name or user.username or "کاربر گرامی"
                    
                    # Log user start
                    user_info = {
                        'user_id': user.id,
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'language_code': user.language_code
                    }
                    
                    self.db.log_event(
                        'INFO',
                        'user_start',
                        user.id,
                        'User started the bot',
                        details=user_info
                    )
                    
                    is_admin = user.id in ADMIN_IDS
                    welcome_text = f"""
*🌟 به ربات مدیریت X\\-UI خوش آمدید*
━━━━━━━━━━━━━━━

👋 {escape_markdown(user_name)} عزیز
{escape_markdown('🛡 شما به عنوان ' + ('ادمین' if is_admin else 'کاربر عادی') + ' وارد شده‌اید')}

📱 *امکانات ربات*:
• مشاهده وضعیت اشتراک
• بررسی میزان مصرف
• مشاهده تاریخ انقضا
• دریافت اطلاعات سیستم

💡 برای شروع:
1\\. دستور /help را ارسال کنید
2\\. لینک اشتراک خود را ارسال کنید
3\\. از امکانات ربات لذت ببرید

🔔 در صورت نیاز به راهنمایی با پشتیبانی در ارتباط باشید
                    """
                    
                    self.bot.reply_to(message, welcome_text, parse_mode='MarkdownV2')
                    logger.info(f"Start message sent to user {message.from_user.id}")
                    
                except Exception as e:
                    logger.error(f"Error in start command: {str(e)}\n{traceback.format_exc()}")
                    self._send_error_message(message)

            # Register other handlers
            self.help_handler.register_handlers()
            self.user_handler.register_handlers()
            self.admin_handler.register_handlers()
            
            # Register unknown command handler
            @self.bot.message_handler(func=lambda message: True)
            def handle_unknown_cmd(message: Message):
                try:
                    if message.text and message.text.startswith('/'):
                        command = message.text.split()[0].lower()
                        registered_commands = [cmd.command for cmd in self.bot.get_my_commands()]
                        
                        if command[1:] not in registered_commands:
                            self.bot.reply_to(
                                message,
                                "❌ دستور نامعتبر\\. برای مشاهده لیست دستورات از /help استفاده کنید\\.",
                                parse_mode='MarkdownV2'
                            )
                            self.db.log_event(
                                'WARNING',
                                'unknown_command',
                                message.from_user.id,
                                f"Unknown command: {message.text}"
                            )
                            logger.warning(f"Unknown command {command} from user {message.from_user.id}")
                except Exception as e:
                    logger.error(f"Error handling unknown command: {str(e)}\n{traceback.format_exc()}")
                    self._send_error_message(message)

            logger.info("All handlers registered successfully")
            
        except Exception as e:
            logger.error(f"Error registering handlers: {str(e)}\n{traceback.format_exc()}")
            raise

    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user has exceeded rate limit"""
        # Implement rate limiting logic here
        return True  # Placeholder implementation

    def _send_error_message(self, message: Message):
        """Send error message to user"""
        try:
            error_text = "❌ خطایی رخ داد\\. لطفاً بعداً تلاش کنید\\."
            self.bot.reply_to(message, error_text, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    def _set_bot_commands(self):
        """Set bot commands with error handling"""
        try:
            commands = [
                BotCommand("start", "شروع کار با ربات"),
                BotCommand("help", "نمایش راهنما"),
                BotCommand("status", "نمایش وضعیت اشتراک"),
                BotCommand("usage", "نمایش میزان مصرف"),
                BotCommand("users", "کاربران آنلاین (ادمین)"),
                BotCommand("logs", "نمایش لاگ‌ها (ادمین)"),
                BotCommand("system", "اطلاعات سیستم (ادمین)"),
                BotCommand("backup", "تهیه نسخه پشتیبان (ادمین)")
            ]
            self.bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {str(e)}")
            raise

    def run(self):
        """Start the bot with improved error handling and reconnection logic"""
        logger.info("Bot is starting...")
        max_retries = 5
        retry_count = 0
        
        def signal_handler(signum, frame):
            """Handle system signals gracefully"""
            logger.info("Received shutdown signal")
            self.cleanup()
            sys.exit(0)
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        while retry_count < max_retries:
            try:
                logger.info(f"Connecting to Telegram (Attempt {retry_count + 1})")
                self.bot.polling(non_stop=True, interval=1, timeout=60)
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"Connection error (Attempt {retry_count}): {str(e)}")
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.info(f"Waiting {wait_time} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    logger.critical("Max retries reached. Bot is shutting down.")
                    self.cleanup()
                    raise

    def cleanup(self):
        """Cleanup resources before shutdown"""
        try:
            logger.info("Performing cleanup...")
            # Close database connections
            if hasattr(self, 'db'):
                self.db.close()
            # Close panel API connections
            if hasattr(self, 'panel_api'):
                self.panel_api.close()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    try:
        bot = XUIBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1) 