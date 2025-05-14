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
        
        input_data = {
            'link': link,
            'command_type': 'direct_link' if message.text.startswith('vless://') else message.text.split()[0][1:]
        }
        
        process_details = {}
        
        try:
            # Ensure user exists and update their info
            if message.from_user:
                user_info = {
                    'id': message.from_user.id,
                    'username': message.from_user.username,
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name,
                    'language_code': message.from_user.language_code
                }
                self.db.ensure_user_exists(user_info)
                process_details['user_update'] = 'success'
            
            # Validate link and get identifier
            identifier = self.validate_vpn_link(link)
            process_details['identifier'] = identifier[:8] + '...'
            logger.debug(f"Extracted identifier: {identifier[:8]}... for user {user_id}")
            
            # Get client info
            client_info = self.panel_api.get_client_info(uuid=identifier)
            if not client_info:
                raise ValidationError("اطلاعات کاربر یافت نشد. لطفا از صحت لینک اطمینان حاصل کنید")

            # Update user's email if not set
            if message.from_user and client_info.get('email'):
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE users 
                        SET email = %s, 
                            inbound_id = %s
                        WHERE telegram_id = %s 
                        AND (email IS NULL OR email = '')
                    """, (
                        client_info.get('email'),
                        client_info.get('inbound_id'),
                        message.from_user.id
                    ))
                    conn.commit()
                process_details['email_update'] = 'success'

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
            
            # Log the activity with all details
            output_data = {
                'total_traffic': total,
                'used_traffic': total_usage,
                'remaining_traffic': remaining,
                'usage_percent': usage_percent,
                'upload': up,
                'download': down,
                'status': client_info.get('enable', True),
                'expire_time': client_info.get('expire_time', 0)
            }
            
            self.db.log_bot_activity(
                user_id=user_id,
                command=input_data['command_type'],
                input_data=input_data,
                output_data=output_data,
                process_details=process_details,
                status='success'
            )
            
        except Exception as e:
            logger.error(f"Error processing VPN link: {str(e)}")
            self.db.log_bot_activity(
                user_id=user_id,
                command=input_data['command_type'],
                input_data=input_data,
                process_details=process_details,
                status='error',
                error=str(e)
            )
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

    @handle_errors
    def handle_info(self, message: Message):
        """Handle /info command to show system and user information"""
        user_id = message.from_user.id
        input_data = {
            'command': 'info',
            'text': message.text
        }
        process_details = {}
        
        try:
            # Ensure user exists and update their info
            if message.from_user:
                user_info = {
                    'id': message.from_user.id,
                    'username': message.from_user.username,
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name,
                    'language_code': message.from_user.language_code
                }
                self.db.ensure_user_exists(user_info)
                process_details['user_update'] = 'success'

            # Get system information
            import psutil
            import platform
            from datetime import datetime
            
            # System information
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            process_details['system_info'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent
            }
            
            # Get user information
            user_info = self.db.get_user_info(user_id, by_telegram=True)
            process_details['user_info_found'] = bool(user_info)
            
            response = f"""
💻 *اطلاعات سیستم*
━━━━━━━━━━━━━━━
🖥 سیستم عامل: `{escape_markdown(platform.system())} {escape_markdown(platform.release())}`
⚡️ مصرف CPU: `{cpu_percent}%`
💾 حافظه: `{format_size(memory.used)}/{format_size(memory.total)} ({memory.percent}%)`
💿 دیسک: `{format_size(disk.used)}/{format_size(disk.total)} ({disk.percent}%)`

👤 *اطلاعات کاربر*
━━━━━━━━━━━━━━━
"""
            if user_info:
                response += f"""
📧 ایمیل: `{escape_markdown(user_info['email'] or 'تنظیم نشده')}`
📊 وضعیت: `{escape_markdown(user_info['status'])}`
📈 حجم کل: `{format_size(user_info['traffic_limit'])}`
📉 مصرف شده: `{format_size(user_info['total_usage'])}`
⏰ تاریخ انقضا: `{escape_markdown(user_info['expiry_date'] or 'تنظیم نشده')}`
🔄 آخرین اتصال: `{escape_markdown(str(user_info.get('last_connection', 'هیچ‌وقت')))}`
"""
            else:
                response += "❌ اطلاعات کاربری یافت نشد\\."

            self.bot.reply_to(message, response, parse_mode='MarkdownV2')
            logger.info(f"System info sent to user {message.from_user.id}")
            
            # Log the activity with all details
            output_data = {
                'system_info': {
                    'os': f"{platform.system()} {platform.release()}",
                    'cpu_percent': cpu_percent,
                    'memory': {
                        'total': memory.total,
                        'used': memory.used,
                        'percent': memory.percent
                    },
                    'disk': {
                        'total': disk.total,
                        'used': disk.used,
                        'percent': disk.percent
                    }
                },
                'user_info': user_info if user_info else None
            }
            
            self.db.log_bot_activity(
                user_id=user_id,
                command='info',
                input_data=input_data,
                output_data=output_data,
                process_details=process_details,
                status='success'
            )
            
        except ImportError as e:
            error_msg = "بسته نظارت بر سیستم نصب نشده است"
            logger.error("psutil module not installed")
            self.db.log_bot_activity(
                user_id=user_id,
                command='info',
                input_data=input_data,
                process_details=process_details,
                status='error',
                error=error_msg
            )
            raise ValidationError(error_msg)
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}\n{traceback.format_exc()}")
            self.db.log_bot_activity(
                user_id=user_id,
                command='info',
                input_data=input_data,
                process_details=process_details,
                status='error',
                error=str(e)
            )
            raise

    def register_handlers(self):
        """Register all user command handlers"""
        try:
            logger.info("Registering user command handlers")
            
            # Register command handlers
            self.bot.message_handler(commands=['status'])(self.handle_status)
            self.bot.message_handler(commands=['usage'])(self.handle_usage)
            self.bot.message_handler(commands=['info'])(self.handle_info)
            
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
                details={'handlers': ['status', 'usage', 'info', 'direct_link']}
            )
        except Exception as e:
            logger.error(f"Failed to register user handlers: {str(e)}\n{traceback.format_exc()}")
            raise 