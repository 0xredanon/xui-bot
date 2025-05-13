from typing import Dict, List, Optional
from telebot import TeleBot
from telebot.types import Message, CallbackQuery
from datetime import datetime, timedelta
import json
import os
import gzip
import shutil
from pathlib import Path
import traceback
from functools import wraps

from ..database.db import Database
from ..utils.formatting import format_size, format_date, escape_markdown, format_code, format_bold
from ..utils.decorators import admin_required
from ..utils.logger import CustomLogger
from ..utils.exceptions import *
from ..utils.panel_api import PanelAPI

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
        logger.info("AdminHandler initialized")

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
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            limit = 10  # Default limit
            
            if args:
                if not args[0].isdigit():
                    raise ValidationError("Please provide a valid number for log limit")
                limit = min(int(args[0]), 50)  # Max 50 logs
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, level, event_type, message, user_id, details
                    FROM logs 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
                logs = cursor.fetchall()
                
                if not logs:
                    self.bot.reply_to(message, "No logs found\\.")
                    return
                
                response = f"*Recent Logs* \\(Last {limit}\\)\n\n"
                for log in logs:
                    timestamp, level, event_type, msg, user_id, details = log
                    level_emoji = {
                        'INFO': 'ℹ️',
                        'WARNING': '⚠️',
                        'ERROR': '❌',
                        'CRITICAL': '🔴'
                    }.get(level, '📝')
                    
                    response += f"{level_emoji} `{format_date(timestamp)}`\n"
                    response += f"Type: `{escape_markdown(event_type)}`\n"
                    if user_id:
                        response += f"User: `{user_id}`\n"
                    response += f"Message: {escape_markdown(msg)}\n"
                    if details:
                        try:
                            details_dict = json.loads(details)
                            if isinstance(details_dict, dict):
                                response += "Details:\n"
                                for key, value in details_dict.items():
                                    if not str(value).startswith('traceback'):  # Skip traceback in output
                                        response += f"• {escape_markdown(key)}: `{escape_markdown(str(value))}`\n"
                        except json.JSONDecodeError:
                            pass
                    response += "\n"
                
                self.bot.reply_to(message, response, parse_mode='MarkdownV2')
                logger.info(f"Logs sent to admin {message.from_user.id}")
                
                self.db.log_admin_action(
                    message.from_user.id,
                    'view_logs',
                    None,
                    {'limit': limit, 'log_count': len(logs)}
                )
        except Exception as e:
            logger.error(f"Error fetching logs: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError("Failed to fetch system logs")

    @admin_required
    @handle_admin_errors
    def handle_backup(self, message: Message):
        """Handle the /backup command to create database backup"""
        logger.info(f"Admin {message.from_user.id} requested database backup")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        # Regular JSON backup
        json_backup_path = backup_dir / f"backup_{timestamp}.json"
        # Compressed backup
        gz_backup_path = backup_dir / f"backup_{timestamp}.json.gz"
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                backup_data = {
                    'metadata': {
                        'timestamp': timestamp,
                        'version': '1.0',
                        'created_by': message.from_user.id,
                        'tables': []
                    },
                    'data': {}
                }
                
                # Get list of all tables
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
                backup_data['metadata']['tables'] = tables
                
                # Backup each table
                for table in tables:
                    logger.debug(f"Backing up table: {table}")
                    cursor.execute(f"SELECT * FROM {table}")
                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()
                    
                    backup_data['data'][table] = {
                        'columns': columns,
                        'rows': [dict(zip(columns, row)) for row in rows]
                    }
                
                # Save uncompressed backup
                with open(json_backup_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Uncompressed backup saved: {json_backup_path}")
                
                # Create compressed version
                with open(json_backup_path, 'rb') as f_in:
                    with gzip.open(gz_backup_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                logger.info(f"Compressed backup saved: {gz_backup_path}")
                
                # Clean up old backups (keep last 7 days by default)
                retention_days = int(os.getenv('BACKUP_RETENTION_DAYS', '7'))
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                
                deleted_count = 0
                for old_backup in backup_dir.glob('backup_*.json*'):
                    try:
                        backup_date = datetime.strptime(
                            old_backup.stem[:15],
                            'backup_%Y%m%d'
                        )
                        if backup_date < cutoff_date:
                            old_backup.unlink()
                            deleted_count += 1
                    except (ValueError, OSError) as e:
                        logger.warning(f"Error cleaning up old backup {old_backup}: {e}")
                        continue
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old backup(s)")
                
                # Get backup sizes
                json_size = json_backup_path.stat().st_size
                gz_size = gz_backup_path.stat().st_size
                
                response = (
                    f"✅ Backup created successfully\\!\n\n"
                    f"📁 JSON Backup: `{json_backup_path.name}`\n"
                    f"Size: `{format_size(json_size)}`\n\n"
                    f"🗜 Compressed Backup: `{gz_backup_path.name}`\n"
                    f"Size: `{format_size(gz_size)}`\n"
                    f"Compression ratio: `{(1 - gz_size/json_size)*100:.1f}%`\n\n"
                    f"🧹 Cleaned up: `{deleted_count}` old backup\\(s\\)"
                )
                
                self.bot.reply_to(message, response, parse_mode='MarkdownV2')
                logger.info(f"Backup completed successfully for admin {message.from_user.id}")
                
                self.db.log_admin_action(
                    message.from_user.id,
                    'create_backup',
                    None,
                    {
                        'json_backup': str(json_backup_path),
                        'gz_backup': str(gz_backup_path),
                        'json_size': json_size,
                        'gz_size': gz_size,
                        'deleted_count': deleted_count,
                        'tables_backed_up': len(tables)
                    }
                )
                
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}\n{traceback.format_exc()}")
            
            # Clean up any partial backups
            for path in [json_backup_path, gz_backup_path]:
                try:
                    if path.exists():
                        path.unlink()
                        logger.info(f"Cleaned up partial backup: {path}")
                except OSError as cleanup_error:
                    logger.error(f"Error cleaning up partial backup {path}: {cleanup_error}")
            
            raise DatabaseError("Failed to create database backup")

    @admin_required
    @handle_admin_errors
    def handle_broadcast(self, message: Message):
        """Handle the /broadcast command to send message to all users"""
        logger.info(f"Admin {message.from_user.id} initiated broadcast")
        
        args = message.text.split(maxsplit=1)
        if len(args) != 2:
            raise ValidationError("Please provide the message to broadcast.\nUsage: /broadcast your message here")
        
        broadcast_message = args[1].strip()
        if not broadcast_message:
            raise ValidationError("Broadcast message cannot be empty")
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE status = 'active'")
                users = cursor.fetchall()
                
                if not users:
                    self.bot.reply_to(message, "No active users found to broadcast to\\.")
                    return
                
                success_count = 0
                fail_count = 0
                
                for user_id, in users:
                    try:
                        self.bot.send_message(user_id, broadcast_message)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                        fail_count += 1
                
                response = (
                    f"📢 *Broadcast Results*\n\n"
                    f"✅ Successful: `{success_count}`\n"
                    f"❌ Failed: `{fail_count}`\n"
                    f"📊 Total: `{len(users)}`"
                )
                
                self.bot.reply_to(message, response, parse_mode='MarkdownV2')
                logger.info(f"Broadcast completed: {success_count} successful, {fail_count} failed")
                
                self.db.log_admin_action(
                    message.from_user.id,
                    'broadcast',
                    None,
                    {
                        'total_users': len(users),
                        'success_count': success_count,
                        'fail_count': fail_count,
                        'message_length': len(broadcast_message)
                    }
                )
        except Exception as e:
            logger.error(f"Error in broadcast: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError("Failed to execute broadcast")

    @admin_required
    @handle_admin_errors
    def handle_system_info(self, message: Message):
        """Handle the /system command to show system information"""
        logger.info(f"Admin {message.from_user.id} requested system information")
        
        try:
            import psutil
            import platform
            
            # System information
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            response = f"""
💻 *System Information*
OS: `{platform.system()} {platform.release()}`
CPU Usage: `{cpu_percent}%`
Memory: `{format_size(memory.used)}/{format_size(memory.total)} ({memory.percent}%)`
Disk: `{format_size(disk.used)}/{format_size(disk.total)} ({disk.percent}%)`

🔄 *Process Information*
Python: `{platform.python_version()}`
PID: `{os.getpid()}`
Threads: `{psutil.Process().num_threads()}`
            """
            
            self.bot.reply_to(message, response, parse_mode='MarkdownV2')
            logger.info(f"System information sent to admin {message.from_user.id}")
            
            self.db.log_admin_action(
                message.from_user.id,
                'view_system_info',
                None,
                {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'disk_percent': disk.percent
                }
            )
        except ImportError:
            logger.error("psutil module not installed")
            raise ValidationError("System monitoring package not installed")
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}\n{traceback.format_exc()}")
            raise

    def register_handlers(self):
        """Register all admin command handlers"""
        try:
            logger.info("Registering admin command handlers")
            
            # Register command handlers
            self.bot.message_handler(commands=['users'])(self.handle_user_list)
            self.bot.message_handler(commands=['logs'])(self.handle_logs)
            self.bot.message_handler(commands=['backup'])(self.handle_backup)
            self.bot.message_handler(commands=['broadcast'])(self.handle_broadcast)
            self.bot.message_handler(commands=['system'])(self.handle_system_info)
            
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