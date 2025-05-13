from telebot import TeleBot
from telebot.types import Message
from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold
from ..utils.panel_api import PanelAPI
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
import traceback
from functools import wraps

# Initialize custom logger
logger = CustomLogger("UserHandler")

def handle_errors(func):
    """Decorator for handling errors in handler methods"""
    @wraps(func)
    def wrapper(self, message: Message, *args, **kwargs):
        try:
            return func(self, message, *args, **kwargs)
        except APIError as e:
            logger.error(f"API Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در ارتباط با سرور\\. لطفاً بعداً تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )
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
            # Log the error event
            if hasattr(self, 'db'):
                self.db.log_event(
                    'ERROR',
                    f'handler_error_{func.__name__}',
                    message.from_user.id if message.from_user else None,
                    str(e),
                    details={'traceback': traceback.format_exc()}
                )
    return wrapper

class UserHandler:
    def __init__(self, bot: TeleBot, db: Database, panel_api: PanelAPI):
        self.bot = bot
        self.db = db
        self.panel_api = panel_api
        logger.info("UserHandler initialized")

    def validate_vpn_link(self, link: str) -> str:
        """Validate VPN link format and extract identifier"""
        if not link or not isinstance(link, str):
            raise ValidationError("لینک اشتراک نامعتبر است")
        
        if not link.lower().startswith('vless://'):
            raise ValidationError("لینک باید با vless:// شروع شود")
        
        identifier = self.panel_api.extract_identifier_from_link(link)
        if not identifier:
            raise ValidationError("شناسه کاربری در لینک یافت نشد")
        
        return identifier

    @handle_errors
    def process_vpn_link(self, message: Message, link: str):
        """Process a VPN link and show status"""
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.info(f"Processing VPN link from user {user_id}")
        
        # Validate link and get identifier
        identifier = self.validate_vpn_link(link)
        logger.debug(f"Extracted identifier: {identifier[:8]}... for user {user_id}")
        
        try:
            # Get client info
            client_info = self.panel_api.get_client_info(uuid=identifier)
            if not client_info:
                raise ValidationError("اطلاعات کاربر یافت نشد. لطفا از صحت لینک اطمینان حاصل کنید")

            # Get traffic values
            up = client_info.get('up', 0)
            down = client_info.get('down', 0)
            total = client_info.get('total_gb', 0) * 1024 * 1024 * 1024  # Convert GB to bytes
            
            # Calculate usage
            total_usage = up + down
            remaining = max(0, total - total_usage) if total > 0 else float('inf')
            usage_percent = (total_usage / total * 100) if total > 0 else 0

            # Get subscription URL
            sub_url = self.panel_api.get_subscription_url(client_info)
            
            # Format response
            response = f"""
{format_bold('🌟 وضعیت اشتراک شما')}
━━━━━━━━━━━━━━━

👤 {format_bold('مشخصات')}:
• نام: {format_code(client_info.get('remark', 'بدون نام'))}
• ایمیل: {format_code(client_info.get('email', 'نامشخص'))}
• وضعیت: {format_code('🟢 فعال' if client_info.get('enable', True) else '🔴 غیرفعال')}

📊 {format_bold('اطلاعات حجم')}:
• کل حجم: {format_code(format_size(total) if total > 0 else 'نامحدود')}
• مصرف شده: {format_code(format_size(total_usage))}
• باقیمانده: {format_code(format_size(remaining) if total > 0 else 'نامحدود')}
• درصد مصرف: {format_code(f'{usage_percent:.1f}%' if total > 0 else '0%')}

📈 {format_bold('جزئیات مصرف')}:
• آپلود: {format_code(format_size(up))}
• دانلود: {format_code(format_size(down))}

⚙️ {format_bold('تنظیمات')}:
• پروتکل: {format_code(client_info.get('protocol', 'VLESS').upper())}
• پورت: {format_code(str(client_info.get('port', '')))}
• امنیت: {format_code(client_info.get('tls', '').upper())}

⏰ {format_bold('زمان')}:
• تاریخ انقضا: {format_code(format_date(client_info.get('expire_time', 0)/1000))}

🔗 {format_bold('لینک اتصال')}:
{format_code(sub_url)}

💫 برای راهنمایی بیشتر از /help استفاده کنید
"""
            
            self.bot.reply_to(message, response, parse_mode='MarkdownV2')
            logger.info(f"Status sent successfully to user {user_id}")
            
            # Log the successful status check
            self.db.log_event(
                'INFO',
                'status_check',
                user_id,
                'Status check completed successfully',
                details={
                    'email': client_info.get('email'),
                    'uuid': identifier[:8] + '...',
                    'total': total,
                    'usage': total_usage,
                    'remaining': remaining
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing VPN link: {str(e)}")
            raise

    @handle_errors
    def handle_status(self, message: Message):
        """Handle the /status command to check subscription status"""
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.info(f"Handling status command from user {user_id}")
        
        args = message.text.split(maxsplit=1)
        if len(args) != 2:
            raise ValidationError("لطفا لینک اشتراک خود را وارد کنید.\nمثال: /status vless://uuid@host:port?...")
        
        vpn_link = args[1].strip()
        self.process_vpn_link(message, vpn_link)

    @handle_errors
    def handle_usage(self, message: Message):
        """Handle the /usage command to show traffic usage"""
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.info(f"Handling usage command from user {user_id}")
        
        args = message.text.split(maxsplit=1)
        if len(args) != 2:
            raise ValidationError("لطفا لینک اشتراک خود را وارد کنید.\nمثال: /usage vless://uuid@host:port?...")
        
        vpn_link = args[1].strip()
        self.process_vpn_link(message, vpn_link)

    @handle_errors
    def handle_direct_link(self, message: Message):
        """Handle direct VPN link messages"""
        if message.text and message.text.lower().startswith('vless://'):
            user_id = message.from_user.id if message.from_user else "Unknown"
            logger.info(f"Handling direct VPN link from user {user_id}")
            self.process_vpn_link(message, message.text.strip())

    def register_handlers(self):
        """Register all user command handlers"""
        try:
            logger.info("Registering user command handlers")
            
            # Register command handlers
            self.bot.message_handler(commands=['status'])(self.handle_status)
            self.bot.message_handler(commands=['usage'])(self.handle_usage)
            
            # Register direct link handler (before unknown command handler)
            self.bot.message_handler(
                func=lambda message: message.text and message.text.lower().startswith('vless://')
            )(self.handle_direct_link)
            
            logger.info("User command handlers registered successfully")
            
            # Log registration
            self.db.log_event(
                'INFO',
                'handlers_registered',
                None,
                'User command handlers registered successfully',
                details={'handlers': ['status', 'usage', 'direct_link']}
            )
        except Exception as e:
            logger.error(f"Failed to register user handlers: {str(e)}\n{traceback.format_exc()}")
            raise 