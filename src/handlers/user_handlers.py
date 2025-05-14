from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold
from ..utils.panel_api import PanelAPI
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
from ..utils.keyboards import (
    create_client_status_keyboard,
    create_traffic_options_keyboard,
    create_expiry_options_keyboard
)
import traceback
from functools import wraps
from datetime import datetime
from typing import Optional
from telebot import types
from sqlalchemy.orm import Session
import pytz

from ..models.models import TelegramUser, VPNClient, UserActivity
from ..models.base import SessionLocal

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
            total = client_info.get('total_gb', 0)
            
            # Convert total from GB to bytes if it's not zero
            if total > 0:
                total = total * (1024 ** 3)  # Convert GB to bytes
            
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
    def handle_usage(self, message: Message):
        """Handle /usage command or direct VPN link"""
        try:
            # Extract VPN link from message
            if message.text.startswith('/usage'):
                # Remove command and get the link
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    self.bot.reply_to(
                        message,
                        "❌ لطفا لینک VPN را وارد کنید\\.\n*نمونه*: `/usage vless://...`",
                        parse_mode='MarkdownV2'
                    )
                    return
                vpn_link = parts[1]
            else:
                # Direct link
                vpn_link = message.text
                
            # Extract identifier from link
            identifier = self.validate_vpn_link(vpn_link)
            if not identifier:
                self.bot.reply_to(
                    message,
                    "❌ لینک نامعتبر است\\.",
                    parse_mode='MarkdownV2'
                )
                return
                
            # Get client info
            client_info = self.panel_api.get_client_info(identifier)
            if not client_info:
                self.bot.reply_to(
                    message,
                    "❌ اطلاعات کاربر یافت نشد\\.",
                    parse_mode='MarkdownV2'
                )
                return
                
            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data=f"refresh_{identifier}"
                )
            )
            
            # Add admin buttons if user is admin
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if user and user.is_admin:
                    keyboard.row(
                        InlineKeyboardButton(
                            "🔄 ریست ترافیک",
                            callback_data=f"reset_{identifier}"
                        ),
                        InlineKeyboardButton(
                            "⚡️ تمدید",
                            callback_data=f"extend_{identifier}"
                        )
                    )
                    keyboard.row(
                        InlineKeyboardButton(
                            "✏️ ویرایش",
                            callback_data=f"edit_{identifier}"
                        ),
                        InlineKeyboardButton(
                            "❌ حذف",
                            callback_data=f"delete_{identifier}"
                        )
                    )
            
            # Generate status text
            status_text = self._generate_status_text(client_info)
            
            # Send response
            self.bot.reply_to(
                message,
                status_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )
            
            # Log activity
            self._log_activity(message.from_user.id, "CHECK_STATUS", identifier)
            
        except Exception as e:
            logger.error(f"Error handling usage command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در پردازش درخواست\\.",
                parse_mode='MarkdownV2'
            )

    @handle_errors
    def handle_callback(self, call: CallbackQuery):
        """Handle callback queries"""
        try:
            # First, check if this is a refresh_info callback
            if call.data == "refresh_info":
                self._refresh_info(call)
                return

            # For all other callbacks
            action, *params = call.data.split('_')
            user_id = call.from_user.id if call.from_user else None
            
            if not user_id:
                logger.error("No user ID in callback query")
                self.bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست")
                return

            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=user_id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return

            # Handle different actions
            if action == "refresh":
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                self._handle_refresh(call, identifier)
                
            elif action == "reset" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                success = self.panel_api.reset_traffic(identifier)
                if success:
                    self.bot.answer_callback_query(call.id, "✅ حجم مصرفی ریست شد")
                    self._handle_refresh(call, identifier)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در ریست حجم")
                
            elif action == "extend" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                keyboard = InlineKeyboardMarkup(row_width=3)
                
                # Add duration buttons
                duration_buttons = []
                for days in [7, 15, 30, 60, 90, 180, 365]:
                    duration_buttons.append(
                        InlineKeyboardButton(
                            f"{days} روز",
                            callback_data=f"setexpiry_{identifier}_{days}"
                        )
                    )
                
                # Add buttons in rows of 3
                for i in range(0, len(duration_buttons), 3):
                    keyboard.row(*duration_buttons[i:min(i+3, len(duration_buttons))])
                
                # Add unlimited and back buttons
                keyboard.row(
                    InlineKeyboardButton("♾️ نامحدود", callback_data=f"setexpiry_{identifier}_0")
                )
                keyboard.row(
                    InlineKeyboardButton("🔙 بازگشت", callback_data=f"refresh_{identifier}")
                )
                
                self.bot.edit_message_text(
                    "🗓️ *مدت زمان تمدید را انتخاب کنید:*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
            elif action == "edit" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                keyboard = InlineKeyboardMarkup(row_width=2)
                
                # Add edit options
                keyboard.row(
                    InlineKeyboardButton("📦 تنظیم حجم", callback_data=f"setvolume_{identifier}"),
                    InlineKeyboardButton("📅 تنظیم زمان", callback_data=f"setdate_{identifier}")
                )
                keyboard.row(
                    InlineKeyboardButton("♾️ نامحدود", callback_data=f"setunlimited_{identifier}"),
                    InlineKeyboardButton("🔄 ریست", callback_data=f"reset_{identifier}")
                )
                keyboard.row(
                    InlineKeyboardButton("🔙 بازگشت", callback_data=f"refresh_{identifier}")
                )
                
                self.bot.edit_message_text(
                    "✏️ *گزینه مورد نظر را انتخاب کنید:*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
            elif action == "delete" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                keyboard = InlineKeyboardMarkup()
                keyboard.row(
                    InlineKeyboardButton("✅ بله", callback_data=f"confirmdelete_{identifier}"),
                    InlineKeyboardButton("❌ خیر", callback_data=f"refresh_{identifier}")
                )
                
                self.bot.edit_message_text(
                    "❗️ *آیا از حذف این کاربر اطمینان دارید؟*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
            elif action == "setexpiry" and user.is_admin:
                if len(params) < 2:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier, days = params
                success = self.panel_api.set_expiry(identifier, int(days))
                if success:
                    msg = "✅ تاریخ انقضا به نامحدود تنظیم شد" if days == "0" else f"✅ تاریخ انقضا به {days} روز تنظیم شد"
                    self.bot.answer_callback_query(call.id, msg)
                    self._handle_refresh(call, identifier)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم تاریخ انقضا")
                    
            elif action == "setvolume" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                keyboard = InlineKeyboardMarkup(row_width=3)
                
                # Add volume buttons
                volume_buttons = []
                for gb in [5, 10, 20, 50, 100, 200, 500, 1000]:
                    volume_buttons.append(
                        InlineKeyboardButton(
                            f"{gb}GB",
                            callback_data=f"setgb_{identifier}_{gb}"
                        )
                    )
                
                # Add buttons in rows of 3
                for i in range(0, len(volume_buttons), 3):
                    keyboard.row(*volume_buttons[i:min(i+3, len(volume_buttons))])
                
                # Add custom and back buttons
                keyboard.row(
                    InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"customgb_{identifier}")
                )
                keyboard.row(
                    InlineKeyboardButton("🔙 بازگشت", callback_data=f"refresh_{identifier}")
                )
                
                self.bot.edit_message_text(
                    "📦 *حجم مورد نظر را انتخاب کنید:*",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
            elif action == "setgb" and user.is_admin:
                if len(params) < 2:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier, gb = params
                success = self.panel_api.set_traffic(identifier, int(gb))
                if success:
                    self.bot.answer_callback_query(call.id, f"✅ حجم به {gb} گیگابایت تنظیم شد")
                    self._handle_refresh(call, identifier)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم حجم")
                    
            elif action == "customgb" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                msg = self.bot.edit_message_text(
                    "🔢 *لطفا حجم مورد نظر را به گیگابایت وارد کنید:*\n"
                    "مثال: `50` برای 50 گیگابایت",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='MarkdownV2'
                )
                self.bot.register_next_step_handler(msg, self._handle_custom_traffic, identifier)
                
            elif action == "setunlimited" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                success = self.panel_api.set_unlimited(identifier)
                if success:
                    self.bot.answer_callback_query(call.id, "✅ حجم به نامحدود تنظیم شد")
                    self._handle_refresh(call, identifier)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم حجم")
                    
            elif action == "confirmdelete" and user.is_admin:
                if len(params) < 1:
                    self.bot.answer_callback_query(call.id, "❌ پارامترهای ناقص")
                    return
                    
                identifier = params[0]
                success = self.panel_api.delete_client(identifier)
                if success:
                    self.bot.answer_callback_query(call.id, "✅ کاربر با موفقیت حذف شد")
                    self.bot.delete_message(call.message.chat.id, call.message.message_id)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در حذف کاربر")
                    self._handle_refresh(call, identifier)
                
            else:
                self.bot.answer_callback_query(call.id, "❌ عملیات نامعتبر")
                
        except Exception as e:
            logger.error(f"Error handling callback: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست")

    def _refresh_info(self, call: CallbackQuery):
        """Refresh system and user information"""
        try:
            # Get user info from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return
                    
                # Get client info from panel API if email exists
                client_info = None
                if hasattr(user, 'email') and user.email:
                    client_info = self.panel_api.get_client_info(email=user.email)
                
            # Format system info
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Create inline keyboard for refresh
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data="refresh_info"
                )
            )
            
            # Format response message
            response = f"""
👤 *اطلاعات کاربر*
━━━━━━━━━━━━━━━
🆔 شناسه: `{user.telegram_id}`
📧 ایمیل: `{escape_markdown(user.email if hasattr(user, 'email') and user.email else "تنظیم نشده")}`
"""

            if client_info:
                # Calculate traffic values
                up = client_info.get('up', 0)
                down = client_info.get('down', 0)
                total = client_info.get('total', 0)
                total_usage = up + down
                
                # Format expiry date
                expiry_timestamp = client_info.get('expire_time', 0)
                if expiry_timestamp == 0:
                    expiry_text = "نامحدود"
                else:
                    expiry_date = datetime.fromtimestamp(expiry_timestamp/1000)
                    expiry_text = format_date(expiry_timestamp/1000)
                
                # Get last connection time
                last_connection = client_info.get('last_connection', None)
                if last_connection:
                    last_connection_text = format_date(last_connection/1000)
                else:
                    last_connection_text = "هیچوقت"
                
                response += f"""
📊 *اطلاعات سرویس*
━━━━━━━━━━━━━━━
📦 حجم کل: `{format_size(total) if total > 0 else "نامحدود"}`
📈 مصرف شده: `{format_size(total_usage)}`
🔼 آپلود: `{format_size(up)}`
🔽 دانلود: `{format_size(down)}`
📅 تاریخ انقضا: `{escape_markdown(expiry_text)}`
🕒 آخرین اتصال: `{escape_markdown(last_connection_text)}`
⚡️ وضعیت: `{'🟢 فعال' if client_info.get('enable', True) else '🔴 غیرفعال'}`
"""
            
            # Update message
            self.bot.edit_message_text(
                response,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )
            
            self.bot.answer_callback_query(call.id, "✅ اطلاعات بروزرسانی شد")
            
        except Exception as e:
            logger.error(f"Error refreshing info: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(call.id, "❌ خطا در بروزرسانی اطلاعات")

    def _handle_custom_traffic(self, message: Message, client_uuid: str):
        """Handle custom traffic input"""
        try:
            gb = int(message.text)
            if gb <= 0:
                self.bot.reply_to(message, "❌ لطفا عدد بزرگتر از صفر وارد کنید")
                return
                
            success = self.panel_api.set_traffic(client_uuid, gb)
            if success:
                status_text = self._generate_status_text(self.panel_api.get_client_info(uuid=client_uuid))
                keyboard = create_client_status_keyboard(client_uuid, True)
                self.bot.send_message(
                    message.chat.id,
                    f"✅ حجم به {gb} گیگابایت تنظیم شد\n\n{status_text}",
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
            else:
                self.bot.reply_to(message, "❌ خطا در تنظیم حجم")
        except ValueError:
            self.bot.reply_to(message, "❌ لطفا یک عدد صحیح وارد کنید")
        except Exception as e:
            logger.error(f"Error handling custom traffic: {str(e)}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")
            
    def _refresh_status(self, call: CallbackQuery, client_uuid: str):
        """Refresh client status message"""
        try:
            client_info = self.panel_api.get_client_info(uuid=client_uuid)
            if not client_info:
                self.bot.answer_callback_query(call.id, "❌ اطلاعات کاربر یافت نشد")
                return
                
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return
                    
            status_text = self._generate_status_text(client_info)
            keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
            
            self.bot.edit_message_text(
                status_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )
            
            self.bot.answer_callback_query(call.id, "✅ اطلاعات بروزرسانی شد")
            self._log_activity(call.from_user.id, "REFRESH_STATUS", client_uuid)
            
        except Exception as e:
            logger.error(f"Error refreshing status: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ خطا در بروزرسانی اطلاعات")

    @handle_errors
    def handle_info(self, message: Message):
        """Handle /info command to show system and user information"""
        try:
            # Get user info from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ اطلاعات کاربر یافت نشد\\.", parse_mode='MarkdownV2')
                    return
                    
                # Get client info from panel API if email exists
                client_info = None
                if hasattr(user, 'email') and user.email:
                    client_info = self.panel_api.get_client_info(email=user.email)
                
            # Format system info
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Create inline keyboard for refresh
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data="refresh_info"
                )
            )
            
            # Format response message
            response = f"""
👤 *اطلاعات کاربر*
━━━━━━━━━━━━━━━
🆔 شناسه: `{user.telegram_id}`
📧 ایمیل: `{escape_markdown(user.email if hasattr(user, 'email') and user.email else "تنظیم نشده")}`
"""

            if client_info:
                # Calculate traffic values
                up = client_info.get('up', 0)
                down = client_info.get('down', 0)
                total = client_info.get('total', 0)
                total_usage = up + down
                
                # Format expiry date
                expiry_timestamp = client_info.get('expire_time', 0)
                if expiry_timestamp == 0:
                    expiry_text = "نامحدود"
                else:
                    expiry_date = datetime.fromtimestamp(expiry_timestamp/1000)
                    expiry_text = format_date(expiry_timestamp/1000)
                
                # Get last connection time
                last_connection = client_info.get('last_connection', None)
                if last_connection:
                    last_connection_text = format_date(last_connection/1000)
                else:
                    last_connection_text = "هیچوقت"
                
                response += f"""
📊 *اطلاعات سرویس*
━━━━━━━━━━━━━━━
📦 حجم کل: `{format_size(total) if total > 0 else "نامحدود"}`
📈 مصرف شده: `{format_size(total_usage)}`
🔼 آپلود: `{format_size(up)}`
🔽 دانلود: `{format_size(down)}`
📅 تاریخ انقضا: `{escape_markdown(expiry_text)}`
🕒 آخرین اتصال: `{escape_markdown(last_connection_text)}`
⚡️ وضعیت: `{'🟢 فعال' if client_info.get('enable', True) else '🔴 غیرفعال'}`
"""
            
            self.bot.reply_to(message, response, parse_mode='MarkdownV2', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error in handle_info: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در دریافت اطلاعات\\.", parse_mode='MarkdownV2')
    
    def _generate_status_text(self, client_info: dict) -> str:
        """Generate formatted status text"""
        try:
            # Calculate traffic values
            up = client_info.get('up', 0)
            down = client_info.get('down', 0)
            total = client_info.get('total_gb', 0)
            
            # Convert total from GB to bytes if it's not zero
            if total > 0:
                total = total * (1024 ** 3)  # Convert GB to bytes
            
            total_usage = up + down
            remaining = max(0, total - total_usage) if total > 0 else float('inf')
            usage_percent = (total_usage / total * 100) if total > 0 else 0
            
            # Format expiry date
            expiry_timestamp = client_info.get('expire_time', 0)
            if expiry_timestamp == 0:
                expiry_text = "نامحدود"
                days_left = "∞"
            else:
                expiry_date = datetime.fromtimestamp(expiry_timestamp/1000)
                days_left = (expiry_date - datetime.now()).days
                expiry_text = expiry_date.strftime("%Y-%m-%d")
            
            # Get current time in Tehran timezone
            tehran_tz = pytz.timezone('Asia/Tehran')
            current_time = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M:%S")
            
            return f"""
📊 *وضعیت سرویس شما*
━━━━━━━━━━━━━━━

👤 *مشخصات*:
• نام: `{escape_markdown(client_info.get('remark', 'بدون نام'))}`
• ایمیل: `{escape_markdown(client_info.get('email', 'نامشخص'))}`
• وضعیت: `{'🟢 فعال' if client_info.get('enable', True) else '🔴 غیرفعال'}`

📈 *آمار مصرف*:
• حجم کل: `{format_size(total) if total > 0 else 'نامحدود'}`
• مصرف شده: `{format_size(total_usage)}`
• باقیمانده: `{format_size(remaining) if total > 0 else 'نامحدود'}`
• درصد مصرف: `{f'{usage_percent:.1f}%' if total > 0 else '0%'}`

🔄 *جزئیات ترافیک*:
• آپلود: `{format_size(up)}`
• دانلود: `{format_size(down)}`

⏰ *زمان*:
• تاریخ انقضا: `{escape_markdown(expiry_text)}`
• روزهای باقیمانده: `{escape_markdown(str(days_left))}`
• آخرین بروزرسانی: `{escape_markdown(current_time)}`
"""
        except Exception as e:
            logger.error(f"Error generating status text: {str(e)}")
            return "❌ خطا در نمایش اطلاعات"
    
    def _log_activity(self, user_id: int, activity_type: str, target_uuid: str):
        """Log user activity"""
        try:
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=user_id).first()
                if not user:
                    return
                    
                activity = UserActivity(
                    user_id=user.id,
                    activity_type=activity_type,
                    target_uuid=target_uuid,
                    details={
                        'timestamp': datetime.now().isoformat()
                    }
                )
                db.add(activity)
                db.commit()
        except Exception as e:
            logger.error(f"Error logging activity: {str(e)}")
    
    def register_handlers(self):
        """Register all user command handlers"""
        # Register command handlers
        self.bot.message_handler(commands=['usage'])(self.handle_usage)
        self.bot.message_handler(commands=['info'])(self.handle_info)
        self.bot.message_handler(regexp='^vless://.*')(self.handle_direct_link)
        
    def handle_direct_link(self, message: Message):
        """Handle direct VPN link without command"""
        # Treat it same as /usage command
        self.handle_usage(message)
        
    def _handle_refresh(self, call: CallbackQuery, identifier: str):
        """Handle refresh callback for client status"""
        try:
            logger.info(f"Handling refresh for identifier: {identifier}")
            
            # Get client info
            client_info = self.panel_api.get_client_info(uuid=identifier)
            if not client_info:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ اطلاعات کاربر یافت نشد",
                    show_alert=True
                )
                return
                
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(
                        call.id,
                        "❌ کاربر یافت نشد",
                        show_alert=True
                    )
                    return
                    
            # Create keyboard with appropriate buttons
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data=f"refresh_{identifier}"
                )
            )
            
            # Add admin buttons if user is admin
            if user.is_admin:
                keyboard.row(
                    InlineKeyboardButton(
                        "🔄 ریست ترافیک",
                        callback_data=f"reset_{identifier}"
                    ),
                    InlineKeyboardButton(
                        "⚡️ تمدید",
                        callback_data=f"extend_{identifier}"
                    )
                )
                keyboard.row(
                    InlineKeyboardButton(
                        "✏️ ویرایش",
                        callback_data=f"edit_{identifier}"
                    ),
                    InlineKeyboardButton(
                        "❌ حذف",
                        callback_data=f"delete_{identifier}"
                    )
                )
            
            # Generate status text
            status_text = self._generate_status_text(client_info)
            
            try:
                # Try to update existing message
                self.bot.edit_message_text(
                    status_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
                self.bot.answer_callback_query(
                    call.id,
                    "✅ اطلاعات بروزرسانی شد",
                    show_alert=False
                )
                
            except telebot.apihelper.ApiException as e:
                if "message is not modified" in str(e).lower():
                    # If content hasn't changed, just show notification
                    self.bot.answer_callback_query(
                        call.id,
                        "✅ اطلاعات بروز است",
                        show_alert=False
                    )
                else:
                    # For other API errors, try to send a new message
                    try:
                        self.bot.delete_message(
                            call.message.chat.id,
                            call.message.message_id
                        )
                    except:
                        pass
                        
                    self.bot.send_message(
                        call.message.chat.id,
                        status_text,
                        reply_markup=keyboard,
                        parse_mode='MarkdownV2'
                    )
                    
                    self.bot.answer_callback_query(
                        call.id,
                        "✅ پیام جدید ارسال شد",
                        show_alert=True
                    )
            
            # Log the refresh action
            self._log_activity(call.from_user.id, "REFRESH_STATUS", identifier)
            
        except Exception as e:
            logger.error(f"Error refreshing status: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در بروزرسانی اطلاعات",
                show_alert=True
            ) 