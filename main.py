import os
import logging
from pathlib import Path
import telebot
from telebot.types import Message, BotCommand
import sys
import time
import signal
import traceback
from telebot import apihelper
from datetime import datetime

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from src.database.db import Database
from src.handlers.admin_handlers import AdminHandler
from src.handlers.help_handler import HelpHandler
from src.handlers.user_handlers import UserHandler
from src.utils.formatting import escape_markdown
from src.utils.panel_api import PanelAPI
from src.utils.logger import CustomLogger
from src.utils.exceptions import *
from proj import *

# Enable middleware
apihelper.ENABLE_MIDDLEWARE = True

# Bot Configuration
BOT_TOKEN = BOT_TOKEN
ADMIN_IDS = ADMIN_IDS

# Panel Configuration
PANEL_URL = PANEL_URL
PANEL_USERNAME = PANEL_USERNAME
PANEL_PASSWORD = PANEL_PASSWORD

# Rate Limiting Configuration
RATE_LIMIT_MESSAGES = 30  # messages per window
RATE_LIMIT_WINDOW = 60  # seconds

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'
BACKUPS_DIR = BASE_DIR / 'backups'

# Additional Configuration
TIMEZONE = 'Asia/Tehran'
LOG_LEVEL = 'INFO'
BACKUP_SCHEDULE = '0 0 * * *'  # Daily at midnight
MAX_BACKUPS = 7
API_TIMEOUT = 30
MAX_RETRIES = 3
SESSION_TIMEOUT = 3600
MAX_LOGIN_ATTEMPTS = 3
DEFAULT_TRAFFIC_LIMIT = 50
DEFAULT_DURATION = 30

# Feature Flags
ENABLE_BACKUP = True
ENABLE_MONITORING = True
ENABLE_NOTIFICATIONS = True

# Initialize custom logger
logger = CustomLogger("XUIBot")

class XUIBot:
    def __init__(self):
        try:
            # Ensure required directories exist
            for directory in [DATA_DIR, LOGS_DIR, BACKUPS_DIR]:
                directory.mkdir(exist_ok=True)
            
            self.bot_token = BOT_TOKEN
            if not self.bot_token:
                raise ConfigError("Bot token is not set")
            
            # Initialize bot with parse_mode and exception handler
            self.bot = telebot.TeleBot(self.bot_token, parse_mode='MarkdownV2')
            self.bot.exception_handler = self._handle_telegram_exceptions
            
            # Test the token by getting bot info
            bot_info = self.bot.get_me()
            logger.info(f"Connected to bot: @{bot_info.username}")
            
            # Initialize components
            self._init_components()
            
            # Run database migrations
            from src.database.migrations.run_migrations import run_migrations
            if not run_migrations():
                logger.warning("Some database migrations failed, but continuing with initialization")
            
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
            max_retries = MAX_RETRIES
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
            def global_middleware(bot: telebot.TeleBot, message: Message):
                """Global middleware for logging and error handling"""
                start_time = time.time()
                try:
                    # Ensure user data is saved and user_id is an integer
                    user_id = int(message.from_user.id)
                    username = message.from_user.username
                    first_name = message.from_user.first_name
                    last_name = message.from_user.last_name
                    
                    # Prepare user info
                    user_info = {
                        'id': user_id,
                        'username': username or '',
                        'first_name': first_name or '',
                        'last_name': last_name or '',
                        'language_code': message.from_user.language_code or 'fa'
                    }
                    
                    # Ensure user exists in database
                    if not self.db.ensure_user_exists(user_info):
                        logger.warning(f"Failed to update user data for {user_id}")
                    
                    # Log user data
                    self.db.log_event('INFO', 'user_data', user_id, f"User data received: {username}")
                    
                    # Log message details
                    message_info = {
                        'message_id': message.message_id,
                        'chat_id': message.chat.id,
                        'message_type': message.content_type,
                        'command': message.text.split()[0] if message.text and message.text.startswith('/') else None
                    }
                    
                    # Log chat message
                    self.db.log_chat_message(
                        user_id=user_id,
                        message_id=message.message_id,
                        chat_id=message.chat.id,
                        message_type=message.content_type,
                        content=message.text or message.caption or '',
                        reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None,
                        forward_from_id=message.forward_from.id if message.forward_from else None,
                        is_command=bool(message.text and message.text.startswith('/')),
                        command_name=message.text.split()[0][1:] if message.text and message.text.startswith('/') else None,
                        command_args=' '.join(message.text.split()[1:]) if message.text and message.text.startswith('/') else None
                    )
                    
                    # Log user activity
                    self.db.log_event('INFO', 'message_received', user_id, f"Message received: {message_info}")
                    
                    # Update user stats
                    self.db.update_user_stats(user_id)
                    
                    # Log system metrics
                    processing_time = int((time.time() - start_time) * 1000)
                    self.db.log_system_metric(
                        metric_type='message_processing',
                        metric_value=processing_time,
                        details={'message_id': message.message_id, 'user_id': user_id}
                    )
                    
                    # Check rate limits
                    if not self._check_rate_limit(user_id):
                        self.db.log_event('WARNING', 'rate_limit_exceeded', user_id, "Rate limit exceeded")
                        return False
                        
                    return True
                    
                except Exception as e:
                    logger.error(f"Middleware error: {str(e)}\n{traceback.format_exc()}")
                    if message and message.from_user and message.from_user.id:
                        self.db.log_event('ERROR', 'middleware_error', int(message.from_user.id), f"Middleware error: {str(e)}")
                    return False

            # Register start command handler
            @self.bot.message_handler(commands=['start'])
            def handle_start_cmd(message: Message):
                try:
                    if not message or not message.from_user or not message.from_user.id:
                        logger.error("Invalid message or missing user data in start command")
                        return
                        
                    user_id = int(message.from_user.id)  # Ensure ID is integer
                    logger.info(f"Handling start command from user {user_id}")
                    
                    user = message.from_user
                    user_name = user.first_name or user.username or "کاربر گرامی"
                    
                    # Prepare user info
                    user_info = {
                        'id': user_id,  # Use the validated integer ID
                        'username': str(user.username or ''),
                        'first_name': str(user.first_name or ''),
                        'last_name': str(user.last_name or ''),
                        'language_code': str(user.language_code or 'fa')
                    }
                    
                    input_data = {
                        'command': 'start',
                        'text': message.text,
                        'user_info': user_info
                    }
                    
                    process_details = {}
                    
                    # Ensure user exists in database
                    if not self.db.ensure_user_exists(user_info):
                        logger.warning(f"Failed to update user data for {user_id}")
                        process_details['user_update'] = 'failed'
                    else:
                        process_details['user_update'] = 'success'
                    
                    is_admin = user_id in ADMIN_IDS
                    process_details['is_admin'] = is_admin
                    
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
                    logger.info(f"Start message sent to user {user_id}")
                    
                    # Log the activity with all details
                    output_data = {
                        'welcome_message_sent': True,
                        'user_type': 'admin' if is_admin else 'regular'
                    }
                    
                    self.db.log_bot_activity(
                        user_id=user_id,
                        command='start',
                        input_data=input_data,
                        output_data=output_data,
                        process_details=process_details,
                        status='success'
                    )
                    
                except Exception as e:
                    logger.error(f"Error in start command: {str(e)}\n{traceback.format_exc()}")
                    if message and message.from_user and message.from_user.id:
                        self._send_error_message(message)
                        if hasattr(self, 'db'):
                            self.db.log_bot_activity(
                                user_id=int(message.from_user.id),
                                command='start',
                                input_data={'text': message.text},
                                status='error',
                                error=str(e)
                            )

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
        try:
            current_time = time.time()
            user_messages = self.db.get_user_messages(user_id, current_time - RATE_LIMIT_WINDOW)
            return len(user_messages) < RATE_LIMIT_MESSAGES
        except Exception as e:
            logger.error(f"Error checking rate limit: {str(e)}")
            return True  # Allow message in case of error

    def _send_error_message(self, message: Message):
        """Send error message to user"""
        try:
            self.bot.reply_to(
                message,
                "❌ خطایی رخ داد\\. لطفا مجددا تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    def _set_bot_commands(self):
        """Set bot commands"""
        try:
            commands = [
                BotCommand("start", "شروع کار با ربات"),
                BotCommand("help", "راهنمای دستورات"),
                BotCommand("usage", "میزان مصرف"),
                BotCommand("system_info", "اطلاعات سیستم"),
                BotCommand("users", "مشاهده کاربران آنلاین"),
                BotCommand("users_info", "لیست کامل کاربران"),
                BotCommand("toggle", "فعال/غیرفعال کردن بکاپ"),
            ]
            self.bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
        except Exception as e:
            logger.error(f"Error setting bot commands: {str(e)}")

    def start(self):
        """Run the bot"""
        try:
            logger.info("Starting bot polling...")
            # Set up signal handlers
            def signal_handler(signum, frame):
                logger.info("Received shutdown signal")
                self.shutdown()
                sys.exit(0)
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            # Start polling
            self.bot.infinity_polling()
        except Exception as e:
            logger.critical(f"Critical error during bot execution: {str(e)}\n{traceback.format_exc()}")
            self.shutdown()
            raise
        finally:
            self.shutdown()

    def shutdown(self):
        """Cleanup resources"""
        try:
            logger.info("Cleaning up resources...")
            if hasattr(self, 'db'):
                self.db.close()
            if hasattr(self, 'panel_api'):
                self.panel_api.close()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

def main():
    try:
        # Initialize bot
        bot = XUIBot()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, lambda s, f: bot.shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: bot.shutdown())
        
        # Start bot with proper cleanup
        try:
            bot.start()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            bot.shutdown()
        except Exception as e:
            logger.error(f"Error running bot: {str(e)}")
            bot.shutdown()
            
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 