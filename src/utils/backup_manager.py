import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import schedule
import threading
import time
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, inspect, text
from telebot import TeleBot
import gzip
import shutil
import re
import traceback
import logging
from functools import wraps
import backoff

from ..models.models import DatabaseBackup, BackupStatus, TelegramUser
from ..models.base import SessionLocal, engine
from ..utils.logger import CustomLogger
from ..utils.datetime_encoder import DateTimeEncoder
from ..utils.exceptions import DatabaseError
from ..utils.formatting import format_size, escape_markdown
from ..config import BACKUP_DIR

logger = logging.getLogger(__name__)

def retry_on_error(max_tries=3, max_time=30):
    """Decorator for retrying operations on failure"""
    def decorator(func):
        @wraps(func)
        @backoff.on_exception(
            backoff.expo,
            Exception,
            max_tries=max_tries,
            max_time=max_time
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

class BackupManager:
    def __init__(self, bot: TeleBot, panel_api):
        self.bot = bot
        self.panel_api = panel_api
        self.backup_dir = Path(BACKUP_DIR)
        self.is_backup_enabled = True
        self.backup_thread = None
        self._backup_lock = threading.Lock()  # Add lock for thread safety
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("BackupManager initialized")
    
    def start_scheduler(self):
        """Start the backup scheduler in a separate thread"""
        if self.backup_thread is not None and self.backup_thread.is_alive():
            logger.warning("Backup scheduler is already running")
            return
            
        def run_scheduler():
            # Schedule backup for every hour at minute 0
            schedule.every().hour.at(":00").do(self.create_scheduled_backup)
            
            while self.is_backup_enabled:
                try:
                    schedule.run_pending()
                    time.sleep(60)  # Sleep for 1 minute
                except Exception as e:
                    logger.error(f"Error in backup scheduler: {str(e)}")
                    time.sleep(60)  # Sleep before retrying
        
        self.backup_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.backup_thread.start()
        logger.info("Backup scheduler started")
    
    def stop_scheduler(self):
        """Stop the backup scheduler"""
        self.is_backup_enabled = False
        if self.backup_thread and self.backup_thread.is_alive():
            self.backup_thread.join(timeout=2)
        logger.info("Backup scheduler stopped")
    
    @retry_on_error(max_tries=3)
    def create_manual_backup(self, user: TelegramUser) -> bool:
        """Create a manual backup and send it to the user"""
        with self._backup_lock:  # Use lock to prevent concurrent backups
            try:
                # Create backup record
                backup_record = DatabaseBackup(
                    filename=f"xui_bot_backup_v1.5.0_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gz",
                    status=BackupStatus.PENDING,
                    created_at=datetime.now(),
                    is_automatic=False,
                    created_by_id=user.id
                )
                
                # Add to session and flush to get the ID
                with SessionLocal() as db:
                    db.add(backup_record)
                    db.flush()
                    backup_id = backup_record.id
                    
                    try:
                        # Create backup data
                        backup_data = self._create_backup_data(db.get_bind())
                        
                        # Create backup directory if it doesn't exist
                        backup_dir = Path("backups")
                        backup_dir.mkdir(exist_ok=True)
                        
                        # Save backup file
                        backup_path = backup_dir / backup_record.filename
                        with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
                            json.dump(backup_data, f, ensure_ascii=False, indent=2)
                        
                        # Update backup record
                        backup_record.status = BackupStatus.COMPLETED
                        backup_record.completed_at = datetime.now()
                        backup_record.size_bytes = backup_path.stat().st_size
                        backup_record.file_path = str(backup_path)
                        
                        db.commit()
                        
                        # Try to get panel backup
                        panel_backup = None
                        last_error = None
                        
                        try:
                            panel_backup = self.panel_api.create_backup()
                            if panel_backup and isinstance(panel_backup, dict) and panel_backup.get('success'):
                                # Save panel backup
                                panel_json_path = backup_dir / f"xui_panel_backup_v1.5.0_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                panel_gz_path = backup_dir / f"xui_panel_backup_v1.5.0_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gz"
                                
                                with open(panel_json_path, 'w', encoding='utf-8') as f:
                                    json.dump(panel_backup['data'], f, indent=2, ensure_ascii=False)
                                logger.info(f"Panel JSON backup saved: {panel_json_path}")
                                
                                # Create compressed backup
                                with open(panel_json_path, 'rb') as f_in:
                                    with gzip.open(panel_gz_path, 'wb') as f_out:
                                        shutil.copyfileobj(f_in, f_out)
                                logger.info(f"Compressed panel JSON backup saved: {panel_gz_path}")
                            else:
                                last_error = panel_backup.get('error', 'Unknown error') if isinstance(panel_backup, dict) else 'Invalid response format'
                                logger.error(f"Failed to create panel backup: {last_error}")
                                
                        except Exception as e:
                            last_error = str(e)
                            logger.error(f"Error creating panel backup: {last_error}")
                        
                        # Clean up old backups
                        try:
                            self._cleanup_old_backups(backup_dir)
                        except Exception as e:
                            logger.warning(f"Failed to clean up old backups: {str(e)}")
                        
                        # Format date for display
                        formatted_date = datetime.now().strftime('%Y\\-%m\\-%d %H:%M:%S')
                        
                        # Prepare response message
                        response = f"""
✅ *بکاپ با موفقیت ایجاد شد*
━━━━━━━━━━━━━━━

📁 *بکاپ دیتابیس ربات*:
• نسخه: `1.5.0`
• تاریخ: `{formatted_date}`
• فایل JSON: `{backup_path.name}`
• حجم: `{format_size(backup_path.stat().st_size)}`
• فشرده: `{backup_path.name}`
• حجم فشرده: `{format_size(backup_path.stat().st_size)}`
"""

                        if panel_backup and isinstance(panel_backup, dict) and panel_backup.get('success'):
                            response += f"""
📁 *بکاپ دیتابیس پنل*:
• نسخه: `1.5.0`
• تاریخ: `{formatted_date}`
• فایل JSON: `{panel_json_path.name}`
• حجم: `{format_size(panel_json_path.stat().st_size)}`
• فشرده: `{panel_gz_path.name}`
• حجم فشرده: `{format_size(panel_gz_path.stat().st_size)}`
• پیام: `{escape_markdown(panel_backup.get('message', 'Backup successful'))}`
"""
                        else:
                            response += f"\n⚠️ *خطا در دریافت بکاپ پنل*\n`{escape_markdown(last_error if last_error else 'دلیل نامشخص')}`"
                        
                        # Send message to user
                        self.bot.send_message(user.telegram_id, response, parse_mode='MarkdownV2')
                        
                        # Send backup files
                        for backup_file in [backup_path]:
                            try:
                                with open(backup_file, 'rb') as f:
                                    self.bot.send_document(
                                        user.telegram_id,
                                        f,
                                        caption=f"🤖 *XUI Bot Backup*\n"
                                               f"• Version: `1.5.0`\n"
                                               f"• Date: `{formatted_date}`",
                                        parse_mode='MarkdownV2'
                                    )
                            except Exception as e:
                                logger.error(f"Failed to send bot backup file {backup_file}: {str(e)}")
                        
                        # Send panel backup if available
                        if panel_backup and isinstance(panel_backup, dict) and panel_backup.get('success'):
                            try:
                                with open(panel_gz_path, 'rb') as f:
                                    self.bot.send_document(
                                        user.telegram_id,
                                        f,
                                        caption=f"🖥 *XUI Panel Backup*\n"
                                               f"• Version: `1.5.0`\n"
                                               f"• Date: `{formatted_date}`\n"
                                               f"• Source: `{escape_markdown(panel_backup.get('message', 'Unknown'))}`",
                                        parse_mode='MarkdownV2'
                                    )
                            except Exception as e:
                                logger.error(f"Failed to send panel backup file: {str(e)}")
                        
                        logger.info(f"Backup completed successfully for user {user.telegram_id}")
                        return True
                        
                    except Exception as e:
                        logger.error(f"Failed to create bot backup: {str(e)}")
                        # Update backup record with error
                        backup_record = db.query(DatabaseBackup).get(backup_id)
                        if backup_record:
                            backup_record.status = BackupStatus.FAILED
                            backup_record.error_message = str(e)
                            db.commit()
                        raise DatabaseError("Failed to create backup data")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error creating backup: {error_msg}\n{traceback.format_exc()}")
                
                # Send error message to user
                error_response = f"""
❌ *خطا در ایجاد بکاپ*
━━━━━━━━━━━━━━━
• دلیل: `{escape_markdown(error_msg)}`
"""
                self.bot.send_message(user.telegram_id, error_response, parse_mode='MarkdownV2')
                return False
    
    def _update_backup_status(self, backup_id: int, status: BackupStatus, error_message: str = None):
        """Update backup status in database"""
        try:
            with SessionLocal() as db:
                backup = db.query(DatabaseBackup).filter_by(id=backup_id).first()
                if backup:
                    backup.status = status
                    if error_message:
                        backup.error_message = error_message
                    if status == BackupStatus.COMPLETED:
                        backup.completed_at = datetime.utcnow()
                    db.commit()
        except Exception as e:
            logger.error(f"Error updating backup status: {str(e)}")
    
    @retry_on_error(max_tries=3)
    def create_scheduled_backup(self) -> bool:
        """Create a scheduled backup"""
        try:
            # Get admin user
            with SessionLocal() as db:
                admin = db.query(TelegramUser).filter_by(is_admin=True).first()
                if not admin:
                    logger.error("No admin user found for scheduled backup")
                    return False
                    
            return self.create_manual_backup(admin)
            
        except Exception as e:
            logger.error(f"Error in scheduled backup: {str(e)}")
            return False
    
    def _create_backup_data(self, engine):
        """Create backup data from database tables"""
        try:
            # Get all table names using inspect
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            backup_data = {}
            for table in tables:
                # Skip system tables
                if table.startswith('_') or table in ['alembic_version']:
                    continue
                    
                # Get table data
                with engine.connect() as conn:
                    result = conn.execute(text(f"SELECT * FROM {table}"))
                    rows = result.fetchall()
                    columns = result.keys()
                    
                    # Convert rows to list of dicts
                    table_data = []
                    for row in rows:
                        row_dict = dict(zip(columns, row))
                        # Convert datetime objects to ISO format
                        for key, value in row_dict.items():
                            if isinstance(value, datetime):
                                row_dict[key] = value.isoformat()
                        table_data.append(row_dict)
                    
                    backup_data[table] = table_data
                    
            return backup_data
        except Exception as e:
            logger.error(f"Error creating backup data: {str(e)}")
            raise DatabaseError("Failed to create backup data")
    
    def _cleanup_old_backups(self, backup_dir: Path, keep_days: int = 7):
        """Clean up old backup files"""
        try:
            # Get current time
            now = datetime.now()
            deleted_count = 0
            error_count = 0
            
            # List all backup files
            backup_files = []
            for ext in ['*.json', '*.json.gz']:
                try:
                    backup_files.extend(backup_dir.glob(ext))
                except Exception as e:
                    logger.error(f"Error listing {ext} files: {str(e)}")
                    error_count += 1
            
            # Process each file
            for file_path in backup_files:
                try:
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    # Delete if older than keep_days
                    if (now - file_mtime).days > keep_days:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old backup: {file_path}")
                        
                except (ValueError, OSError) as e:
                    logger.warning(f"Error processing backup file {file_path}: {str(e)}")
                    error_count += 1
                    continue
            
            logger.info(f"Backup cleanup completed: {deleted_count} files deleted, {error_count} errors")
                    
        except Exception as e:
            logger.error(f"Error cleaning up backups: {str(e)}")
    
    def _send_backup_notification(self, json_path: Path, gz_path: Path, is_automated: bool, admin_user: TelegramUser = None):
        """Send backup notification and files to admin"""
        try:
            # Format message
            backup_type = "🤖 Automated" if is_automated else "👤 Manual"
            if admin_user:
                backup_type += f" by {admin_user.username or admin_user.first_name}"
            
            message = f"""
✅ *Backup Completed*
━━━━━━━━━━━━━━━
Type: `{backup_type}`
Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
JSON Size: `{format_size(json_path.stat().st_size)}`
GZ Size: `{format_size(gz_path.stat().st_size)}`
"""
            
            # Send message
            self.bot.send_message(
                self.admin_chat_id,
                message,
                parse_mode='MarkdownV2'
            )
            
            # Send backup files
            with open(gz_path, 'rb') as f:
                self.bot.send_document(
                    self.admin_chat_id,
                    f,
                    caption=f"{backup_type} Backup"
                )
                
        except Exception as e:
            logger.error(f"Error sending backup notification: {str(e)}")
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB" 