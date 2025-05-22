import types
from typing import Dict, List, Optional
from telebot import TeleBot, apihelper
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
import json
import os
import gzip
import shutil
from pathlib import Path
import traceback
from functools import wraps
from sqlalchemy.orm import Session
import re
import psutil
import platform
import time
import pytz
import requests
import uuid as uuid_lib
from proj import ADMIN_IDS

from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold
from ..utils.decorators import admin_required
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
from ..utils.panel_api import PanelAPI
from ..models.models import BackupStatus, DatabaseBackup, TelegramUser, VPNClient, SystemLog, SystemLogType
from ..models.base import SessionLocal
from ..utils.backup_manager import BackupManager
from ..utils.datetime_encoder import DateTimeEncoder

# Initialize custom logger
logger = CustomLogger("AdminHandler")

def handle_admin_errors(func):
    """Decorator for handling errors in admin handler methods"""
    @wraps(func)
    def wrapper(self, message: Message, *args, **kwargs):
        try:
            return func(self, message, *args, **kwargs)
        except DatabaseError as e:
            logger.error(f"Database Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در پایگاه داده\\. لطفاً با تیم پشتیبانی تماس بگیرید\\.",
                parse_mode='MarkdownV2'
            )
        except ValidationError as e:
            logger.warning(f"Validation Error in {func.__name__}: {str(e)}")
            self.bot.reply_to(
                message,
                f"❌ {escape_markdown(str(e))}",
                parse_mode='MarkdownV2'
            )
        except APIError as e:
            logger.error(f"API Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در ارتباط با پنل\\. لطفاً بعداً تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطای غیرمنتظره\\. لطفاً با تیم پشتیبانی تماس بگیرید\\.",
                parse_mode='MarkdownV2'
            )
            # Log the error event
            if hasattr(self, 'db'):
                try:
                    self.db.log_event(
                        'ERROR',
                        f'admin_handler_error_{func.__name__}',
                        message.from_user.id if message.from_user else None,
                        str(e),
                        details={'traceback': traceback.format_exc()}
                    )
                except Exception as log_error:
                    logger.error(f"Failed to log error event: {str(log_error)}")
    return wrapper

class AdminHandler:
    def __init__(self, bot: TeleBot, db: Database, panel_api: PanelAPI):
        self.bot = bot
        self.db = db
        self.panel_api = panel_api
        # Get admin chat ID from database or environment
        admin_chat_id = self._get_admin_chat_id()
        self.backup_manager = BackupManager(bot, panel_api)
        
        # Enhanced cache for online clients
        self._online_clients_cache = {}
        self._last_cache_update = 0
        self._cache_ttl = 10  # Reduced cache TTL to 10 seconds for more frequent updates
        self._is_updating = False  # Flag to prevent concurrent updates
        
        # Start backup scheduler
        self.backup_manager.start_scheduler()
        
        logger.info("AdminHandler initialized")

    def _get_admin_chat_id(self) -> int:
        """Get admin chat ID from database"""
        try:
            with SessionLocal() as db:
                admin = db.query(TelegramUser).filter_by(is_admin=True).first()
                if not admin:
                    logger.warning("No admin user found in database, using first admin ID from config")
                    return ADMIN_IDS[0] if ADMIN_IDS else None
                return admin.telegram_id
        except Exception as e:
            logger.error(f"Error getting admin chat ID: {str(e)}")
            return ADMIN_IDS[0] if ADMIN_IDS else None

    def _get_cached_online_clients(self):
        """Get online clients from cache or update cache if needed"""
        current_time = time.time()
        
        # Check if cache is valid and not currently being updated
        if (current_time - self._last_cache_update < self._cache_ttl and 
            self._online_clients_cache and 
            not self._is_updating):
            return self._online_clients_cache.copy()  # Return a copy to prevent race conditions
        
        # If cache is being updated, return current cache
        if self._is_updating:
            return self._online_clients_cache.copy()  # Return a copy to prevent race conditions
        
        try:
            self._is_updating = True
            
            # Get online clients in one batch
            online_clients = self.panel_api.get_online_clients()
            if not online_clients:
                self._online_clients_cache = {}
                self._last_cache_update = current_time
                return {}
            
            # Update cache with online clients info
            new_cache = {}
            for email in online_clients:
                try:
                    # Get client info using email
                    client_info = self.panel_api.get_client_info(email=email)
                    if client_info:
                        # Add traffic info if available
                        if isinstance(client_info, dict):
                            client_info['up'] = client_info.get('up', 0)
                            client_info['down'] = client_info.get('down', 0)
                        new_cache[email] = client_info
                except Exception as e:
                    logger.error(f"Error getting client info for {email}: {str(e)}")
                    # Add basic info if detailed info fails
                    new_cache[email] = {
                        'email': email,
                        'up': 0,
                        'down': 0
                    }
                    continue
            
            self._online_clients_cache = new_cache
            self._last_cache_update = current_time
            return new_cache.copy()  # Return a copy to prevent race conditions
            
        except Exception as e:
            logger.error(f"Error updating online clients cache: {str(e)}")
            return self._online_clients_cache.copy()  # Return a copy to prevent race conditions
        finally:
            self._is_updating = False

    @admin_required
    @handle_admin_errors
    def handle_user_list(self, message: Message):
        """Handle the /users command to list online users"""
        logger.info(f"Admin {message.from_user.id} requested online users list")
        
        try:
            # Get online clients from cache
            online_clients_info = self._get_cached_online_clients()
            online_clients = list(online_clients_info.keys())
            
            if not online_clients:
                self.bot.reply_to(
                    message,
                    "📊 *وضعیت کاربران*\n\n❌ در حال حاضر هیچ کاربری آنلاین نیست\\.",
                    parse_mode='MarkdownV2'
                )
                return

            # Format response message
            response = f"""
{format_bold('📊 کاربران آنلاین')}
━━━━━━━━━━━━━━━

"""
            # Create inline keyboard for user buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            buttons = []
            
            # Process online clients from cache
            for email in online_clients:
                client_info = online_clients_info.get(email)
                if client_info:
                    # Create button for each user with email
                    buttons.append(InlineKeyboardButton(
                        f"📧 {email}",
                        callback_data=f"show_usage:{email}"
                    ))
            
            if not buttons:
                logger.warning("No valid clients found to create buttons")
                self.bot.reply_to(
                    message,
                    "📊 *وضعیت کاربران*\n\n❌ در حال حاضر هیچ کاربری آنلاین نیست\\.",
                    parse_mode='MarkdownV2'
                )
                return
            
            # Add buttons in pairs (2 per row)
            for i in range(0, len(buttons), 2):
                if i + 1 < len(buttons):
                    keyboard.row(buttons[i], buttons[i+1])
                else:
                    keyboard.row(buttons[i])
            
            # Add refresh button at the bottom
            keyboard.row(InlineKeyboardButton(
                "🔄 بروزرسانی",
                callback_data="refresh_online_users"
            ))

            # Add summary
            response += f"""
{format_bold('📈 آمار کلی')}:
• تعداد کاربران آنلاین: {format_code(str(len(buttons)))}
• آخرین بروزرسانی: {format_code(datetime.now().strftime('%H:%M:%S'))}
"""

            self.bot.reply_to(
                message, 
                response, 
                parse_mode='MarkdownV2',
                reply_markup=keyboard
            )
            logger.info(f"Online users list sent to admin {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"Error fetching online users: {str(e)}\n{traceback.format_exc()}")
            raise APIError("Failed to fetch online users")

    @admin_required
    @handle_admin_errors
    def handle_logs(self, message: Message):
        """Handle the /logs command to show recent system logs"""
        logger.info(f"Admin {message.from_user.id} requested system logs")
        
        try:
            # Create logs directory if it doesn't exist
            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)

            # Generate filename with current date and time
            tehran_tz = pytz.timezone('Asia/Tehran')
            current_time_tehran = datetime.now(tehran_tz)
            current_time_str = current_time_tehran.strftime("%Y%m%d_%H%M%S")
            filename = f"system_logs_{current_time_str}.txt"
            filepath = export_dir / filename

            # Get logs from database
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        timestamp,
                        level,
                        event_type,
                        message,
                        details
                    FROM logs 
                    ORDER BY timestamp DESC 
                    LIMIT 100
                """)
                
                logs = cursor.fetchall()
                if not logs:
                    self.bot.reply_to(
                        message,
                        "❌ *هیچ لاگی یافت نشد*",
                        parse_mode='MarkdownV2'
                    )
                    return

            # Write logs to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("📋 گزارش لاگ‌های سیستم\n")
                f.write("═══════════════════════════════\n\n")
                
                for log in logs:
                    timestamp, level, event_type, msg, details = log
                    
                    # Format timestamp
                    try:
                        if isinstance(timestamp, str):
                            timestamp = datetime.fromisoformat(timestamp.split('.')[0])
                        formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        formatted_time = str(timestamp)

                    # Write log entry
                    f.write(f"⏰ زمان: {formatted_time}\n")
                    f.write(f"📊 سطح: {level}\n")
                    f.write(f"📝 نوع: {event_type}\n")
                    f.write(f"📄 پیام: {msg}\n")
                    
                    # Format details if they exist
                    if details:
                        try:
                            if isinstance(details, str):
                                details_dict = json.loads(details)
                            else:
                                details_dict = details
                                
                            # Format details, excluding binary data
                            formatted_details = json.dumps(
                                {k: v for k, v in details_dict.items() if not isinstance(v, (bytes, bytearray))},
                                ensure_ascii=False,
                                indent=2
                            )
                            f.write(f"📎 جزئیات:\n{formatted_details}\n")
                        except:
                            f.write(f"📎 جزئیات: {str(details)}\n")
                    
                    f.write("───────────────────────────────\n\n")

            # Send file to admin
            with open(filepath, 'rb') as f:
                self.bot.send_document(
                    message.chat.id,
                    f,
                    caption=f"*📋 گزارش لاگ‌های سیستم*\n"
                           f"📅 تاریخ: `{escape_markdown(current_time_tehran.strftime('%Y-%m-%d'))}`\n"
                           f"⏰ زمان: `{escape_markdown(current_time_tehran.strftime('%H:%M:%S'))}`\n"
                           f"📊 تعداد رکورد: `{len(logs)}`",
                    parse_mode='MarkdownV2'
                )

            # Clean up old export files
            self._cleanup_old_exports(export_dir)
            
            logger.info(f"Log file sent to admin {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"Error handling logs: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError("Failed to generate log file")

    def _cleanup_old_exports(self, export_dir: Path, keep_days: int = 3):
        """Clean up old export files"""
        try:
            tehran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(tehran_tz)
            for file in export_dir.glob("system_logs_*.txt"):
                try:
                    # Extract date from filename
                    date_str = file.stem.split('_')[2]  # Gets YYYYMMDD from system_logs_YYYYMMDD_HHMMSS.txt
                    file_date_naive = datetime.strptime(date_str, "%Y%m%d")
                    file_date = tehran_tz.localize(file_date_naive) # Localize to Tehran
                    
                    # Delete if older than keep_days
                    if (now - file_date).days > keep_days:
                        file.unlink()
                        logger.info(f"Deleted old export file: {file}")
                except Exception as e:
                    logger.warning(f"Error processing export file {file}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error cleaning up exports: {str(e)}")

    @admin_required
    @handle_admin_errors
    def handle_backup(self, message):
        """Handle backup command"""
        try:
            # Get user from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return
                
                if not user.is_admin:
                    self.bot.reply_to(message, "❌ شما دسترسی به این دستور را ندارید")
                    return
            
            # Send initial message
            status_msg = self.bot.reply_to(message, "⏳ در حال ایجاد بکاپ\\.\\.\\.")
            
            # Create backup
            success = self.backup_manager.create_manual_backup(user)
            
            if success:
                # Delete status message
                try:
                    self.bot.delete_message(message.chat.id, status_msg.message_id)
                except:
                    pass
            else:
                # Update status message with error
                self.bot.edit_message_text(
                    "❌ خطا در ایجاد بکاپ",
                    message.chat.id,
                    status_msg.message_id,
                    parse_mode='MarkdownV2'
                )
        except Exception as e:
            logger.error(f"Error in backup command: {str(e)}")
            self.bot.reply_to(
                message, 
                f"❌ خطا در ایجاد بکاپ: {escape_markdown(str(e))}",
                parse_mode='MarkdownV2'
            )
    
    def handle_backup_status(self, message):
        """Handle backup status command"""
        try:
            # Get user from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user:
                    self.bot.reply_to(message, "❌ کاربر یافت نشد")
                    return
                
                if not user.is_admin:
                    self.bot.reply_to(message, "❌ شما دسترسی به این دستور را ندارید")
                    return
                
                # Get latest backup
                latest_backup = (db.query(DatabaseBackup)
                               .order_by(DatabaseBackup.created_at.desc())
                               .first())
                
                if not latest_backup:
                    self.bot.reply_to(message, "❌ هیچ بکاپی یافت نشد")
                    return
                
                # Format backup info
                status_emoji = {
                    BackupStatus.PENDING: "⏳",
                    BackupStatus.COMPLETED: "✅",
                    BackupStatus.FAILED: "❌"
                }.get(latest_backup.status, "❓")
                
                status_text = {
                    BackupStatus.PENDING: "در انتظار",
                    BackupStatus.COMPLETED: "تکمیل شده",
                    BackupStatus.FAILED: "ناموفق"
                }.get(latest_backup.status, "نامشخص")
                
                backup_info = f"""
📊 *وضعیت آخرین بکاپ*
━━━━━━━━━━━━━━━
• وضعیت: {status_emoji} `{status_text}`
• تاریخ: `{latest_backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}`
• نوع: `{'خودکار' if latest_backup.is_automatic else 'دستی'}`
"""
                
                if latest_backup.completed_at:
                    backup_info += f"• زمان تکمیل: `{latest_backup.completed_at.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                
                if latest_backup.size_bytes:
                    backup_info += f"• حجم: `{format_size(latest_backup.size_bytes)}`\n"
                
                if latest_backup.error_message:
                    backup_info += f"• خطا: `{escape_markdown(latest_backup.error_message)}`\n"
                
                # Add keyboard with refresh button
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    InlineKeyboardButton(
                        "🔄 بروزرسانی وضعیت",
                        callback_data="refresh_backup_status"
                    )
                )
                
                self.bot.reply_to(
                    message,
                    backup_info,
                    parse_mode='MarkdownV2',
                    reply_markup=keyboard
                )
            
        except Exception as e:
            logger.error(f"Error in backup status command: {str(e)}")
            self.bot.reply_to(message, f"❌ خطا در دریافت وضعیت بکاپ: {str(e)}")
    
    def _handle_backup_status_refresh(self, call):
        """Handle backup status refresh callback"""
        try:
            # Get user from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return
                
                if not user.is_admin:
                    self.bot.answer_callback_query(call.id, "❌ شما دسترسی به این دستور را ندارید")
                    return

                # Get latest backup
                latest_backup = (db.query(DatabaseBackup)
                               .order_by(DatabaseBackup.created_at.desc())
                               .first())
                
                if not latest_backup:
                    self.bot.edit_message_text(
                        "❌ هیچ بکاپی یافت نشد",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    return
                
                # Format backup info
                status_emoji = {
                    BackupStatus.PENDING: "⏳",
                    BackupStatus.COMPLETED: "✅",
                    BackupStatus.FAILED: "❌"
                }.get(latest_backup.status, "❓")
                
                status_text = {
                    BackupStatus.PENDING: "در انتظار",
                    BackupStatus.COMPLETED: "تکمیل شده",
                    BackupStatus.FAILED: "ناموفق"
                }.get(latest_backup.status, "نامشخص")
                
                backup_info = f"""
📊 *وضعیت آخرین بکاپ*
━━━━━━━━━━━━━━━
• وضعیت: {status_emoji} `{status_text}`
• تاریخ: `{latest_backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}`
• نوع: `{'خودکار' if latest_backup.is_automatic else 'دستی'}`
"""
                
                if latest_backup.completed_at:
                    backup_info += f"• زمان تکمیل: `{latest_backup.completed_at.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                
                if latest_backup.size_bytes:
                    backup_info += f"• حجم: `{format_size(latest_backup.size_bytes)}`\n"
                
                if latest_backup.error_message:
                    backup_info += f"• خطا: `{escape_markdown(latest_backup.error_message)}`\n"
                
                # Add keyboard with refresh button
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    InlineKeyboardButton(
                        "🔄 بروزرسانی وضعیت",
                        callback_data="refresh_backup_status"
                    )
                )
                
                self.bot.edit_message_text(
                    backup_info,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='MarkdownV2',
                    reply_markup=keyboard
                )
                
                self.bot.answer_callback_query(call.id, "✅ وضعیت بروزرسانی شد")
            
        except Exception as e:
            logger.error(f"Error in backup status refresh: {str(e)}")
            self.bot.answer_callback_query(
                call.id,
                f"❌ خطا در بروزرسانی وضعیت: {str(e)}"
            )

    @admin_required
    @handle_admin_errors
    def handle_broadcast(self, message: Message):
        """Handle /broadcast command to send message to all users"""
        try:
            # Check if user is admin
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not user or not user.is_admin:
                    self.bot.reply_to(
                        message,
                        "❌ شما دسترسی به این دستور را ندارید\\.",
                        parse_mode='MarkdownV2'
                    )
                    return

            # Get message text
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                self.bot.reply_to(
                    message,
                    "❌ لطفا پیام خود را وارد کنید\\.\n*نمونه*: `/broadcast پیام شما`",
                    parse_mode='MarkdownV2'
                )
                return

            broadcast_text = parts[1]
            
            # Get all users
            with SessionLocal() as db:
                users = db.query(TelegramUser).all()
                total_users = len(users)
                
            if total_users == 0:
                self.bot.reply_to(
                    message,
                    "❌ هیچ کاربری یافت نشد\\.",
                    parse_mode='MarkdownV2'
                )
                return

            # Send status message
            status_msg = self.bot.reply_to(
                message,
                f"""
{format_bold('📢 ارسال پیام همگانی')}
━━━━━━━━━━━━━━━

📊 {format_bold('وضعیت')}:
• تعداد کل کاربران: {format_code(str(total_users))}
• وضعیت: {format_code('در حال ارسال')}

⏳ {format_bold('پیشرفت')}:
• ارسال شده: {format_code('0')}
• باقیمانده: {format_code(str(total_users))}
• درصد: {format_code('0%')}
""",
                parse_mode='MarkdownV2'
            )

            # Send message to users
            success_count = 0
            fail_count = 0
            for i, user in enumerate(users, 1):
                try:
                    self.bot.send_message(
                        user.telegram_id,
                        broadcast_text,
                        parse_mode='MarkdownV2'
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error sending broadcast to user {user.telegram_id}: {str(e)}")
                    fail_count += 1

                # Update status every 10 users or at the end
                if i % 10 == 0 or i == total_users:
                    try:
                        self.bot.edit_message_text(
                            f"""
{format_bold('📢 ارسال پیام همگانی')}
━━━━━━━━━━━━━━━

📊 {format_bold('وضعیت')}:
• تعداد کل کاربران: {format_code(str(total_users))}
• وضعیت: {format_code('در حال ارسال')}

⏳ {format_bold('پیشرفت')}:
• ارسال شده: {format_code(str(i))}
• باقیمانده: {format_code(str(total_users - i))}
• درصد: {format_code(f'{int(i/total_users*100)}%')}
""",
                            status_msg.chat.id,
                            status_msg.message_id,
                            parse_mode='MarkdownV2'
                        )
                    except Exception as e:
                        logger.error(f"Error updating status message: {str(e)}")

            # Send final status
            try:
                self.bot.edit_message_text(
                    f"""
{format_bold('📢 ارسال پیام همگانی')}
━━━━━━━━━━━━━━━

📊 {format_bold('نتیجه')}:
• تعداد کل کاربران: {format_code(str(total_users))}
• ارسال موفق: {format_code(str(success_count))}
• ارسال ناموفق: {format_code(str(fail_count))}
• وضعیت: {format_code('تکمیل شده')}

⏰ {format_bold('زمان')}:
• تاریخ: {format_code(escape_markdown(format_date(time.time())))}
• ساعت: {format_code(escape_markdown(datetime.now().strftime('%H:%M:%S')))}
""",
                    status_msg.chat.id,
                    status_msg.message_id,
                    parse_mode='MarkdownV2'
                )
            except Exception as e:
                logger.error(f"Error sending final status message: {str(e)}")
                self.bot.reply_to(
                    message,
                    f"""
{format_bold('📢 ارسال پیام همگانی')}
━━━━━━━━━━━━━━━

📊 {format_bold('نتیجه')}:
• تعداد کل کاربران: {format_code(str(total_users))}
• ارسال موفق: {format_code(str(success_count))}
• ارسال ناموفق: {format_code(str(fail_count))}
• وضعیت: {format_code('تکمیل شده')}

⏰ {format_bold('زمان')}:
• تاریخ: {format_code(escape_markdown(format_date(time.time())))}
• ساعت: {format_code(escape_markdown(datetime.now().strftime('%H:%M:%S')))}
""",
                    parse_mode='MarkdownV2'
                )

        except Exception as e:
            logger.error(f"Unexpected error in handle_broadcast: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در ارسال پیام همگانی\\. لطفا دوباره تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )

    @admin_required
    @handle_admin_errors
    def handle_system(self, message: Message):
        """Handle the /system command to show system information""" 
        try:
            # Get CPU info
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            # Get memory info
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Get disk info
            disk = psutil.disk_usage('/')

            # Get network info
            net_io = psutil.net_io_counters()

            # Get system uptime
            uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            
            # Format response
            tehran_tz = pytz.timezone('Asia/Tehran')
            server_time_tehran = datetime.now(tehran_tz).strftime('%Y-%m-%d %H:%M:%S')
            response = f"""
{format_bold('🖥 اطلاعات سیستم')}
━━━━━━━━━━━━━━━

{format_bold('💻 سیستم عامل')}:
• نام: `{escape_markdown(platform.system())}`
• نسخه: `{escape_markdown(platform.release())}`
• معماری: `{escape_markdown(platform.machine())}`

{format_bold('🔄 پردازنده')}:
• تعداد هسته: `{cpu_count}`
• درصد استفاده: `{cpu_percent}%`
• فرکانس: `{int(cpu_freq.current)} MHz`

{format_bold('💾 حافظه')}:
• کل: `{format_size(memory.total)}`
• استفاده شده: `{format_size(memory.used)}`
• آزاد: `{format_size(memory.free)}`
• درصد استفاده: `{memory.percent}%`

{format_bold('💿 دیسک')}:
• کل: `{format_size(disk.total)}`
• استفاده شده: `{format_size(disk.used)}`
• آزاد: `{format_size(disk.free)}`
• درصد استفاده: `{disk.percent}%`

{format_bold('🌐 شبکه')}:
• دریافت شده: `{format_size(net_io.bytes_recv)}`
• ارسال شده: `{format_size(net_io.bytes_sent)}`

{format_bold('⏰ زمان')}:
• آپتایم: `{str(uptime).split('.')[0]}`
• زمان سرور: `{escape_markdown(server_time_tehran)}`
"""

            # Create refresh buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(
                    "🔄 بروزرسانی اطلاعات سیستم",
                    callback_data="refresh_system"
                ),
                InlineKeyboardButton(
                    "📊 بروزرسانی آمار",
                    callback_data="refresh_stats"
                )
            )

            self.bot.reply_to(
                message,
                response,
                parse_mode='MarkdownV2',
                reply_markup=keyboard
            )

            # Log the action
            self.db.log_event(
                'INFO',
                'system_info_check',
                message.from_user.id,
                'System information checked',
                details={
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'disk_percent': disk.percent
                }
            )

        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}\n{traceback.format_exc()}")
            raise APIError("Failed to get system information")

    @admin_required
    @handle_admin_errors
    def handle_users(self, message: Message):
        """Handle /users_info command to list all bot users"""
        try:
            # Get all users from database
            with SessionLocal() as db:
                all_users = db.query(TelegramUser).all()
                
            if not all_users:
                self.bot.reply_to(message, "❌ No users found in database.")
                return
                
            # Start with a simple count message
            response = f"👥 Total registered users: {len(all_users)}\n\n"
            
            # Create inline keyboard for pagination
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("📄 Export List", callback_data="export_users"),
                InlineKeyboardButton("👥 View Details", callback_data="view_users_1")
            )
            
            # Send initial response
            self.bot.reply_to(
                message,
                response,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Error handling users_info command: {str(e)}")
            self.bot.reply_to(message, "❌ Error retrieving user information.")

    def handle_callback(self, call):
        """Handle callback queries"""
        try:
            # Get user from database
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if not user:
                    self.bot.answer_callback_query(call.id, "❌ کاربر یافت نشد")
                    return
                
                if not user.is_admin:
                    self.bot.answer_callback_query(call.id, "❌ شما دسترسی به این دستور را ندارید")
                    return
            
            # Parse callback data
            callback_data = call.data.split(':')
            action = callback_data[0]
            
            # Handle different actions
            if action == "refresh":
                if len(callback_data) < 2:
                    return
                    
                refresh_type = callback_data[1]
                if refresh_type == "system":
                    self._refresh_system_info(call)
                elif refresh_type == "stats":
                    self._refresh_stats(call)
                elif refresh_type == "backup_status":
                    self._handle_backup_status_refresh(call)
                else:
                    # Handle client refresh
                    client_uuid = refresh_type
                    self._refresh_client_info(call, client_uuid)
            elif action == "stats":
                self._show_stats_options(call)
            elif action == "back":
                self._handle_back(call)
            
        except Exception as e:
            logger.error(f"Error handling callback: {str(e)}")
            try:
                self.bot.answer_callback_query(call.id, f"❌ خطا: {str(e)}")
            except:
                pass
    
    def _show_users_page(self, call: CallbackQuery, page: int):
        """Show a specific page of users"""
        try:
            # Calculate offset
            limit = 10
            offset = (page - 1) * limit
            
            # Get total users and page data
            total_users = self.db.count_users()
            users = self.db.get_all_users(limit=limit, offset=offset)
            
            if not users:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ نمیتوان صفحه را بارگذاری کرد. لطفاً مجدد تلاش کنید.",
                    show_alert=True
                )
                return
            
            # Format response message
            response = f"""
{format_bold('📊 لیست کاربران ربات')}
━━━━━━━━━━━━━━━

{format_bold(f'🔢 تعداد کل کاربران:')} {format_code(str(total_users))}
{format_bold('📄 صفحه:')} {format_code(str(page))}
"""
            
            # Add each user's info
            for user in users:
                # Extract user data
                username = user.get('username', '')
                first_name = user.get('first_name', '')
                last_name = user.get('last_name', '')
                telegram_id = user.get('telegram_id', '')
                email = user.get('email', '')
                status = user.get('status', '')
                
                # Format user display name
                display_name = first_name
                if last_name:
                    display_name += f" {last_name}"
                if username:
                    display_name += f" (@{username})"
                if not display_name:
                    display_name = "بدون نام"
                
                response += f"""
👤 {format_bold('کاربر')}: {escape_markdown(display_name)}
🆔 {format_bold('آیدی')}: {format_code(str(telegram_id)) if telegram_id else format_code('ندارد')}
📧 {format_bold('ایمیل')}: {format_code(email) if email else format_code('ندارد')}
⚙️ {format_bold('وضعیت')}: {format_code(status) if status else format_code('ندارد')}
━━━━━━━━━━
"""
            
            # Create pagination keyboard
            markup = InlineKeyboardMarkup()
            buttons = []
            
            # Add previous page button if not on first page
            if page > 1:
                buttons.append(InlineKeyboardButton("⏪ صفحه قبل", callback_data=f"users_page_{page-1}"))
            
            # Add next page button if more pages exist
            total_pages = (total_users + limit - 1) // limit
            if page < total_pages:
                buttons.append(InlineKeyboardButton("صفحه بعد ⏩", callback_data=f"users_page_{page+1}"))
            
            # Add page indicator
            markup.row(*buttons)
            markup.row(InlineKeyboardButton(f"📄 صفحه {page} از {total_pages}", callback_data="noop"))
            markup.row(InlineKeyboardButton("📋 خروجی", callback_data="export_users"))
            
            # Edit message with new page data
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=response,
                parse_mode='MarkdownV2',
                reply_markup=markup
            )
            
            # Answer callback query
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Error showing users page {page}: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در نمایش صفحه. لطفاً مجدد تلاش کنید.",
                show_alert=True
            )
            
    def _export_users_list(self, call: CallbackQuery):
        """Export full users list as a text file"""
        try:
            # Create exports directory if it doesn't exist
            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)
            
            # Generate filename with current date and time
            tehran_tz = pytz.timezone('Asia/Tehran')
            current_time_tehran = datetime.now(tehran_tz)
            current_time_str = current_time_tehran.strftime("%Y%m%d_%H%M%S")
            filename = f"users_list_{current_time_str}.txt"
            filepath = export_dir / filename
            
            # Get all users from database
            total_users = self.db.count_users()
            all_users = self.db.get_all_users(limit=total_users)
            
            if not all_users:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ هیچ کاربری در سیستم ثبت نشده است.",
                    show_alert=True
                )
                return
            
            # Write users to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("📋 لیست کامل کاربران ربات\n")
                f.write("═══════════════════════════════\n\n")
                f.write(f"📊 تعداد کل کاربران: {total_users}\n")
                f.write(f"🕒 تاریخ استخراج: {current_time_tehran.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for i, user in enumerate(all_users, 1):
                    # Extract user data
                    username = user.get('username', '')
                    first_name = user.get('first_name', '')
                    last_name = user.get('last_name', '')
                    telegram_id = user.get('telegram_id', '')
                    email = user.get('email', '')
                    status = user.get('status', '')
                    created_at = user.get('created_at', '')
                    traffic_limit = user.get('traffic_limit', 0)
                    total_usage = user.get('total_usage', 0)
                    expiry_date = user.get('expiry_date', '')
                    
                    # Format user display name
                    display_name = first_name
                    if last_name:
                        display_name += f" {last_name}"
                    if username:
                        display_name += f" (@{username})"
                    if not display_name:
                        display_name = "بدون نام"
                    
                    # Format traffic values
                    traffic_limit_gb = traffic_limit if traffic_limit else 0
                    total_usage_gb = round(total_usage / (1024**3), 2) if total_usage else 0
                    
                    # Write user details
                    f.write(f"👤 کاربر #{i}:\n")
                    f.write(f"📝 نام: {display_name}\n")
                    f.write(f"🆔 آیدی تلگرام: {telegram_id if telegram_id else 'ندارد'}\n")
                    f.write(f"📧 ایمیل: {email if email else 'ندارد'}\n")
                    f.write(f"⚙️ وضعیت: {status if status else 'نامشخص'}\n")
                    
                    if created_at:
                        # Try to format the datetime
                        try:
                            if isinstance(created_at, str):
                                # Parse ISO format
                                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                formatted_date = created_at.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            formatted_date = str(created_at)
                        f.write(f"🕒 تاریخ ثبت: {formatted_date}\n")
                    
                    if traffic_limit is not None:
                        f.write(f"🔢 حجم: {traffic_limit_gb} GB\n")
                    
                    if total_usage is not None:
                        f.write(f"📊 مصرف: {total_usage_gb} GB\n")
                    
                    if expiry_date:
                        f.write(f"📅 تاریخ انقضا: {expiry_date}\n")
                    
                    f.write("───────────────────────────────\n\n")
            
            # Cleanup old exports
            self._cleanup_old_exports(export_dir)
            
            # Send file to admin
            with open(filepath, 'rb') as f:
                self.bot.send_document(
                    call.message.chat.id,
                    f,
                    caption=f"📋 لیست کامل {total_users} کاربر"
                )
            
            # Answer callback query
            self.bot.answer_callback_query(call.id, "✅ لیست کاربران با موفقیت استخراج شد.")
            logger.info(f"User list exported to {filepath}")
            
        except Exception as e:
            logger.error(f"Error exporting users list: {str(e)}\n{traceback.format_exc()}")
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در استخراج لیست کاربران.",
                show_alert=True
            )
            
    def register_handlers(self):
        """Register all admin command handlers"""
        try:
            logger.info("Registering admin command handlers")
            
            # Register command handlers
            self.bot.message_handler(commands=['users'])(self.handle_user_list)
            self.bot.message_handler(commands=['users_info'])(self.handle_users_info)
            self.bot.message_handler(commands=['logs'])(self.handle_logs)
            self.bot.message_handler(commands=['backup'])(self.handle_backup)
            self.bot.message_handler(commands=['broadcast'])(self.handle_broadcast)
            self.bot.message_handler(commands=['add'])(self.handle_add_client)
            self.bot.message_handler(commands=['toggle'])(self.handle_toggle_bot)
            self.bot.message_handler(commands=['system'])(self.handle_system)
            
            # Register callback handlers
            self.bot.callback_query_handler(func=lambda call: call.data.startswith("users_page_") or 
                                                             call.data == "export_users" or
                                                             call.data.startswith("backup_") or
                                                             call.data == "refresh_system" or
                                                             call.data == "refresh_stats" or
                                                             call.data == "noop")(self.handle_callback)
            
            logger.info("Admin command handlers registered successfully")
            
            # Log registration without user context since this is during initialization
            try:
                self.db.log_event(
                    'INFO',
                    'admin_handlers_registered',
                    None,  # No user ID during initialization
                    'Admin command handlers registered successfully',
                    details={'handlers': ['users', 'users_info', 'logs', 'backup', 'broadcast', 'system', 'add', 'toggle']}
                )
            except Exception as e:
                logger.warning(f"Could not log handler registration event: {str(e)}")
                
        except Exception as e:
            logger.error(f"Failed to register admin handlers: {str(e)}\n{traceback.format_exc()}")
            raise

    def handle_link(self, message: Message, user: TelegramUser):
        """Handle link management for admin"""
        if not message.text or '@' not in message.text:
            self.bot.reply_to(message, "❌ Invalid link format. Please send a valid email.")
            return
            
        email = message.text.strip()
        
        # Get client info
        client = self._get_client_by_email(email)
        if not client:
            self.bot.reply_to(message, "❌ Client not found.")
            return
            
        # Create inline keyboard
        keyboard = InlineKeyboardMarkup(row_width=3)
        
        # Traffic volume buttons
        volume_buttons = []
        for gb in [10, 20, 30, 50, 100]:
            volume_buttons.append(
                InlineKeyboardButton(
                    f"{gb}GB",
                    callback_data=f"set_volume:{email}:{gb}"
                )
            )
        keyboard.add(*volume_buttons)
        
        # Reset and unlimited buttons
        keyboard.row(
            InlineKeyboardButton("♻️ Reset Volume", callback_data=f"reset_volume:{email}"),
            InlineKeyboardButton("♾️ Unlimited", callback_data=f"set_unlimited:{email}")
        )
        
        # Custom volume button
        keyboard.row(
            InlineKeyboardButton("🔢 Custom Volume", callback_data=f"custom_volume:{email}")
        )
        
        # Expiry date buttons
        expiry_buttons = []
        for days in [1, 2, 3, 5, 10, 30, 60, 90, 120, 180]:
            expiry_buttons.append(
                InlineKeyboardButton(
                    f"{days}d",
                    callback_data=f"set_expiry:{email}:{days}"
                )
            )
        
        # Add expiry buttons in rows of 5
        for i in range(0, len(expiry_buttons), 5):
            keyboard.row(*expiry_buttons[i:i+5])
            
        # Unlimited expiry
        keyboard.row(
            InlineKeyboardButton("♾️ Never Expires", callback_data=f"set_expiry:{email}:0")
        )
        
        # IP and traffic management
        keyboard.row(
            InlineKeyboardButton("👀 View IPs", callback_data=f"view_ips:{email}"),
            InlineKeyboardButton("♻️ Reset Traffic", callback_data=f"reset_traffic:{email}")
        )
        
        # Send client info with management buttons
        total_gb = "Unlimited" if client.total_gb == 0 else f"{client.total_gb}GB"
        expiry = "Never" if client.expire_time == 0 else datetime.fromtimestamp(client.expire_time/1000).strftime("%Y-%m-%d")
        used_gb = round((client.upload + client.download) / (1024**3), 2)
        
        info_text = (
            f"📊 Client Information\n\n"
            f"📧 Email: {client.email}\n"
            f"📦 Volume: {total_gb}\n"
            f"📈 Used: {used_gb}GB\n"
            f"📅 Expires: {expiry}\n"
            f"🔌 Port: {client.port}\n"
            f"🔄 Last Update: {client.last_sync.strftime('%Y-%m-%d %H:%M')}"
        )
        
        self.bot.reply_to(message, info_text, reply_markup=keyboard)
    
    def handle_backup_callback(self, call: CallbackQuery):
        """Handle backup-related callbacks"""
        if call.data == "toggle_backup":
            if self.backup_manager.is_backup_enabled:
                self.backup_manager.stop_scheduler()
                self.bot.answer_callback_query(call.id, "❌ Auto-backup disabled")
            else:
                self.backup_manager.start_scheduler()
                self.bot.answer_callback_query(call.id, "✅ Auto-backup enabled")
                
        elif call.data == "create_backup":
            self.bot.answer_callback_query(call.id, "🔄 Creating backup...")
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(telegram_id=call.from_user.id).first()
                if user:
                    success = self.backup_manager.create_manual_backup(user)
                    if not success:
                        self.bot.send_message(call.message.chat.id, "❌ Failed to create backup")

    def _refresh_system_info(self, call: CallbackQuery):
        """Refresh system information"""
        try:
            # Get CPU info
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            # Get memory info
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Get disk info
            disk = psutil.disk_usage('/')

            # Get network info
            net_io = psutil.net_io_counters()

            # Get system uptime
            uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
            
            # Format response
            tehran_tz = pytz.timezone('Asia/Tehran')
            server_time_tehran = datetime.now(tehran_tz).strftime('%Y-%m-%d %H:%M:%S')
            response = f"""
{format_bold('🖥 اطلاعات سیستم')}
━━━━━━━━━━━━━━━

{format_bold('💻 سیستم عامل')}:
• نام: `{escape_markdown(platform.system())}`
• نسخه: `{escape_markdown(platform.release())}`
• معماری: `{escape_markdown(platform.machine())}`

{format_bold('🔄 پردازنده')}:
• تعداد هسته: `{cpu_count}`
• درصد استفاده: `{cpu_percent}%`
• فرکانس: `{int(cpu_freq.current)} MHz`

{format_bold('💾 حافظه')}:
• کل: `{format_size(memory.total)}`
• استفاده شده: `{format_size(memory.used)}`
• آزاد: `{format_size(memory.free)}`
• درصد استفاده: `{memory.percent}%`

{format_bold('💿 دیسک')}:
• کل: `{format_size(disk.total)}`
• استفاده شده: `{format_size(disk.used)}`
• آزاد: `{format_size(disk.free)}`
• درصد استفاده: `{disk.percent}%`

{format_bold('🌐 شبکه')}:
• دریافت شده: `{format_size(net_io.bytes_recv)}`
• ارسال شده: `{format_size(net_io.bytes_sent)}`

{format_bold('⏰ زمان')}:
• آپتایم: `{str(uptime).split('.')[0]}`
• زمان سرور: `{escape_markdown(server_time_tehran)}`
"""

            # Create refresh buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(
                    "🔄 بروزرسانی اطلاعات سیستم",
                    callback_data="refresh_system"
                ),
                InlineKeyboardButton(
                    "📊 بروزرسانی آمار",
                    callback_data="refresh_stats"
                )
            )

            try:
                self.bot.edit_message_text(
                    response,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='MarkdownV2',
                    reply_markup=keyboard
                )
                self.bot.answer_callback_query(
                    call.id,
                    "✅ اطلاعات بروزرسانی شد",
                    show_alert=False
                )
            except apihelper.ApiTelegramException as e:
                if "message is not modified" in str(e).lower():
                    self.bot.answer_callback_query(
                        call.id,
                        "✅ اطلاعات بروز است",
                        show_alert=False
                    )
                else:
                    raise

        except Exception as e:
            logger.error(f"Error refreshing system info: {str(e)}")
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در بروزرسانی اطلاعات",
                show_alert=True
            ) 

    def _refresh_stats(self, call: CallbackQuery):
        """Refresh system statistics"""
        try:
            # Get CPU info
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            net_io = psutil.net_io_counters()

            # Format response
            response = f"""
{format_bold('📊 آمار سیستم')}
━━━━━━━━━━━━━━━

{format_bold('🔄 پردازنده')}:
• استفاده: `{cpu_percent}%`

{format_bold('💾 حافظه')}:
• استفاده: `{memory.percent}%`
• استفاده شده: `{format_size(memory.used)}`
• آزاد: `{format_size(memory.free)}`

{format_bold('💿 دیسک')}:
• استفاده: `{disk.percent}%`
• استفاده شده: `{format_size(disk.used)}`
• آزاد: `{format_size(disk.free)}`

{format_bold('🌐 شبکه')}:
• دریافت شده: `{format_size(net_io.bytes_recv)}`
• ارسال شده: `{format_size(net_io.bytes_sent)}`

{format_bold('⏰ زمان بروزرسانی')}:
• تاریخ: `{format_date(time.time())}`
• ساعت: `{datetime.now().strftime('%H:%M:%S')}`
"""

            # Create refresh buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(
                    "🔄 بروزرسانی اطلاعات سیستم",
                    callback_data="refresh_system"
                ),
                InlineKeyboardButton(
                    "📊 بروزرسانی آمار",
                    callback_data="refresh_stats"
                )
            )

            try:
                self.bot.edit_message_text(
                    response,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='MarkdownV2',
                    reply_markup=keyboard
                )
                self.bot.answer_callback_query(
                    call.id,
                    "✅ آمار بروزرسانی شد",
                    show_alert=False
                )
            except apihelper.ApiTelegramException as e:
                if "message is not modified" in str(e).lower():
                    self.bot.answer_callback_query(
                        call.id,
                        "✅ آمار بروز است",
                        show_alert=False
                    )
                else:
                    raise

        except Exception as e:
            logger.error(f"Error refreshing stats: {str(e)}")
            self.bot.answer_callback_query(
                call.id,
                "❌ خطا در بروزرسانی آمار",
                show_alert=True
            )

    def create_stats_keyboard(self, client_uuid: str) -> InlineKeyboardMarkup:
        """Create keyboard for statistics options"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📊 آمار کلی", callback_data=f"stats_overview:{client_uuid}"),
            InlineKeyboardButton("📈 آمار روزانه", callback_data=f"stats_daily:{client_uuid}"),
            InlineKeyboardButton("📉 آمار هفتگی", callback_data=f"stats_weekly:{client_uuid}"),
            InlineKeyboardButton("📊 آمار ماهانه", callback_data=f"stats_monthly:{client_uuid}"),
            InlineKeyboardButton("🔙 بازگشت", callback_data=f"refresh:{client_uuid}")
        )
        return keyboard

    @admin_required
    @handle_admin_errors
    def handle_users_info(self, message: Message):
        """Handle the /users_info command to list all registered bot users"""
        logger.info(f"Admin {message.from_user.id} requested users info list")
        
        try:
            # Get users count from users table
            with SessionLocal() as db:
                all_users = db.query(TelegramUser).all()
                
            if not all_users:
                self.bot.reply_to(
                    message,
                    "📊 *لیست کاربران*\n\n❌ هیچ کاربری در سیستم ثبت نشده است\\.",
                    parse_mode='MarkdownV2'
                )
                return
            
            # Get first page of users (limit 10)
            with SessionLocal() as db:
                users = db.query(TelegramUser).limit(10).offset(0).all()
            
            # Format response message
            response = f"""
{format_bold('📊 لیست کاربران ربات')}
━━━━━━━━━━━━━━━

{format_bold(f'🔢 تعداد کل کاربران:')} {format_code(str(len(all_users)))}
{format_bold('📄 صفحه:')} {format_code('1')}
"""
            
            # Add each user's info
            for user in users:
                # Extract user data
                username = user.username or ''
                first_name = user.first_name or ''
                last_name = user.last_name or ''
                telegram_id = user.telegram_id
                email = user.email or ''
                status = 'فعال' if user.is_admin else 'کاربر عادی'
                
                # Format user display name
                display_name = first_name
                if last_name:
                    display_name += f" {last_name}"
                if username:
                    display_name += f" (@{username})"
                if not display_name:
                    display_name = "بدون نام"
                
                response += f"""
👤 {format_bold('کاربر')}: {escape_markdown(display_name)}
🆔 {format_bold('آیدی')}: {format_code(str(telegram_id)) if telegram_id else format_code('ندارد')}
📧 {format_bold('ایمیل')}: {format_code(email) if email else format_code('ندارد')}
⚙️ {format_bold('وضعیت')}: {format_code(status) if status else format_code('ندارد')}
━━━━━━━━━━
"""
            
            # Create pagination keyboard if needed
            markup = None
            if len(all_users) > 10:
                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("صفحه بعد ⏩", callback_data="users_page_2"),
                    InlineKeyboardButton("📋 خروجی", callback_data="export_users")
                )
            
            self.bot.reply_to(message, response, parse_mode='MarkdownV2', reply_markup=markup)
            logger.info(f"Users info list sent to admin {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"Error fetching users info: {str(e)}\n{traceback.format_exc()}")
            raise APIError("Failed to fetch users info")

    def _handle_user_action(self, call: CallbackQuery):
        """Handle user action callbacks"""
        try:
            # Parse callback data
            parts = call.data.split('_')
            if len(parts) < 3:
                self.bot.answer_callback_query(call.id, "❌ Invalid callback data")
                return
                
            action = parts[2]  # user_action_ACTION
            if action == "reset" and len(parts) >= 4:
                user_id = parts[3]
                self._handle_reset_traffic_by_id(call, user_id)
            else:
                self.bot.answer_callback_query(call.id, "❌ Unknown action")
        except Exception as e:
            logger.error(f"Error handling user action: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ Error processing action")
    
    def _handle_reset_traffic(self, call: CallbackQuery):
        """Handle reset traffic callback"""
        try:
            # Extract email from callback data: reset_traffic:email
            email = call.data.split(':')[1]
            
            # Get client info to get inbound_id
            client_info = None
            with SessionLocal() as db:
                user = db.query(TelegramUser).filter_by(email=email).first()
                if user and user.telegram_id:
                    user_id = user.telegram_id
                    # Try to get client info from panel API
                    try:
                        client_info = self.panel_api.get_client_info(email=email)
                    except Exception as e:
                        logger.error(f"Error getting client info: {str(e)}")
            
            if client_info and client_info.get('inbound_id') and email:
                # Use the new API endpoint with inbound_id and email
                success = self.panel_api.reset_traffic(
                    client_info.get('uuid', ''), 
                    inbound_id=client_info.get('inbound_id'),
                    email=email
                )
                
                if success:
                    self.bot.answer_callback_query(call.id, f"✅ ترافیک کاربر {email} با موفقیت ریست شد")
                else:
                    self.bot.answer_callback_query(call.id, "❌ خطا در ریست ترافیک", show_alert=True)
            else:
                self.bot.answer_callback_query(call.id, "❌ اطلاعات کاربر یافت نشد", show_alert=True)
        except Exception as e:
            logger.error(f"Error resetting traffic: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ خطا در ریست ترافیک", show_alert=True)
    
    def _handle_reset_traffic_by_id(self, call: CallbackQuery, user_id: str):
        """Handle reset traffic action by user ID"""
        try:
            # Get client info first to get the UUID
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, uuid, email, inbound_id 
                    FROM clients 
                    WHERE id = %s
                """, (user_id,))
                
                client = cursor.fetchone()
                if not client:
                    self.bot.answer_callback_query(call.id, "❌ Client not found")
                    return
                
                client_id, uuid, email, inbound_id = client
                
                # Reset traffic using the API
                success = self.panel_api.reset_traffic(uuid, inbound_id, email)
                
                if success:
                    # Update database record
                    cursor.execute("""
                        UPDATE clients SET upload = 0, download = 0, last_update = NOW() 
                        WHERE id = %s
                    """, (client_id,))
                    conn.commit()
                    
                    # Log the action
                    self.db.log_event(
                        'INFO',
                        'client_traffic_reset',
                        call.from_user.id,
                        f"Traffic reset for client {email} (ID: {client_id})"
                    )
                    
                    self.bot.answer_callback_query(call.id, f"✅ Traffic reset for {email}")
                else:
                    self.bot.answer_callback_query(call.id, "❌ Failed to reset traffic")
        except Exception as e:
            logger.error(f"Error handling reset traffic by ID: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ Error processing request")

    @admin_required
    @handle_admin_errors
    def handle_add_client(self, message: Message):
        """Handle /add command to add a new client"""
        try:
            # Initialize variables
            vless_link = None
            sub_url = None
            processing_msg = None
            
            # Parse command arguments
            args = message.text.split()
            
            # Check if we have the required number of arguments
            if len(args) < 5:
                self.bot.reply_to(
                    message,
                    "❌ *فرمت نادرست*\n\n"
                    "نحوه استفاده:\n"
                    "`/add شناسه_کاربر حجم_به_گیگابایت مدت_به_روز شناسه_اینباند`\n\n"
                    "مثال:\n"
                    "`/add user 50 30 1`",
                    parse_mode='MarkdownV2'
                )
                return
            
            # Extract parameters
            email = args[1]
            gb_limit = args[2]
            days = args[3]
            inbound_id = args[4]
            
            # Validate and convert parameters
            try:
                gb_limit = int(gb_limit)
                days = int(days)
                inbound_id = int(inbound_id)
                
                # Basic validation
                if gb_limit < 0:
                    raise ValueError("حجم باید عدد مثبت باشد")
                if days < 0:
                    raise ValueError("مدت زمان باید عدد مثبت باشد")
                if inbound_id <= 0:
                    raise ValueError("شناسه اینباند باید عدد مثبت باشد")
                
                # Email validation - just ensure it's not empty
                if not email.strip():
                    raise ValueError("شناسه کاربر نمی‌تواند خالی باشد")
                
            except ValueError as e:
                self.bot.reply_to(
                    message,
                    f"❌ *خطای اعتبارسنجی*\n\n{escape_markdown(str(e))}",
                    parse_mode='MarkdownV2'
                )
                return
            
            # Additional parameters (optional)
            limit_ip = 0
            telegram_id = ""
            enable = True
            
            # Try to extract optional parameters
            if len(args) > 5 and args[5].isdigit():
                limit_ip = int(args[5])
            
            if len(args) > 6:
                telegram_id = args[6]
            
            # Send a processing message
            try:
                processing_msg = self.bot.send_message(
                    message.chat.id,
                    "⏳ در حال پردازش درخواست",  # Removed dots to avoid escape issues
                    parse_mode=None
                )
            except Exception as e:
                logger.error(f"Error sending processing message: {str(e)}")
                processing_msg = None
            
            # Create the client
            result = self.panel_api.add_client(
                inbound_id=inbound_id,
                email=email,
                traffic_gb=gb_limit,
                expiry_days=days,
                limit_ip=limit_ip,
                telegram_id=telegram_id,
                enable=enable
            )
            
            # Check if the result is a UUID (success) or False (failure)
            if result and isinstance(result, str):
                # Use the returned UUID
                client_uuid = result
                
                # Wait a moment for the server to process the client addition
                time.sleep(1)
                
                try:
                    # Try to get client info using UUID, email, and inbound_id
                    client_info = self.panel_api.get_client_info(
                        uuid=client_uuid, 
                        email=email,
                        inbound_id=inbound_id
                    )
                    
                    if not client_info or not client_info.get('id'):
                        # If client info not found, create a minimal info dictionary
                        client_info = {
                            'id': client_uuid,
                            'uuid': client_uuid,
                            'email': email,
                            'inbound_id': inbound_id
                        }
                    
                    # Generate the VLESS link
                    vless_link = self.panel_api.get_vless_link(client_info)
                    
                    # Generate the subscription URL
                    sub_url = self.panel_api.get_subscription_url(client_info)
                except Exception as e:
                    logger.error(f"Error getting client info or generating link: {str(e)}")
                    client_info = {}
                    vless_link = ""
                    sub_url = ""
            
            # Format success message with client details
            expiry_text = "نامحدود" if days == 0 else f"{days} روز"
            traffic_text = "نامحدود" if gb_limit == 0 else f"{gb_limit} GB"
            
            success_text = f"""
✅ *کاربر با موفقیت اضافه شد*
━━━━━━━━━━━━━━━

👤 شناسه کاربر: `{escape_markdown(email)}`
📊 حجم: `{escape_markdown(traffic_text)}`
⏱ مدت اعتبار: `{escape_markdown(expiry_text)}`
🔌 اینباند: `{escape_markdown(str(inbound_id))}`
"""

            # Add links if available
            if vless_link:
                success_text += f"""
🔗 *لینک اتصال*:
`{escape_markdown(vless_link)}`
"""

            if sub_url:
                success_text += f"""
📲 *لینک اشتراک*:
`{escape_markdown(sub_url)}`
"""
            
            # Edit or send the success message
            if processing_msg:
                try:
                    self.bot.edit_message_text(
                        success_text,
                        processing_msg.chat.id,
                        processing_msg.message_id,
                        parse_mode='MarkdownV2'
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {str(e)}")
                    self.bot.send_message(
                        message.chat.id,
                        success_text,
                        parse_mode='MarkdownV2'
                    )
            else:
                self.bot.send_message(
                    message.chat.id,
                    success_text,
                    parse_mode='MarkdownV2'
                )
            
            # Log the action
            logger.info(f"Admin {message.from_user.id} added client {email} to inbound {inbound_id}")
            self.db.log_event(
                'INFO',
                'client_added',
                message.from_user.id,
                f"Client {email} added to inbound {inbound_id}",
                details={
                    'email': email,
                    'inbound_id': inbound_id,
                    'traffic_gb': gb_limit,
                    'days': days,
                    'limit_ip': limit_ip,
                    'telegram_id': telegram_id,
                    'uuid': client_uuid if isinstance(result, str) else None
                }
            )
        except Exception as e:
            logger.error(f"Error handling add client: {str(e)}\n{traceback.format_exc()}")
            try:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ خطای سیستمی: {str(e)}",
                    parse_mode=None
                )
            except Exception as ex:
                logger.error(f"Error sending error message: {str(ex)}")

    def _show_user_details(self, call: CallbackQuery, email: str):
        """Show detailed information for a specific user"""
        try:
            # Get client info
            client_info = self.panel_api.get_client_info(email=email)
            if not client_info:
                self.bot.answer_callback_query(call.id, "❌ اطلاعات کاربر یافت نشد")
                return

            # Calculate traffic usage and limits
            total_traffic = client_info.get('totalGB', 0)
            up = client_info.get('up', 0)
            down = client_info.get('down', 0)
            total_usage = up + down
            remaining = total_traffic * (1024 * 1024 * 1024) - total_usage if total_traffic > 0 else 0
            usage_percent = (total_usage / (total_traffic * (1024 * 1024 * 1024))) * 100 if total_traffic > 0 else 0

            # Format expiry date
            expiry_time = client_info.get('expiryTime', 0)
            expiry_date = format_date(expiry_time/1000) if expiry_time > 0 else "نامحدود"

            # Generate connection links
            vless_link = self.panel_api.get_vless_link(client_info)
            sub_url = self.panel_api.get_subscription_url(client_info)

            # Format response
            response = f"""
{format_bold('👤 اطلاعات کاربر')}
━━━━━━━━━━━━━━━

📧 ایمیل: `{escape_markdown(email)}`
🔄 وضعیت: `آنلاین`

📊 {format_bold('اطلاعات حجم')}:
• کل حجم: `{format_size(total_traffic * (1024 * 1024 * 1024)) if total_traffic > 0 else 'نامحدود'}`
• مصرف شده: `{format_size(total_usage)}`
• باقیمانده: `{format_size(remaining) if total_traffic > 0 else 'نامحدود'}`
• درصد مصرف: `{f"{usage_percent:.1f}%" if total_traffic > 0 else "0%"}`

📈 {format_bold('جزئیات مصرف')}:
• آپلود: `{format_size(up)}`
• دانلود: `{format_size(down)}`

⚙️ {format_bold('تنظیمات')}:
• پروتکل: `{escape_markdown(client_info.get('protocol', 'VLESS').upper())}`
• پورت: `{escape_markdown(str(client_info.get('port', '')))}`
• امنیت: `{escape_markdown(client_info.get('tls', '').upper())}`

⏰ {format_bold('زمان')}:
• تاریخ انقضا: `{escape_markdown(expiry_date)}`
"""

            # Add connection links if available
            if vless_link:
                response += f"""
🔗 {format_bold('لینک اتصال')}:
`{escape_markdown(vless_link)}`
"""

            if sub_url:
                response += f"""
📲 {format_bold('لینک اشتراک')}:
`{escape_markdown(sub_url)}`
"""

            # Create keyboard with action buttons
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.row(
                InlineKeyboardButton("♻️ ریست ترافیک", callback_data=f"reset_traffic:{email}"),
                InlineKeyboardButton("🔙 بازگشت", callback_data="refresh_online_users")
            )

            # Edit message with user details
            self.bot.edit_message_text(
                response,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='MarkdownV2',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Error showing user details: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ خطا در نمایش اطلاعات کاربر")

    @admin_required
    @handle_admin_errors
    def handle_toggle_bot(self, message: Message):
        """Handle /toggle command to enable/disable the bot"""
        try:
            # Get current status
            current_status = self.db.get_bot_status()
            
            # Toggle status
            new_status = not current_status
            
            # Get reason if provided
            reason = None
            if len(message.text.split()) > 1:
                reason = ' '.join(message.text.split()[1:])
            
            # Update status
            success = self.db.set_bot_status(new_status, message.from_user.id, reason)
            
            if success:
                status_text = "فعال" if new_status else "غیرفعال"
                reason_text = f"\nدلیل: `{escape_markdown(reason)}`" if reason else ""
                
                response = f"""
{format_bold('🔄 وضعیت ربات تغییر کرد')}
━━━━━━━━━━━━━━━

• وضعیت جدید: `{escape_markdown(status_text)}`
• توسط: `{escape_markdown(message.from_user.first_name)}`
• زمان: `{escape_markdown(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}`{reason_text}
"""
                
                self.bot.reply_to(
                    message,
                    response,
                    parse_mode='MarkdownV2'
                )
                
                # Log the action
                self.db.log_event(
                    'INFO',
                    'bot_status_toggle',
                    message.from_user.id,
                    f"Bot status changed to {status_text}",
                    details={
                        'previous_status': current_status,
                        'new_status': new_status,
                        'reason': reason
                    }
                )
            else:
                self.bot.reply_to(
                    message,
                    "❌ خطا در تغییر وضعیت ربات\\. لطفاً دوباره تلاش کنید\\.",
                    parse_mode='MarkdownV2'
                )
                
        except Exception as e:
            logger.error(f"Error toggling bot status: {str(e)}\n{traceback.format_exc()}")
            self.bot.reply_to(
                message,
                "❌ خطا در تغییر وضعیت ربات\\. لطفاً دوباره تلاش کنید\\.",
                parse_mode='MarkdownV2'
            )