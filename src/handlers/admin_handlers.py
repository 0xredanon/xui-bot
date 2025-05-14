import types
from typing import Dict, List, Optional
from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
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

from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold
from ..utils.decorators import admin_required
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
from ..utils.panel_api import PanelAPI
from ..models.models import BackupStatus, DatabaseBackup, TelegramUser, VPNClient, SystemLog, SystemLogType
from ..models.base import SessionLocal
from ..utils.backup_manager import BackupManager

# Initialize custom logger
logger = CustomLogger("AdminHandler")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

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
                self.db.log_event(
                    'ERROR',
                    f'admin_handler_error_{func.__name__}',
                    message.from_user.id if message.from_user else None,
                    str(e),
                    details={'traceback': traceback.format_exc()}
                )
    return wrapper

class AdminHandler:
    def __init__(self, bot: TeleBot, db: Database, panel_api: PanelAPI):
        self.bot = bot
        self.db = db
        self.panel_api = panel_api
        # Get admin chat ID from database or environment
        admin_chat_id = self._get_admin_chat_id()
        self.backup_manager = BackupManager(bot, admin_chat_id=admin_chat_id)
        
        # Start backup scheduler
        self.backup_manager.start_scheduler()
        
        logger.info("AdminHandler initialized")

    def _get_admin_chat_id(self) -> int:
        """Get admin chat ID from database"""
        with SessionLocal() as db:
            admin = db.query(TelegramUser).filter_by(is_admin=True).first()
            if not admin:
                logger.error("No admin user found in database")
                raise ValueError("No admin user found")
            return admin.telegram_id

    @admin_required
    @handle_admin_errors
    def handle_user_list(self, message: Message):
        """Handle the /users command to list online users"""
        logger.info(f"Admin {message.from_user.id} requested online users list")
        
        try:
            # Get online clients from panel
            online_clients = self.panel_api.get_online_clients()
            
            if not online_clients:
                self.bot.reply_to(
                    message,
                    "📊 *وضعیت کاربران*\n\n❌ در حال حاضر هیچ کاربری آنلاین نیست\\.",
                    parse_mode='MarkdownV2'
                )
                return

            # Format response message
            response = f"""
{format_bold('📊 وضعیت کاربران آنلاین')}
━━━━━━━━━━━━━━━

"""
            # Add each client's info
            total_up = 0
            total_down = 0
            
            for client in online_clients:
                # اگر client یک رشته باشد، آن را نادیده می‌گیریم
                if isinstance(client, str):
                    continue
                    
                email = client.get('email', 'نامشخص')
                up = int(client.get('up', 0))
                down = int(client.get('down', 0))
                total_up += up
                total_down += down
                
                response += f"""
👤 {format_bold('کاربر')}: {format_code(email)}
🔼 {format_bold('آپلود')}: {format_code(format_size(up))}
🔽 {format_bold('دانلود')}: {format_code(format_size(down))}
━━━━━━━━━━
"""

            # Add summary
            response += f"""
{format_bold('📈 آمار کلی')}:
• تعداد کاربران: {format_code(str(len(online_clients)))}
• مجموع آپلود: {format_code(format_size(total_up))}
• مجموع دانلود: {format_code(format_size(total_down))}
"""

            self.bot.reply_to(message, response, parse_mode='MarkdownV2')
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
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"system_logs_{current_time}.txt"
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
                           f"📅 تاریخ: `{escape_markdown(datetime.now().strftime('%Y-%m-%d'))}`\n"
                           f"⏰ زمان: `{escape_markdown(datetime.now().strftime('%H:%M:%S'))}`\n"
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
            now = datetime.now()
            for file in export_dir.glob("system_logs_*.txt"):
                try:
                    # Extract date from filename
                    date_str = file.stem.split('_')[2]  # Gets YYYYMMDD from system_logs_YYYYMMDD_HHMMSS.txt
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    
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
    def handle_backup(self, message: Message):
        """Handle the /backup command to create database backup"""
        logger.info(f"Admin {message.from_user.id} requested database backup")
        
        # Create a more detailed timestamp with date and time
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        try:
            # Initialize paths as None
            panel_backup_path = None
            panel_gz_path = None
            
            # Define version and build structured filenames
            bot_version = "v1.0"  # You can update this based on your versioning
            bot_backup_name = f"xui_bot_backup_{bot_version}_{timestamp}"
            panel_backup_name = f"xui_panel_backup_{bot_version}_{timestamp}"
            
            # 1. Create bot database backup
            bot_backup_data = self._create_bot_backup()
            
            # Save bot database backup with structured names
            bot_json_path = backup_dir / f"{bot_backup_name}.json"
            bot_gz_path = backup_dir / f"{bot_backup_name}.json.gz"
            
            # Save uncompressed bot backup
            with open(bot_json_path, 'w', encoding='utf-8') as f:
                json.dump(bot_backup_data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
            logger.info(f"Bot database backup saved: {bot_json_path}")
            
            # Create compressed bot backup
            with open(bot_json_path, 'rb') as f_in:
                with gzip.open(bot_gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"Compressed bot backup saved: {bot_gz_path}")
            
            # 2. Get panel database backup
            panel_backup = self.panel_api.create_backup()
            if panel_backup:
                panel_backup_path = backup_dir / f"{panel_backup_name}.json"
                with open(panel_backup_path, 'w', encoding='utf-8') as f:
                    json.dump(panel_backup, f, indent=2, ensure_ascii=False)
                logger.info(f"Panel backup saved: {panel_backup_path}")
                
                # Create compressed panel backup
                panel_gz_path = backup_dir / f"{panel_backup_name}.json.gz"
                with open(panel_backup_path, 'rb') as f_in:
                    with gzip.open(panel_gz_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                logger.info(f"Compressed panel backup saved: {panel_gz_path}")
            else:
                logger.error("Failed to get panel backup: No data received")
            
            # Clean up old backups (keep last 7 days)
            self._cleanup_old_backups(backup_dir)
            
            # Format date for display
            formatted_date = datetime.now().strftime('%Y\\-%m\\-%d %H:%M:%S')
            
            # Prepare response message
            response = f"""
{format_bold('✅ بکاپ با موفقیت ایجاد شد')}
━━━━━━━━━━━━━━━

{format_bold('📁 بکاپ دیتابیس ربات')}:
• نسخه: `{bot_version}`
• تاریخ: `{formatted_date}`
• فایل: `{bot_json_path.name}`
• حجم: `{format_size(bot_json_path.stat().st_size)}`
• فشرده: `{bot_gz_path.name}`
• حجم فشرده: `{format_size(bot_gz_path.stat().st_size)}`
"""

            if panel_backup_path and panel_backup_path.exists():
                response += f"""
{format_bold('📁 بکاپ دیتابیس پنل')}:
• نسخه: `{bot_version}`
• تاریخ: `{formatted_date}`
• فایل: `{panel_backup_path.name}`
• حجم: `{format_size(panel_backup_path.stat().st_size)}`
• فشرده: `{panel_gz_path.name}`
• حجم فشرده: `{format_size(panel_gz_path.stat().st_size)}`
"""
            else:
                response += "\n⚠️ *خطا در دریافت بکاپ پنل*"
            
            # Send backup files
            self.bot.reply_to(message, response, parse_mode='MarkdownV2')
            
            # Send bot database backup file with escaped caption
            with open(bot_gz_path, 'rb') as f:
                self.bot.send_document(
                    message.chat.id,
                    f,
                    caption=f"🤖 *XUI Bot Backup*\n"
                           f"• Version: `{bot_version}`\n"
                           f"• Date: `{formatted_date}`",
                    parse_mode='MarkdownV2'
                )
            
            # Send panel backup file if available
            if panel_gz_path and panel_gz_path.exists():
                with open(panel_gz_path, 'rb') as f:
                    self.bot.send_document(
                        message.chat.id,
                        f,
                        caption=f"🖥 *XUI Panel Backup*\n"
                               f"• Version: `{bot_version}`\n"
                               f"• Date: `{formatted_date}`",
                        parse_mode='MarkdownV2'
                    )
            
            logger.info(f"Backup completed successfully for admin {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError("Failed to create database backup")

    def _create_bot_backup(self) -> dict:
        """Create backup of bot database"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            backup_data = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'version': '1.0',
                    'tables': []
                },
                'data': {}
            }
            
            # Get list of all tables
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM information_schema.tables 
                WHERE table_schema = %s 
                AND table_type = 'BASE TABLE'
            """, (self.db.db_config['database'],))
            
            tables = [row[0] for row in cursor.fetchall()]
            backup_data['metadata']['tables'] = tables
            
            # Backup each table
            for table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()
                
                backup_data['data'][table] = {
                    'columns': columns,
                    'rows': [dict(zip(columns, row)) for row in rows]
                }
            
            return backup_data

    def _cleanup_old_backups(self, backup_dir: Path, keep_days: int = 7):
        """Clean up old backup files"""
        try:
            # Get current time
            now = datetime.now()
            
            # List all backup files
            backup_files = []
            for ext in ['*.json', '*.json.gz']:
                backup_files.extend(backup_dir.glob(ext))
            
            # Process each file
            for file_path in backup_files:
                try:
                    # Extract date from filename using regex
                    match = re.search(r'_(\d{8})_', file_path.name)
                    if not match:
                        continue
                        
                    # Parse date from filename
                    file_date_str = match.group(1)
                    file_date = datetime.strptime(file_date_str, '%Y%m%d')
                    
                    # Delete if older than keep_days
                    if (now - file_date).days > keep_days:
                        file_path.unlink()
                        logger.info(f"Deleted old backup: {file_path}")
                        
                except (ValueError, OSError) as e:
                    logger.warning(f"Error processing backup file {file_path}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error cleaning up backups: {str(e)}")

    @admin_required
    @handle_admin_errors
    def handle_broadcast(self, message: Message):
        """Handle broadcast command"""
        try:
            # Check if user is admin
            if not self._is_admin(message.from_user.id):
                self.bot.reply_to(message, "❌ شما دسترسی به این دستور را ندارید.")
                return

            # Get broadcast message
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                raise ValidationError(
                    "Please provide the message to broadcast.\n"
                    "Usage: /broadcast your message here"
                )

            broadcast_msg = parts[1]
            
            # Get active users from database
            with SessionLocal() as db:
                active_users = db.query(TelegramUser).filter(
                    TelegramUser.is_active == True,
                    TelegramUser.last_seen > datetime.now() - timedelta(days=30)
                ).all()

            if not active_users:
                self.bot.reply_to(message, "❌ No active users found to broadcast to.")
                return

            # Send broadcast
            success_count = 0
            failed_count = 0
            failed_users = []

            status_msg = self.bot.reply_to(
                message, 
                f"📤 Broadcasting message to {len(active_users)} users..."
            )

            for user in active_users:
                try:
                    self.bot.send_message(
                        user.telegram_id,
                        f"📢 *پیام مدیریت*\n\n{broadcast_msg}",
                        parse_mode='MarkdownV2'
                    )
                    success_count += 1
                    
                    # Update status every 10 users
                    if (success_count + failed_count) % 10 == 0:
                        self.bot.edit_message_text(
                            f"📤 Broadcasting: {success_count + failed_count}/{len(active_users)} users processed...",
                            status_msg.chat.id,
                            status_msg.message_id
                        )
                        
                except Exception as e:
                    logger.error(f"Failed to send broadcast to user {user.telegram_id}: {str(e)}")
                    failed_count += 1
                    failed_users.append(user.telegram_id)

            # Final status update
            final_status = (
                f"📬 Broadcast completed:\n"
                f"✅ Successful: {success_count}\n"
                f"❌ Failed: {failed_count}"
            )
            
            if failed_users:
                final_status += f"\n\nFailed user IDs: {', '.join(map(str, failed_users))}"
                
            self.bot.edit_message_text(
                final_status,
                status_msg.chat.id,
                status_msg.message_id
            )

            # Log the broadcast
            self.db.log_admin_action(
                admin_id=message.from_user.id,
                action="broadcast",
                details={
                    "message": broadcast_msg,
                    "total_users": len(active_users),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_users": failed_users
                }
            )

        except ValidationError as e:
            self.bot.reply_to(message, f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Error in broadcast: {str(e)}")
            self.bot.reply_to(message, "❌ Error processing broadcast command.")

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
• زمان سرور: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
"""

            # Create refresh button
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data="refresh_system"
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

    def register_handlers(self):
        """Register all admin command handlers"""
        try:
            logger.info("Registering admin command handlers")
            
            # Register command handlers
            self.bot.message_handler(commands=['users'])(self.handle_user_list)
            self.bot.message_handler(commands=['logs'])(self.handle_logs)
            self.bot.message_handler(commands=['backup'])(self.handle_backup)
            self.bot.message_handler(commands=['broadcast'])(self.handle_broadcast)
            self.bot.message_handler(commands=['system'])(self.handle_system)
            
            logger.info("Admin command handlers registered successfully")
            
            # Log registration
            self.db.log_event(
                'INFO',
                'admin_handlers_registered',
                None,
                'Admin command handlers registered successfully',
                details={'handlers': ['users', 'logs', 'backup', 'broadcast', 'system']}
            )
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
    
    def handle_callback(self, call: CallbackQuery):
        """Handle admin callback queries"""
        try:
            if call.data == "refresh_system":
                self._refresh_system_info(call)
            action, *params = call.data.split(":")
            email = params[0]
            
            # Get client
            client = self._get_client_by_email(email)
            if not client:
                self.bot.answer_callback_query(call.id, "❌ Client not found.")
                return
                
            if action == "set_volume":
                gb = int(params[1])
                success = self._set_client_volume(client, gb, call.from_user.id)
                self.bot.answer_callback_query(
                    call.id,
                    f"✅ Volume set to {gb}GB" if success else "❌ Failed to set volume"
                )
                
            elif action == "reset_volume":
                success = self._reset_client_volume(client, call.from_user.id)
                self.bot.answer_callback_query(
                    call.id,
                    "✅ Volume reset to initial value" if success else "❌ Failed to reset volume"
                )
                
            elif action == "set_unlimited":
                success = self._set_client_volume(client, 0, call.from_user.id)
                self.bot.answer_callback_query(
                    call.id,
                    "✅ Set to unlimited volume" if success else "❌ Failed to set unlimited"
                )
                
            elif action == "custom_volume":
                msg = self.bot.send_message(
                    call.message.chat.id,
                    "📝 Please enter the desired volume in GB (e.g., 25):"
                )
                self.bot.register_next_step_handler(msg, self._handle_custom_volume, client)
                
            elif action == "set_expiry":
                days = int(params[1])
                success = self._set_client_expiry(client, days, call.from_user.id)
                expiry_text = "never expires" if days == 0 else f"expires in {days} days"
                self.bot.answer_callback_query(
                    call.id,
                    f"✅ Client now {expiry_text}" if success else "❌ Failed to set expiry"
                )
                
            elif action == "view_ips":
                ips = self._get_client_ips(client)
                if ips:
                    ip_text = "🌐 Connected IPs:\n\n" + "\n".join(f"- {ip}" for ip in ips)
                else:
                    ip_text = "ℹ️ No active connections"
                self.bot.answer_callback_query(call.id)
                self.bot.send_message(call.message.chat.id, ip_text)
                
            elif action == "reset_traffic":
                success = self._reset_client_traffic(client, call.from_user.id)
                self.bot.answer_callback_query(
                    call.id,
                    "✅ Traffic reset successfully" if success else "❌ Failed to reset traffic"
                )
            
            # Update message with new info if needed
            if action in ["set_volume", "reset_volume", "set_unlimited", "set_expiry", "reset_traffic"]:
                client = self._get_client_by_email(email)  # Refresh client info
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
                
                self.bot.edit_message_text(
                    info_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=call.message.reply_markup
                )
                
        except Exception as e:
            logger.error(f"Error handling callback: {str(e)}")
            self.bot.answer_callback_query(call.id, "❌ An error occurred")
    
    def _handle_custom_volume(self, message: Message, client: VPNClient):
        """Handle custom volume input"""
        try:
            volume = int(message.text)
            if volume <= 0:
                self.bot.reply_to(message, "❌ Please enter a positive number.")
                return
                
            success = self._set_client_volume(client, volume, message.from_user.id)
            self.bot.reply_to(
                message,
                f"✅ Volume set to {volume}GB" if success else "❌ Failed to set volume"
            )
            
        except ValueError:
            self.bot.reply_to(message, "❌ Please enter a valid number.")
    
    def _get_client_by_email(self, email: str) -> Optional[VPNClient]:
        """Get client by email"""
        with SessionLocal() as db:
            return db.query(VPNClient).filter_by(email=email).first()
    
    def _set_client_volume(self, client: VPNClient, gb: int, admin_id: int) -> bool:
        """Set client volume and log the action"""
        try:
            with SessionLocal() as db:
                # Update client
                client.total_gb = gb
                client.last_sync = datetime.utcnow()
                
                # Log action
                log = SystemLog(
                    log_type=SystemLogType.VOLUME_CHANGE,
                    user_id=admin_id,
                    client_id=client.id,
                    details={
                        'old_volume': client.total_gb,
                        'new_volume': gb,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                db.add(log)
                db.commit()
                
            return True
            
        except Exception as e:
            logger.error(f"Error setting client volume: {str(e)}")
            return False
    
    def _reset_client_volume(self, client: VPNClient, admin_id: int) -> bool:
        """Reset client volume to initial value"""
        # You can define your initial volume value here
        return self._set_client_volume(client, 10, admin_id)  # Default 10GB
    
    def _set_client_expiry(self, client: VPNClient, days: int, admin_id: int) -> bool:
        """Set client expiry and log the action"""
        try:
            with SessionLocal() as db:
                old_expiry = client.expire_time
                
                # Set new expiry
                if days == 0:
                    client.expire_time = 0
                else:
                    expiry_date = datetime.utcnow() + timedelta(days=days)
                    client.expire_time = int(expiry_date.timestamp() * 1000)
                
                client.last_sync = datetime.utcnow()
                
                # Log action
                log = SystemLog(
                    log_type=SystemLogType.EXPIRY_CHANGE,
                    user_id=admin_id,
                    client_id=client.id,
                    details={
                        'old_expiry': old_expiry,
                        'new_expiry': client.expire_time,
                        'days_added': days,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                db.add(log)
                db.commit()
                
            return True
            
        except Exception as e:
            logger.error(f"Error setting client expiry: {str(e)}")
            return False
    
    def _get_client_ips(self, client: VPNClient) -> List[str]:
        """Get client's connected IPs"""
        try:
            response = self.panel_api.get_client_ips(client.email)
            return response.get('ips', []) if response else []
        except Exception as e:
            logger.error(f"Error getting client IPs: {str(e)}")
            return []
    
    def _reset_client_traffic(self, client: VPNClient, admin_id: int) -> bool:
        """Reset client traffic and log the action"""
        try:
            response = self.panel_api.reset_client_traffic(client.inbound_id, client.email)
            if not response:
                return False
                
            with SessionLocal() as db:
                # Update client
                old_upload = client.upload
                old_download = client.download
                client.upload = 0
                client.download = 0
                client.last_sync = datetime.utcnow()
                
                # Log action
                log = SystemLog(
                    log_type=SystemLogType.TRAFFIC_RESET,
                    user_id=admin_id,
                    client_id=client.id,
                    details={
                        'old_upload': old_upload,
                        'old_download': old_download,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                db.add(log)
                db.commit()
                
            return True
            
        except Exception as e:
            logger.error(f"Error resetting client traffic: {str(e)}")
            return False
    
    def handle_backup_command(self, message: Message, user: TelegramUser):
        """Handle backup commands"""
        command = message.text.lower()
        
        if command == "/backup":
            # Create manual backup
            success = self.backup_manager.create_manual_backup(user)
            if success:
                self.bot.reply_to(message, "✅ Manual backup created and sent to you.")
            else:
                self.bot.reply_to(message, "❌ Failed to create backup.")
                
        elif command == "/backups":
            # Show backup status and controls
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "✅ Enable Auto-Backup" if not self.backup_manager.is_backup_enabled else "❌ Disable Auto-Backup",
                    callback_data="toggle_backup"
                )
            )
            keyboard.row(
                InlineKeyboardButton("📥 Create Backup Now", callback_data="create_backup")
            )
            
            with SessionLocal() as db:
                recent_backups = (
                    db.query(DatabaseBackup)
                    .order_by(DatabaseBackup.created_at.desc())
                    .limit(5)
                    .all()
                )
                
                status_text = (
                    f"🔄 Backup Status\n\n"
                    f"Auto-Backup: {'✅ Enabled' if self.backup_manager.is_backup_enabled else '❌ Disabled'}\n"
                    f"Schedule: Every hour at minute 0\n\n"
                    f"Recent Backups:\n"
                )
                
                for backup in recent_backups:
                    status = "✅" if backup.status == BackupStatus.COMPLETED else "❌"
                    size = self.backup_manager._format_size(backup.size_bytes)
                    status_text += f"{status} {backup.created_at.strftime('%Y-%m-%d %H:%M')} ({size})\n"
            
            self.bot.reply_to(message, status_text, reply_markup=keyboard)
    
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
• زمان سرور: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
"""

            # Update message with refresh button
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data="refresh_system"
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
            except Exception as e:
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