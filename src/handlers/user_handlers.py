from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot import apihelper
from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold, format_remaining_time, format_total, format_remaining_days, convert_bytes
from ..utils.panel_api import PanelAPI
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
from ..utils.first_version import format_remaining_days as first_version_format_remaining_days
from ..utils.keyboards import (
    create_client_status_keyboard,
    create_traffic_options_keyboard,
    create_expiry_options_keyboard,
    create_stats_keyboard
)
import traceback
from functools import wraps
from datetime import datetime
from typing import Optional
from telebot import types
from sqlalchemy.orm import Session
import pytz
import os
from typing import Dict, Any, List, Union
from persiantools.jdatetime import JalaliDateTime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import logging
import json
import platform
import asyncio
from tests.test_date_formatting import test_specific_client

from ..models.models import TelegramUser, VPNClient, UserActivity
from ..models.base import SessionLocal

# Initialize custom logger
logger = CustomLogger("UserHandler")

def configure_retries(session):
    """Configure retry strategy for requests"""
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def handle_errors(func):
    """Decorator for handling errors in handler methods"""
    @wraps(func)
    def wrapper(self, message: Message, *args, **kwargs):
        try:
            return func(self, message, *args, **kwargs)
        except apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                return
            elif "query is too old" in str(e).lower():
                return
            logger.error(f"API Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.reply_to(
                    message,
                    f"""
{format_bold('⚠️ خطا در ارتباط با سرور')}
━━━━━━━━━━━━━━━━━━

• مشکل: خطا در ارتباط با سرور تلگرام
• راه حل: لطفاً چند دقیقه صبر کنید و دوباره تلاش کنید
• وضعیت: {format_code('موقت')}

{format_bold('💡 راهنمایی')}
اگر مشکل همچنان ادامه داشت، با پشتیبانی تماس بگیرید
""",
                    parse_mode='MarkdownV2'
                )
            except:
                pass
        except requests.exceptions.RequestException as e:
            logger.error(f"Network Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.reply_to(
                    message,
                    f"""
{format_bold('⚠️ خطا در اتصال به اینترنت')}
━━━━━━━━━━━━━━━━━━

• مشکل: عدم دسترسی به اینترنت
• راه حل: اتصال اینترنت خود را بررسی کنید
• وضعیت: {format_code('موقت')}

{format_bold('💡 راهنمایی')}
پس از اطمینان از اتصال اینترنت، دوباره تلاش کنید
""",
                    parse_mode='MarkdownV2'
                )
            except:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.reply_to(
                    message,
                    f"""
{format_bold('⚠️ خطای غیرمنتظره')}
━━━━━━━━━━━━━━━━━━

• مشکل: خطای سیستمی
• راه حل: لطفاً چند دقیقه صبر کنید
• وضعیت: {format_code('موقت')}

{format_bold('💡 راهنمایی')}
اگر مشکل همچنان ادامه داشت، با پشتیبانی تماس بگیرید
""",
                    parse_mode='MarkdownV2'
                )
            except:
                pass
    return wrapper

class ExceptionHandler:
    def __init__(self, logger):
        self.logger = logger

    def handle(self, exception):
        """Handle exceptions during bot operation"""
        if isinstance(exception, apihelper.ApiTelegramException):
            if "message is not modified" in str(exception).lower():
                return True  # Handled successfully
            elif "query is too old" in str(exception).lower():
                return True  # Handled successfully
        
        self.logger.error(f"Unhandled exception: {str(exception)}\n{traceback.format_exc()}")
        return False  # Not handled

class UserHandler:
    def __init__(self, bot: TeleBot, db: Database, panel_api: PanelAPI):
        self.bot = bot
        self.db = db
        self.panel_api = panel_api
        self.logger = CustomLogger("UserHandler")
        
        # Set up exception handler
        self.bot.exception_handler = ExceptionHandler(self.logger)
        
        # Configure retry strategy for network requests
        if hasattr(self.bot, 'session'):
            self.bot.session = configure_retries(self.bot.session)
        
        # Configure retry for panel API session if available
        if hasattr(self.panel_api, 'session'):
            self.panel_api.session = configure_retries(self.panel_api.session)
        
        logger.info("UserHandler initialized with retry configuration")

    def validate_vpn_link(self, link: str) -> str:
        """Validate VPN link format and extract identifier"""
        if not link or not isinstance(link, str):
            raise ValidationError(f"""
{format_bold('⚠️ خطا در لینک اشتراک')}
━━━━━━━━━━━━━━━━━━

• مشکل: لینک اشتراک نامعتبر است
• راه حل: لطفاً لینک را به درستی وارد کنید
• وضعیت: {format_code('دائمی')}

{format_bold('💡 راهنمایی')}
لینک اشتراک باید با vless:// شروع شود
""")
        
        if not link.lower().startswith('vless://'):
            raise ValidationError(f"""
{format_bold('⚠️ خطا در فرمت لینک')}
━━━━━━━━━━━━━━━━━━

• مشکل: فرمت لینک اشتراک نادرست است
• راه حل: لینک باید با vless:// شروع شود
• وضعیت: {format_code('دائمی')}

{format_bold('💡 راهنمایی')}
لطفاً از صحت لینک اشتراک اطمینان حاصل کنید
""")
        
        identifier = self.panel_api.extract_identifier_from_link(link)
        if not identifier:
            raise ValidationError(f"""
{format_bold('⚠️ خطا در شناسه کاربری')}
━━━━━━━━━━━━━━━━━━

• مشکل: شناسه کاربری در لینک یافت نشد
• راه حل: لینک اشتراک را از پنل مدیریت دریافت کنید
• وضعیت: {format_code('دائمی')}

{format_bold('💡 راهنمایی')}
لینک اشتراک باید شامل شناسه کاربری معتبر باشد
""")
        
        return identifier

    def _normalize_timestamp(self, timestamp: Any) -> float:
        """Normalize timestamp to seconds."""
        if timestamp is None or timestamp == "":
            return 0.0
        try:
            timestamp = float(timestamp)
            if timestamp > 1e12:  # Likely milliseconds
                timestamp /= 1000
            return timestamp
        except (ValueError, TypeError):
            logger.error(f"Invalid timestamp format: {timestamp} (type: {type(timestamp)})")
            return 0.0



    @handle_errors
    def process_vpn_link(self, message: Message, link: str):
        """Process a VPN link and show status"""
        try:
            # Extract identifier from link
            identifier = self.panel_api.extract_identifier_from_link(link)
            if not identifier:
                self.bot.reply_to(message, "❌ لینک نامعتبر است")
                return

            # Get client info
            client_info = self.panel_api.get_client_info(uuid=identifier)
            if not client_info:
                self.bot.reply_to(message, "❌ اطلاعات کاربر یافت نشد")
                return

            # Log complete client info for debugging
            logger.info(f"Complete client info: {json.dumps(client_info, indent=2)}")

            # Get traffic values
            down_bytes = client_info.get('down', 0)
            up_bytes = client_info.get('up', 0)
            total_bytes = client_info.get('total', 0)
            total_usage = down_bytes + up_bytes

            # Format traffic values with appropriate units
            up_str = format_size(up_bytes)
            down_str = format_size(down_bytes)
            total_use_str = format_size(total_usage)
            formatted_total = format_size(total_bytes) if total_bytes > 0 else "نامحدود"

            # Get current time in Tehran timezone
            time = datetime.now(pytz.timezone('Asia/Tehran'))
            jtime = time.strftime('%Y/%m/%d %H:%M:%S')

            # Build status string
            Enable = "فعال 🟢" if client_info.get('enable', True) else "غیرفعال 🔴"
            is_online = "آنلاین 🟢" if client_info.get('is_online', True) else "آفلاین 🔴"
            email = client_info.get('email', 'نامشخص')

            # Extract and log expiry time
            expiry_time = client_info.get('expiryTime', 0)
            logger.info(f"Raw expiry_time from client_info: {expiry_time}")
            logger.info(f"Expiry time type: {type(expiry_time)}")
            logger.info(f"All client_info keys: {list(client_info.keys())}")
            
            # Format expiry time using first version's function
            formatted_remaining_days = first_version_format_remaining_days(expiry_time)
            logger.info(f"Formatted remaining days: {formatted_remaining_days}")

            # Format the message with escaped special characters
            formatted_text = (
                f"📧 ایمیل : {escape_markdown(email)}\n"
                f"وضعیت : {escape_markdown(Enable)}\n"
                f"آنلاین : {escape_markdown(is_online)}\n"
                f"🔼آپلود : {escape_markdown(up_str)}\n"
                f"🔽دانلود : {escape_markdown(down_str)}\n"
                f"➕مصرف کلی : {escape_markdown(total_use_str)}\n"
                f"🟥حجم خریداری شده : {escape_markdown(formatted_total)}\n"
                f"📅انقضا : {escape_markdown(formatted_remaining_days)}\n"
                f"\n⏳آخرین آپدیت مقادیر : {escape_markdown(jtime)}"
            )

            # Create keyboard with refresh button
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"refresh_{identifier}")
            )

            # Create keyboard with admin buttons if needed
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                keyboard = create_client_status_keyboard(identifier, user.is_admin if user else False)

            # Send message
            self.bot.reply_to(
                message,
                formatted_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "USAGE", link)

        except Exception as e:
            logger.error(f"Error processing VPN link: {str(e)}")
            self.bot.reply_to(message, "❌ خطا در پردازش لینک")

    @handle_errors
    def handle_usage(self, message: Message):
        """Handle usage command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            # Get VPN link from message
            vpn_link = message.text.split()[1] if len(message.text.split()) > 1 else None
            if not vpn_link:
                self.bot.reply_to(message, "❌ لینک VPN را وارد کنید")
                return

            # Validate link and get identifier
            try:
                identifier = self.validate_vpn_link(vpn_link)
            except ValidationError as e:
                self.bot.reply_to(message, str(e))
                return

            # Get client info using identifier
            client_info = self.panel_api.get_client_info(uuid=identifier)
            if not client_info:
                self.bot.reply_to(message, "❌ کاربر یافت نشد")
                return

            # Generate status text
            status_text = self._generate_status_text(client_info)

            # Create keyboard with admin buttons if needed
            keyboard = create_client_status_keyboard(identifier, user.is_admin)

            # Send message
            self.bot.reply_to(
                message,
                status_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "USAGE", vpn_link)

        except Exception as e:
            logger.error(f"Error handling usage: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در دریافت اطلاعات")

    @handle_errors
    def handle_state_input(self, message: Message):
        """Handle input based on user state"""
        try:
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user or not user.state:
                    return
                    
                # Extract state and additional info
                state_parts = user.state.split(':')
                state = state_parts[0]
                
                if len(state_parts) < 2:
                    # Reset state and return if no additional info
                    user.state = None
                    db.commit()
                    self.bot.reply_to(message, "❌ خطا در پردازش درخواست. لطفا دوباره تلاش کنید.")
                    return
                    
                client_uuid = state_parts[1]
                
                # Handle custom traffic input
                if state == "ing_custom_traffic":
                    try:
                        # Validate input is a number
                        gb = int(message.text.strip())
                        if gb <= 0:
                            raise ValueError("Traffic must be positive")
                            
                        # Set traffic
                        success = self.panel_api.set_traffic(client_uuid, gb)
                        
                        if success:
                            self.bot.reply_to(
                                message, 
                                f"✅ حجم با موفقیت به {gb}GB تنظیم شد.",
                                parse_mode='MarkdownV2'
                            )
                            
                            # Refresh client info
                            client_info = self.panel_api.get_client_info(uuid=client_uuid)
                            if client_info:
                                status_text = self._generate_status_text(client_info)
                                
                                # Create keyboard
                                keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
                                
                                # Send updated status
                                self.bot.send_message(
                                    message.chat.id,
                                    status_text,
                                    reply_markup=keyboard,
                                    parse_mode='MarkdownV2'
                                )
                        else:
                            self.bot.reply_to(
                                message,
                                "❌ خطا در تنظیم حجم. لطفا بعدا دوباره تلاش کنید.",
                                parse_mode='MarkdownV2'
                            )
                    except ValueError:
                        self.bot.reply_to(
                            message,
                            "❌ خطا: لطفا یک عدد صحیح مثبت وارد کنید.",
                            parse_mode='MarkdownV2'
                        )
                        
                # Handle custom expiry input
                elif state == "ing_custom_expiry":
                    try:
                        # Validate input is a number
                        days = int(message.text.strip())
                        if days < 0:
                            raise ValueError("Days must be non-negative")
                            
                        # Set expiry
                        success = self.panel_api.set_expiry(client_uuid, days)
                        
                        if success:
                            days_text = "نامحدود" if days == 0 else f"{days} روز"
                            self.bot.reply_to(
                                message, 
                                f"✅ تاریخ انقضا با موفقیت به {days_text} تنظیم شد.",
                                parse_mode='MarkdownV2'
                            )
                            
                            # Refresh client info
                            client_info = self.panel_api.get_client_info(uuid=client_uuid)
                            if client_info:
                                status_text = self._generate_status_text(client_info)
                                
                                # Create keyboard
                                keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
                                
                                # Send updated status
                                self.bot.send_message(
                                    message.chat.id,
                                    status_text,
                                    reply_markup=keyboard,
                                    parse_mode='MarkdownV2'
                                )
                        else:
                            self.bot.reply_to(
                                message,
                                "❌ خطا در تنظیم تاریخ انقضا. لطفا بعدا دوباره تلاش کنید.",
                                parse_mode='MarkdownV2'
                            )
                    except ValueError:
                        self.bot.reply_to(
                            message,
                            "❌ خطا: لطفا یک عدد صحیح غیرمنفی وارد کنید.",
                            parse_mode='MarkdownV2'
                        )
                
                # Reset user state
                user.state = None
                db.commit()
                
        except Exception as e:
            logger.error(f"Error handling state input: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست. لطفا دوباره تلاش کنید.")
            
            # Reset user state on error
            with SessionLocal() as db:
                db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).update({"state": None})
                db.commit()

    def handle_direct_link(self, message: Message):
        """Handle direct VPN link without command"""
        # Treat it same as /usage command
        self.handle_usage(message)
        
    def _get_total_stats(self, client_uuid: str) -> str:
        """Get total statistics for a client"""
        try:
            client_info = self.panel_api.get_client_info(uuid=client_uuid)
            if not client_info:
                return "❌ اطلاعات کاربر یافت نشد"

            # Calculate traffic values
            up = int(client_info.get('up', 0))
            down = int(client_info.get('down', 0))
            total = int(client_info.get('total', 0))
            total_usage = up + down
            remaining = max(0, total - total_usage) if total > 0 else float('inf')
            usage_percent = (total_usage / total * 100) if total > 0 else 0

            # Normalize timestamps
            expire_time = self._normalize_timestamp(client_info.get('expire_time', 0))
            last_connection = self._normalize_timestamp(client_info.get('last_connection', 0))

            # Format response
            response = f"""
{format_bold('📊 آمار کلی مصرف')}
━━━━━━━━━━━━━━━

📈 {format_bold('اطلاعات حجم')}:
• کل حجم: {format_code(escape_markdown(format_size(total) if total > 0 else 'نامحدود'))}
• مصرف شده: {format_code(escape_markdown(format_size(total_usage)))}
• باقیمانده: {format_code(escape_markdown(format_size(remaining) if total > 0 else 'نامحدود'))}
• درصد مصرف: {format_code(f'{usage_percent:.1f}\\%' if total > 0 else '0\\%')}

🔄 {format_bold('جزئیات مصرف')}:
• آپلود: {format_code(escape_markdown(format_size(up)))}
• دانلود: {format_code(escape_markdown(format_size(down)))}

⏰ {format_bold('زمان')}:
• تاریخ انقضا: {format_code(escape_markdown(format_date(expire_time)))}
• آخرین اتصال: {format_code(escape_markdown(format_date(last_connection)))}
"""
            return response

        except Exception as e:
            logger.error(f"Error getting total stats: {str(e)}")
            return "❌ خطا در دریافت آمار"

    def _get_online_users(self, client_uuid: str) -> str:
        """Get list of online users for a client"""
        try:
            # Get client info first
            client_info = self.panel_api.get_client_info(uuid=client_uuid)
            if not client_info:
                return "❌ اطلاعات کاربر یافت نشد"

            # Get online users
            online_clients = self.panel_api.get_online_clients()
            
            # Create keyboard for refresh
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی لیست کاربران",
                    callback_data=f"refresh_online_users_{client_uuid}"
                )
            )
            
            # Handle case where online_users is None or empty
            if not online_clients or (isinstance(online_clients, list) and len(online_clients) == 0):
                return f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

{format_bold('📊 وضعیت')}:
• تعداد کاربران: {format_code('0')}
• وضعیت: {format_code('خالی')}

{format_bold('💡 راهنما')}:
در حال حاضر هیچ کاربری آنلاین نیست\\.
برای بروزرسانی اطلاعات از دکمه 🔄 استفاده کنید"""

            # Handle case where online_users is an error message
            if isinstance(online_clients, str):
                logger.error(f"Error getting online users: {online_clients}")
                return f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

{format_bold('❌ خطا')}:
• وضعیت: {format_code('خطا در دریافت اطلاعات')}
• جزئیات: {format_code(escape_markdown(online_clients))}

{format_bold('💡 راهنما')}:
لطفا چند لحظه صبر کنید و دوباره تلاش کنید"""

            # Ensure online_users is a list
            if not isinstance(online_clients, list):
                online_clients = [online_clients]

            # Filter online users for this client
            client_online = []
            for user in online_clients:
                if isinstance(user, dict) and user.get('uuid') == client_uuid:
                    client_online.append(user)
            
            if not client_online:
                return f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

{format_bold('📊 وضعیت')}:
• تعداد کاربران: {format_code('0')}
• وضعیت: {format_code('خالی')}

{format_bold('💡 راهنما')}:
در حال حاضر هیچ کاربری آنلاین نیست\\.
برای بروزرسانی اطلاعات از دکمه 🔄 استفاده کنید"""

            # Format response
            response = f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

{format_bold('📊 آمار کلی')}:
• تعداد کاربران: {format_code(str(len(client_online)))}
• وضعیت: {format_code('فعال')}

{format_bold('📋 لیست کاربران')}:
"""

            for i, user in enumerate(client_online, 1):
                ip = user.get('ip', 'نامشخص')
                inbound = user.get('inbound', 'نامشخص')
                last_seen = self._normalize_timestamp(user.get('last_seen', 0))
                
                # Format last seen time
                last_seen_str = format_date(last_seen) if last_seen else "نامشخص"
                
                response += f"""
{format_bold(f'👤 کاربر {i}')}:
• آی‌پی: {format_code(escape_markdown(str(ip)))}
• اینباند: {format_code(escape_markdown(str(inbound)))}
• آخرین اتصال: {format_code(escape_markdown(str(last_seen_str)))}
━━━━━━━━━━━━━━━"""
            
            response += f"""

{format_bold('💡 راهنما')}:
برای بروزرسانی اطلاعات از دکمه 🔄 استفاده کنید"""
            
            return response

        except Exception as e:
            logger.error(f"Error getting online users: {str(e)}\n{traceback.format_exc()}")
            return f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

{format_bold('❌ خطا')}:
• وضعیت: {format_code('خطا در دریافت اطلاعات')}
• جزئیات: {format_code(escape_markdown(str(e)))}

{format_bold('💡 راهنما')}:
لطفا چند لحظه صبر کنید و دوباره تلاش کنید"""

    def _generate_daily_report(self, client_uuid: str) -> str:
        """Generate daily usage report for a client"""
        try:
            client_info = self.panel_api.get_client_info(uuid=client_uuid)
            if not client_info:
                return "❌ اطلاعات کاربر یافت نشد"

            # Get today's usage
            today_up = int(client_info.get('today_up', 0))
            today_down = int(client_info.get('today_down', 0))
            today_total = today_up + today_down

            # Get total usage
            total_up = int(client_info.get('up', 0))
            total_down = int(client_info.get('down', 0))
            total_usage = total_up + total_down

            # Normalize timestamps
            created_at = self._normalize_timestamp(client_info.get('created_at', 0))
            expiry_time = self._normalize_timestamp(client_info.get('expire_time', 0))
            last_connection = self._normalize_timestamp(client_info.get('last_connection', 0))

            # Calculate days active
            if created_at > 0:
                tehran_tz = pytz.timezone('Asia/Tehran')
                now = datetime.now(tehran_tz)
                creation_date = datetime.fromtimestamp(created_at, tehran_tz)
                days_active = max(1, (now - creation_date).days)
                
                # Calculate averages
                avg_daily = total_usage / days_active if days_active > 0 else 0
                avg_monthly = avg_daily * 30
            else:
                days_active = 0
                avg_daily = 0
                avg_monthly = 0

            # Format response with proper escaping
            response = f"""
{format_bold('📋 گزارش روزانه')}
━━━━━━━━━━━━━━━

📅 {format_bold('مصرف امروز')}:
• کل: {format_code(escape_markdown(format_size(today_total)))}
• آپلود: {format_code(escape_markdown(format_size(today_up)))}
• دانلود: {format_code(escape_markdown(format_size(today_down)))}

📊 {format_bold('میانگین مصرف')}:
• روزانه: {format_code(escape_markdown(format_size(avg_daily)))}
• ماهانه: {format_code(escape_markdown(format_size(avg_monthly)))}

⏰ {format_bold('زمان')}:
• تاریخ ایجاد: {format_code(escape_markdown(format_date(created_at)))}
• روزهای فعال: {format_code(escape_markdown(str(days_active)))} روز
• تاریخ انقضا: {format_code(escape_markdown(format_date(expiry_time)))}
• زمان باقیمانده: {format_code(escape_markdown(format_remaining_time(expiry_time)))}
• آخرین اتصال: {format_code(escape_markdown(format_date(last_connection)))}

💡 {format_bold('راهنما')}:
برای بروزرسانی اطلاعات از دکمه 🔄 استفاده کنید
"""
            return response

        except Exception as e:
            logger.error(f"Error generating daily report: {str(e)}\n{traceback.format_exc()}")
            return "❌ خطا در تولید گزارش روزانه"

    def _generate_usage_graph(self, client_uuid: str) -> Optional[str]:
        """Generate usage graph for a client"""
        try:
            client_info = self.panel_api.get_client_info(uuid=client_uuid)
            if not client_info:
                return None

            # Get traffic values
            up = int(client_info.get('up', 0))
            down = int(client_info.get('down', 0))
            total = int(client_info.get('total', 0))
            total_usage = up + down
            usage_percent = (total_usage / total * 100) if total > 0 else 0

            # Calculate daily average
            created_at = self._normalize_timestamp(client_info.get('created_at', 0))
            if created_at > 0:
                tehran_tz = pytz.timezone('Asia/Tehran')
                now = datetime.now(tehran_tz)
                creation_date = datetime.fromtimestamp(created_at, tehran_tz)
                days_active = max(1, (now - creation_date).days)
                avg_daily = total_usage / days_active if days_active > 0 else 0
            else:
                avg_daily = 0

            # Format response with proper escaping
            response = f"""
{format_bold('📊 نمودار مصرف')}
━━━━━━━━━━━━━━━

📈 {format_bold('آمار مصرف')}:
• درصد مصرف: {format_code(f'{usage_percent:.1f}\\%')}
• پیشرفت: {format_code('█' * int(usage_percent/10) + '░' * (10 - int(usage_percent/10)))}

📊 {format_bold('جزئیات')}:
• حجم کل: {format_code(escape_markdown(format_size(total) if total > 0 else 'نامحدود'))}
• مصرف شده: {format_code(escape_markdown(format_size(total_usage)))}
• میانگین روزانه: {format_code(escape_markdown(format_size(avg_daily)))}

💡 {format_bold('راهنما')}:
برای بروزرسانی اطلاعات از دکمه 🔄 استفاده کنید
"""
            return response

        except Exception as e:
            logger.error(f"Error generating usage graph: {str(e)}")
            return "❌ خطا در تولید نمودار مصرف"

    @handle_errors
    def handle_message(self, message: Message):
        """Handle incoming messages"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            # Check for VLESS link in any message
            if message.text and 'vless://' in message.text.lower():
                # Extract the VLESS link
                vpn_link = message.text
                if message.text.startswith('/usage'):
                    # If it's a /usage command, extract the link from the command
                    parts = message.text.split()
                    if len(parts) > 1:
                        vpn_link = parts[1]
                    else:
                        self.bot.reply_to(message, "❌ لینک VPN را وارد کنید")
                        return
                else:
                    # If it's not a command, use the entire message as the link
                    vpn_link = message.text.strip()

                # Process the VPN link
                self.process_vpn_link(message, vpn_link)
                return

            # Handle commands
            if message.text and message.text.startswith('/'):
                command = message.text.split()[0].lower()
                if command == '/start':
                    self.handle_start(message)
                elif command == '/help':
                    self.handle_help(message)
                elif command == '/usage':
                    self.handle_usage(message)
                elif command == '/admin' and user.is_admin:
                    self.handle_admin(message)
                elif command == '/system_info' and user.is_admin:
                    self.handle_system_info(message)
                elif command == '/online_users' and user.is_admin:
                    self.handle_online_users(message)
                elif command == '/total_stats' and user.is_admin:
                    self.handle_total_stats(message)
                elif command == '/daily_report' and user.is_admin:
                    self.handle_daily_report(message)
                elif command == '/usage_graph' and user.is_admin:
                    self.handle_usage_graph(message)
                else:
                    self.bot.reply_to(message, "❌ دستور نامعتبر است")
                return

            # Default response for other messages
            self.bot.reply_to(message, "❌ پیام نامعتبر است")

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش پیام")

    @handle_errors
    def handle_admin(self, message: Message):
        """Handle /admin command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Send admin panel message
            admin_text = (
                "👨‍💼 *پنل مدیریت*\n\n"
                "دستورات موجود:\n"
                "• `/system_info` \\- اطلاعات سیستم\n"
                "• `/online_users` \\- کاربران آنلاین\n"
                "• `/total_stats` \\- آمار کلی\n"
                "• `/daily_report` \\- گزارش روزانه\n"
                "• `/usage_graph` \\- نمودار مصرف"
            )

            self.bot.reply_to(
                message,
                admin_text,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "ADMIN", None)

        except Exception as e:
            logger.error(f"Error handling admin command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_online_users(self, message: Message):
        """Handle /online_users command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Get online users
            online_users = self.panel_api.get_online_users()
            if not online_users:
                self.bot.reply_to(message, "❌ خطا در دریافت لیست کاربران آنلاین")
                return

            # Format online users list
            online_users_text = f"""
{format_bold('👥 کاربران آنلاین')}
━━━━━━━━━━━━━━━

"""
            for user in online_users:
                online_users_text += f"• {format_code(user['email'])}\n"

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی لیست کاربران",
                    callback_data="refresh_online_users"
                )
            )

            # Send message
            self.bot.reply_to(
                message,
                online_users_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "ONLINE_USERS", None)

        except Exception as e:
            logger.error(f"Error handling online users command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_total_stats(self, message: Message):
        """Handle /total_stats command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Get total stats
            total_stats = self.panel_api.get_total_stats()
            if not total_stats:
                self.bot.reply_to(message, "❌ خطا در دریافت آمار کلی")
                return

            # Format total stats
            total_stats_text = f"""
{format_bold('📊 آمار کلی')}
━━━━━━━━━━━━━━━

{format_bold('👥 کاربران')}:
• کل: {format_code(str(total_stats['total_users']))}
• آنلاین: {format_code(str(total_stats['online_users']))}
• غیرفعال: {format_code(str(total_stats['inactive_users']))}

{format_bold('📈 ترافیک')}:
• کل: {format_code(format_size(total_stats['total_traffic']))}
• آپلود: {format_code(format_size(total_stats['total_upload']))}
• دانلود: {format_code(format_size(total_stats['total_download']))}

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: {format_code(format_date(time.time()))}
• ساعت: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی آمار",
                    callback_data="refresh_total_stats"
                )
            )

            # Send message
            self.bot.reply_to(
                message,
                total_stats_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "TOTAL_STATS", None)

        except Exception as e:
            logger.error(f"Error handling total stats command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_daily_report(self, message: Message):
        """Handle /daily_report command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Get daily report
            daily_report = self.panel_api.get_daily_report()
            if not daily_report:
                self.bot.reply_to(message, "❌ خطا در دریافت گزارش روزانه")
                return

            # Format daily report
            daily_report_text = f"""
{format_bold('📅 گزارش روزانه')}
━━━━━━━━━━━━━━━

{format_bold('👥 کاربران')}:
• جدید: {format_code(str(daily_report['new_users']))}
• حذف شده: {format_code(str(daily_report['deleted_users']))}
• فعال: {format_code(str(daily_report['active_users']))}

{format_bold('📈 ترافیک')}:
• کل: {format_code(format_size(daily_report['total_traffic']))}
• آپلود: {format_code(format_size(daily_report['total_upload']))}
• دانلود: {format_code(format_size(daily_report['total_download']))}

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: {format_code(format_date(time.time()))}
• ساعت: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی گزارش",
                    callback_data="refresh_daily_report"
                )
            )

            # Send message
            self.bot.reply_to(
                message,
                daily_report_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "DAILY_REPORT", None)

        except Exception as e:
            logger.error(f"Error handling daily report command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_usage_graph(self, message: Message):
        """Handle /usage_graph command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Get usage graph
            usage_graph = self.panel_api.get_usage_graph()
            if not usage_graph:
                self.bot.reply_to(message, "❌ خطا در دریافت نمودار مصرف")
                return

            # Format usage graph
            usage_graph_text = f"""
{format_bold('📊 نمودار مصرف')}
━━━━━━━━━━━━━━━

{format_bold('📈 ترافیک')}:
• کل: {format_code(format_size(usage_graph['total_traffic']))}
• آپلود: {format_code(format_size(usage_graph['total_upload']))}
• دانلود: {format_code(format_size(usage_graph['total_download']))}

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: {format_code(format_date(time.time()))}
• ساعت: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی نمودار",
                    callback_data="refresh_usage_graph"
                )
            )

            # Send message
            self.bot.reply_to(
                message,
                usage_graph_text,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "USAGE_GRAPH", None)

        except Exception as e:
            logger.error(f"Error handling usage graph command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    def _generate_status_text(self, client_info: dict) -> str:
        """Generate formatted status text from client info."""
        try:
            logger.info(f"Generating status text for client: {client_info.get('email', 'unknown')}")
            
            # Get traffic values
            up = int(client_info.get('up', 0))
            down = int(client_info.get('down', 0))
            total = int(client_info.get('total', 0))
            
            # Calculate remaining and usage percent
            total_usage = up + down
            remaining = max(0, total - total_usage) if total > 0 else float('inf')
            usage_percent = (total_usage / total * 100) if total > 0 else 0
            
            # Normalize timestamps
            expire_time = self._normalize_timestamp(client_info.get('expire_time', 0))
            last_connection = self._normalize_timestamp(client_info.get('last_connection', 0))
            created_at = self._normalize_timestamp(client_info.get('created_at', 0))
            
            # Log raw timestamp values
            logger.info(f"Raw timestamps - expire_time: {expire_time} (type: {type(expire_time)})")
            logger.info(f"Raw timestamps - last_connection: {last_connection} (type: {type(last_connection)})")
            logger.info(f"Raw timestamps - created_at: {created_at} (type: {type(created_at)})")
            
            # Format dates
            expire_str = format_date(expire_time)
            last_conn_str = format_date(last_connection)
            created_str = format_date(created_at)
            
            # Calculate remaining time
            remaining_time = format_remaining_time(expire_time)
            
            # Build status message with escaped special characters
            status = (
                f"{format_bold('👤 اطلاعات کاربر')}\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📧 *ایمیل:* `{escape_markdown(client_info.get('email', 'نامشخص'))}`\n"
                f"📝 *توضیحات:* `{escape_markdown(client_info.get('remark', 'بدون توضیحات'))}`\n"
                f"📊 *وضعیت:* {escape_markdown('✅ فعال' if client_info.get('enable', True) else '❌ غیرفعال')}\n\n"
                f"{format_bold('⏰ زمان‌ها')}\n"
                f"• *تاریخ ایجاد:* `{escape_markdown(created_str)}`\n"
                f"• *آخرین اتصال:* `{escape_markdown(last_conn_str)}`\n"
                f"• *تاریخ انقضا:* `{escape_markdown(expire_str)}`\n"
                f"• *زمان باقیمانده:* `{escape_markdown(remaining_time)}`\n\n"
                f"{format_bold('📊 آمار ترافیک')}\n"
                f"• *آپلود:* `{escape_markdown(format_size(up))}`\n"
                f"• *دانلود:* `{escape_markdown(format_size(down))}`\n"
                f"• *کل مصرف:* `{escape_markdown(format_size(total_usage))}`\n"
                f"• *باقیمانده:* `{escape_markdown(format_size(remaining) if total > 0 else 'نامحدود')}`\n"
                f"• *درصد مصرف:* `{escape_markdown(f'{usage_percent:.1f}%'.replace('.', '\\.'))}`\n"
                f"• *حجم کل:* `{escape_markdown(format_size(total) if total > 0 else 'نامحدود')}`"
            )
            
            logger.info("Status text generated successfully")
            return status
            
        except Exception as e:
            logger.error(f"Error generating status text: {str(e)}\n{traceback.format_exc()}")
            return "خطا در دریافت اطلاعات"

    def _log_activity(self, user_id: int, activity_type: str, target_uuid: str):
        """Log user activity"""
        try:
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=user_id).first()
                if not user:
                    return
                    
                # Extract just the UUID if target_uuid contains callback data
                if '_' in target_uuid:
                    # Handle callback data like 'stats_uuid' or 'total_stats_uuid'
                    parts = target_uuid.split('_')
                    target_uuid = parts[-1]  # Get the last part which should be the UUID
                
                activity = UserActivity(
                    user_id=user.id,
                    activity_type=activity_type,
                    target_uuid=target_uuid,
                    details={
                        'timestamp': datetime.now(pytz.timezone('Asia/Tehran')).isoformat(),
                        'full_callback_data': target_uuid if not '_' in target_uuid else '_'.join(parts)
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
        self.bot.message_handler(commands=['system_info'])(self.handle_system_info)
        
        # Register direct link handler
        @self.bot.message_handler(func=lambda message: message.text and 'vless://' in message.text.lower())
        def handle_direct_link(message):
            self.process_vpn_link(message, message.text.strip())
        
        # Register state handlers
        self.bot.message_handler(func=lambda message: self._check_user_state(message))(self.handle_state_input)
        
        # Register callback handlers
        self.bot.callback_query_handler(func=lambda call: True)(self.handle_callback)
        
        logger.info("User handlers registered successfully")
        
    def _check_user_state(self, message: Message) -> bool:
        """Check if user is in a specific state that needs handling"""
        try:
            if not message.from_user:
                return False
                
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user or not user.state:
                    return False
                    
                # Check if user is in a state that needs handling
                return user.state.startswith(('ing_custom_traffic:', 'ing_custom_expiry:'))
        except Exception as e:
            logger.error(f"Error checking user state: {str(e)}")
            return False
            
    @handle_errors
    def handle_callback(self, call: CallbackQuery):
        """Handle callback queries"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return

            action, *params = call.data.split('_')
            
            if action == "refresh":
                if params[0] == "system":
                    # Handle system info refresh using the new function
                    self._handle_system_info_refresh(call)
                else:
                    # Handle client refresh
                    client_uuid = params[0]
                    self._handle_refresh(call, client_uuid)
                
            elif action == "stats":
                client_uuid = params[0]
                # Display statistics options
                keyboard = create_stats_keyboard(client_uuid)
                try:
                    self.bot.edit_message_text(
                        "📊 *آمار و گزارشات*\n\nلطفا گزینه مورد نظر را انتخاب کنید:",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=keyboard,
                        parse_mode='MarkdownV2'
                    )
                except apihelper.ApiTelegramException as e:
                    if "message is not modified" not in str(e).lower():
                        raise
                    self.bot.answer_callback_query(call.id, "✅ اطلاعات بروز است")
                
            elif action == "back":
                client_uuid = params[0]
                self._handle_refresh(call, client_uuid)
                
            elif action in ["edit", "extend", "delete", "reset"] and user.is_admin:
                client_uuid = params[0]
                if action == "edit":
                    keyboard = create_traffic_options_keyboard(client_uuid)
                    try:
                        self.bot.edit_message_text(
                            "✏️ *ویرایش تنظیمات*\n\nلطفا حجم جدید را انتخاب کنید:",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=keyboard,
                            parse_mode='MarkdownV2'
                        )
                    except apihelper.ApiTelegramException as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                        self.bot.answer_callback_query(call.id, "✅ اطلاعات بروز است")
                elif action == "extend":
                    keyboard = create_expiry_options_keyboard(client_uuid)
                    try:
                        self.bot.edit_message_text(
                            "⚡️ *تمدید سرویس*\n\nلطفا مدت زمان تمدید را انتخاب کنید:",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=keyboard,
                            parse_mode='MarkdownV2'
                        )
                    except apihelper.ApiTelegramException as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                        self.bot.answer_callback_query(call.id, "✅ اطلاعات بروز است")
                elif action == "delete":
                    # Get client info to get inbound_id
                    client_info = self.panel_api.get_client_info(uuid=client_uuid)
                    if client_info and client_info.get('inbound_id'):
                        # Use the new API endpoint with inbound_id
                        success = self.panel_api.delete_client(
                            client_uuid, 
                            inbound_id=client_info.get('inbound_id')
                        )
                    else:
                        # Fallback to legacy method
                        success = self.panel_api.delete_client(client_uuid)
                        
                    if success:
                        self.bot.answer_callback_query(call.id, "✅ کاربر با موفقیت حذف شد")
                        self.bot.delete_message(call.message.chat.id, call.message.message_id)
                    else:
                        self.bot.answer_callback_query(call.id, "❌ خطا در حذف کاربر")
                elif action == "reset":
                    # Get client info to get inbound_id and email
                    client_info = self.panel_api.get_client_info(uuid=client_uuid)
                    if client_info and client_info.get('inbound_id') and client_info.get('email'):
                        # Use the new API endpoint with inbound_id and email
                        success = self.panel_api.reset_traffic(
                            client_uuid, 
                            inbound_id=client_info.get('inbound_id'),
                            email=client_info.get('email')
                        )
                    else:
                        # Fallback to legacy method
                        success = self.panel_api.reset_traffic(client_uuid)
                        
                    if success:
                        self.bot.answer_callback_query(call.id, "✅ ترافیک با موفقیت ریست شد")
                        self._handle_refresh(call, client_uuid)
                    else:
                        self.bot.answer_callback_query(call.id, "❌ خطا در ریست ترافیک")
            
            elif action == "settraffic" and user.is_admin:
                client_uuid, gb = params
                # Get client info to get inbound_id
                client_info = self.panel_api.get_client_info(uuid=client_uuid)
                
                success = self.panel_api.set_traffic(client_uuid, int(gb))
                if success:
                    self.bot.answer_callback_query(call.id, f"✅ حجم با موفقیت به {gb}GB تنظیم شد")
                    self._handle_refresh(call, client_uuid)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم حجم", show_alert=True)
            
            elif action == "setexpiry" and user.is_admin:
                client_uuid, days = params
                
                success = self.panel_api.set_expiry(client_uuid, int(days))
                if success:
                    days_text = "نامحدود" if int(days) == 0 else f"{days} روز"
                    self.bot.answer_callback_query(call.id, f"✅ تاریخ انقضا با موفقیت به {days_text} تنظیم شد")
                    self._handle_refresh(call, client_uuid)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم تاریخ انقضا", show_alert=True)
            
            elif action == "setunlimited" and user.is_admin:
                client_uuid = params[0]
                
                success = self.panel_api.set_unlimited(client_uuid)
                if success:
                    self.bot.answer_callback_query(call.id, "✅ حجم با موفقیت نامحدود شد")
                    self._handle_refresh(call, client_uuid)
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در تنظیم حجم نامحدود", show_alert=True)
            
            elif (action == "customtraffic" or action == "custom_traffic") and user.is_admin:
                client_uuid = params[0]
                
                # Force user to state for getting custom traffic
                with SessionLocal() as db:
                    db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).update({
                        "state": f"ing_custom_traffic:{client_uuid}"
                    })
                    db.commit()
                
                self.bot.answer_callback_query(call.id)
                self.bot.send_message(
                    call.message.chat.id,
                    "🔢 *حجم دلخواه*\n\nلطفا حجم مورد نظر را به گیگابایت وارد کنید\\. مثال: `50`",
                    parse_mode='MarkdownV2'
                )
            
            elif (action == "customexpiry" or action == "custom_expiry") and user.is_admin:
                client_uuid = params[0]
                
                # Force user to state for getting custom expiry
                with SessionLocal() as db:
                    db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).update({
                        "state": f"ing_custom_expiry:{client_uuid}"
                    })
                    db.commit()
                
                self.bot.answer_callback_query(call.id)
                self.bot.send_message(
                    call.message.chat.id,
                    "📅 *تاریخ دلخواه*\n\nلطفا تعداد روز مورد نظر را وارد کنید\\. مثال: `30`",
                    parse_mode='MarkdownV2'
                )
            
            # Log activity
            self._log_activity(call.from_user.id, f"CALLBACK_{action.upper()}", '_'.join(params))
            
        except apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                self.bot.answer_callback_query(call.id, "✅ اطلاعات بروز است")
            else:
                logger.error(f"Error handling callback: {str(e)}\n{traceback.format_exc()}")
                self.bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست")
        except Exception as e:
            logger.error(f"Error handling callback: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست")

    def _retry_operation(self, operation, *args, max_retries=3, **kwargs):
        """Helper method to retry operations with exponential backoff"""
        last_error = None
        for attempt in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except (requests.exceptions.ConnectionError,
                   requests.exceptions.Timeout,
                   requests.exceptions.RequestException) as e:
                last_error = e
                if attempt == max_retries - 1:  # Last attempt
                    break
                wait_time = (2 ** attempt) * 0.5  # Exponential backoff
                self.logger.warning(f"Network error, retrying in {wait_time}s: {str(e)}")
                time.sleep(wait_time)
            except Exception as e:
                raise  # Re-raise other exceptions immediately
        
        # If we get here, all retries failed
        self.logger.error(f"Operation failed after {max_retries} retries: {str(last_error)}")
        raise last_error

    def _handle_refresh(self, call: CallbackQuery, identifier: str):
        """Handle refresh callback for client status"""
        try:
            logger.info(f"Handling refresh for identifier: {identifier}")
            
            # Get client info with retry
            try:
                client_info = self._retry_operation(
                    self.panel_api.get_client_info,
                    uuid=identifier
                )
            except Exception as e:
                logger.error(f"Failed to get client info after retries: {str(e)}")
                try:
                    self.bot.answer_callback_query(
                        call.id,
                        "❌ خطا در ارتباط با سرور. لطفاً دوباره تلاش کنید",
                        show_alert=True
                    )
                except apihelper.ApiTelegramException as e:
                    if "query is too old" not in str(e).lower():
                        raise
                return

            if not client_info:
                try:
                    self.bot.answer_callback_query(
                        call.id,
                        "❌ اطلاعات کاربر یافت نشد",
                        show_alert=True
                    )
                except apihelper.ApiTelegramException as e:
                    if "query is too old" not in str(e).lower():
                        raise
                return

            # Get traffic values
            down_bytes = client_info.get('down', 0)
            up_bytes = client_info.get('up', 0)
            total_bytes = client_info.get('total', 0)
            total_usage = down_bytes + up_bytes

            # Format traffic values with appropriate units
            up_str = format_size(up_bytes)
            down_str = format_size(down_bytes)
            total_use_str = format_size(total_usage)
            formatted_total = format_size(total_bytes) if total_bytes > 0 else "نامحدود"

            # Get current time in Tehran timezone
            time = datetime.now(pytz.timezone('Asia/Tehran'))
            jtime = time.strftime('%Y/%m/%d %H:%M:%S')

            # Build status string
            Enable = "فعال 🟢" if client_info.get('enable', True) else "غیرفعال 🔴"
            
            is_online = "آنلاین 🟢" if client_info.get('is_online', True) else "آفلاین 🔴"
            email = client_info.get('email', 'نامشخص')

            # Format expiry time using first version's function
            expiry_time = client_info.get('expiryTime', 0)  # Changed from expire_time to expiryTime
            if expiry_time <= int(datetime.now().timestamp() * 1000):
                formatted_remaining_days = "فاقد تاریخ انقضا"
            else:
                formatted_remaining_days = first_version_format_remaining_days(expiry_time)

            # Format the message with escaped special characters
            formatted_text = (
                f"📧 ایمیل : {escape_markdown(email)}\n"
                f"وضعیت : {escape_markdown(Enable)}\n"
                f"آنلاین : {escape_markdown(is_online)}\n"
                f"🔼آپلود : {escape_markdown(up_str)}\n"
                f"🔽دانلود : {escape_markdown(down_str)}\n"
                f"➕مصرف کلی : {escape_markdown(total_use_str)}\n"
                f"🟥حجم خریداری شده : {escape_markdown(formatted_total)}\n"
                f"📅انقضا : {escape_markdown(formatted_remaining_days)}\n"
                f"\n⏳آخرین آپدیت مقادیر : {escape_markdown(jtime)}"
            )

            # Create keyboard with refresh button
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"refresh_{identifier}")
            )

            # Create keyboard with admin buttons if needed
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                keyboard = create_client_status_keyboard(identifier, user.is_admin if user else False)

            try:
                # Try to update existing message
                self.bot.edit_message_text(
                    formatted_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                
                try:
                    self.bot.answer_callback_query(
                        call.id,
                        "✅ اطلاعات بروزرسانی شد",
                        show_alert=False
                    )
                except apihelper.ApiTelegramException as e:
                    if "query is too old" not in str(e).lower():
                        raise
                
            except apihelper.ApiTelegramException as e:
                if "message is not modified" in str(e).lower():
                    # If content hasn't changed, just show notification
                    try:
                        self.bot.answer_callback_query(
                            call.id,
                            "✅ اطلاعات بروز است",
                            show_alert=False
                        )
                    except apihelper.ApiTelegramException as e:
                        if "query is too old" not in str(e).lower():
                            raise
                else:
                    # For other API errors, try to send a new message
                    logger.warning(f"Failed to edit message for refresh, attempting to send new one. Error: {str(e)}")
                    try:
                        self.bot.delete_message(
                            call.message.chat.id,
                            call.message.message_id
                        )
                    except Exception as del_e:
                        logger.error(f"Failed to delete old message during refresh fallback: {str(del_e)}")
                        
                    self.bot.send_message(
                        call.message.chat.id,
                        formatted_text,
                        reply_markup=keyboard
                    )
                    
                    try:
                        self.bot.answer_callback_query(
                            call.id,
                            "✅ پیام جدید ارسال شد",
                            show_alert=True
                        )
                    except apihelper.ApiTelegramException as e:
                        if "query is too old" not in str(e).lower():
                            raise
            
            # Log the refresh action
            self._log_activity(call.from_user.id, "REFRESH_STATUS", identifier)
            
        except Exception as e:
            logger.error(f"Error refreshing status: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ خطا در بروزرسانی اطلاعات",
                    show_alert=True
                )
            except apihelper.ApiTelegramException as e:
                if "query is too old" not in str(e).lower():
                    raise

    @handle_errors
    def handle_start(self, message: Message):
        """Handle /start command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    # Create new user
                    user = TelegramUser(
                        telegram_id=message.from_user.id,
                        username=message.from_user.username,
                        first_name=message.from_user.first_name,
                        last_name=message.from_user.last_name,
                        is_admin=False
                    )
                    db.add(user)
                    db.commit()

            # Send welcome message
            self.bot.reply_to(
                message,
                f"👋 سلام {message.from_user.first_name}!\n\n"
                "به ربات مدیریت VPN خوش آمدید\\.\n\n"
                "برای مشاهده راهنما از دستور /help استفاده کنید\\.",
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "START", None)

        except Exception as e:
            logger.error(f"Error handling start command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_help(self, message: Message):
        """Handle /help command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            # Send help message
            help_text = (
                "📚 *راهنمای استفاده*\n\n"
                "دستورات موجود:\n"
                "• `/start` \\- شروع کار با ربات\n"
                "• `/help` \\- نمایش این راهنما\n"
                "• `/usage` \\- مشاهده وضعیت سرویس\n\n"
                "برای مشاهده وضعیت سرویس، لینک VPN را ارسال کنید یا از دستور `/usage` استفاده کنید\\.\n\n"
                "نمونه:\n"
                "`/usage vless://...`\n\n"
                "یا لینک را مستقیما ارسال کنید:\n"
                "`vless://...`"
            )

            if user.is_admin:
                help_text += "\n\n*دستورات ادمین:*\n• `/admin` \\- پنل مدیریت"

            self.bot.reply_to(
                message,
                help_text,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "HELP", None)

        except Exception as e:
            logger.error(f"Error handling help command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    @handle_errors
    def handle_system_info(self, message: Message):
        """Handle /system_info command"""
        try:
            # Get user info
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return

            if not user.is_admin:
                self.bot.reply_to(message, "❌ دسترسی غیرمجاز")
                return

            # Get system info
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Format system info
            system_info = f"""
{format_bold('💻 اطلاعات سیستم')}
━━━━━━━━━━━━━━━

🖥 {format_bold('سیستم')}:
• CPU: {format_code(f'{cpu_percent}\\%')}
• RAM: {format_code(f'{memory.percent}\\%')} \\({format_code(format_size(memory.used))} از {format_code(format_size(memory.total))}\\)
• دیسک: {format_code(f'{disk.percent}\\%')} \\({format_code(format_size(disk.used))} از {format_code(format_size(disk.total))}\\)

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: {format_code(format_date(time.time()))}
• ساعت: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی اطلاعات سیستم",
                    callback_data="refresh_system"
                )
            )

            # Send message
            self.bot.reply_to(
                message,
                system_info,
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )

            # Log activity
            self._log_activity(message.from_user.id, "SYSTEM_INFO", None)

        except Exception as e:
            logger.error(f"Error handling system info command: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(message, "❌ خطا در پردازش درخواست")

    def _handle_system_info_refresh(self, call: CallbackQuery):
        """Handle refresh callback for system info"""
        try:
            # Get system info
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            response = f"""
{format_bold('💻 اطلاعات سیستم')}
━━━━━━━━━━━━━━━

🖥 {format_bold('سیستم')}:
• CPU: {format_code(f'{cpu_percent}\\%')}
• RAM: {format_code(f'{memory.percent}\\%')} \\({format_code(format_size(memory.used))} از {format_code(format_size(memory.total))}\\)
• دیسک: {format_code(f'{disk.percent}\\%')} \\({format_code(format_size(disk.used))} از {format_code(format_size(disk.total))}\\)

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: {format_code(format_date(time.time()))}
• ساعت: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی اطلاعات سیستم",
                    callback_data="refresh_system"
                )
            )
            
            try:
                self.bot.edit_message_text(
                    response,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard,
                    parse_mode='MarkdownV2'
                )
                self.bot.answer_callback_query(call.id, "✅ اطلاعات سیستم بروزرسانی شد")
            except apihelper.ApiTelegramException as e:
                if "message is not modified" not in str(e).lower():
                    raise
                self.bot.answer_callback_query(call.id, "✅ اطلاعات بروز است")
                
        except Exception as e:
            logger.error(f"Error refreshing system info: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ خطا در بروزرسانی اطلاعات سیستم",
                    show_alert=True
                )
            except apihelper.ApiTelegramException as e:
                if "query is too old" not in str(e).lower():
                    raise