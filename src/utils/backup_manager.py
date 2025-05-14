import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import schedule
import threading
import time
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from telebot import TeleBot
import gzip
import shutil
import re
import traceback

from ..models.models import DatabaseBackup, BackupStatus, TelegramUser
from ..models.base import SessionLocal, engine
from ..utils.logger import CustomLogger
from ..utils.datetime_encoder import DateTimeEncoder

logger = CustomLogger("BackupManager")

class BackupManager:
    def __init__(self, bot: TeleBot, admin_chat_id: int, backup_dir: str = "backups"):
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.backup_dir = Path(backup_dir)
        self.is_backup_enabled = True
        self.backup_thread = None
        
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
            schedule.every().hour.at(":00").do(self.create_automated_backup)
            
            while self.is_backup_enabled:
                schedule.run_pending()
                time.sleep(60)  # Sleep for 1 minute
        
        self.backup_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.backup_thread.start()
        logger.info("Backup scheduler started")
    
    def stop_scheduler(self):
        """Stop the backup scheduler"""
        self.is_backup_enabled = False
        if self.backup_thread and self.backup_thread.is_alive():
            self.backup_thread.join(timeout=2)
        logger.info("Backup scheduler stopped")
    
    def create_backup(self, is_automated: bool = False, admin_user: TelegramUser = None) -> bool:
        """Create a backup of the database"""
        try:
            # Generate timestamp and filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_type = "auto" if is_automated else "manual"
            version = "v1.0"  # You can update this based on your versioning
            
            base_name = f"xui_bot_backup_{version}_{timestamp}"
            json_path = self.backup_dir / f"{base_name}.json"
            gz_path = self.backup_dir / f"{base_name}.json.gz"
            
            # Create backup data
            backup_data = self._create_backup_data()
            if not backup_data:
                logger.error("Failed to create backup data")
                return False
            
            # Save uncompressed backup
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
            logger.info(f"Backup saved: {json_path}")
            
            # Create compressed backup
            with open(json_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"Compressed backup saved: {gz_path}")
            
            # Record backup in database
            with SessionLocal() as db:
                backup_record = DatabaseBackup(
                    filename=gz_path.name,
                    status=BackupStatus.COMPLETED,
                    size_bytes=gz_path.stat().st_size,
                    completed_at=datetime.utcnow(),
                    is_automatic=is_automated,
                    created_by_id=admin_user.id if admin_user else None,
                    file_path=str(gz_path)
                )
                db.add(backup_record)
                db.commit()
            
            # Clean up old backups
            self._cleanup_old_backups()
            
            # Send notification to admin
            self._send_backup_notification(json_path, gz_path, is_automated, admin_user)
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to create backup: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            
            try:
                self.bot.send_message(
                    self.admin_chat_id,
                    f"❌ {error_msg}"
                )
            except:
                pass
                
            return False
    
    def create_automated_backup(self) -> bool:
        """Create automated backup"""
        return self.create_backup(is_automated=True)
    
    def create_manual_backup(self, admin_user: TelegramUser) -> bool:
        """Create manual backup initiated by admin"""
        return self.create_backup(is_automated=False, admin_user=admin_user)
    
    def _create_backup_data(self) -> Optional[Dict[str, Any]]:
        """Create backup of database tables"""
        try:
            with SessionLocal() as db:
                backup_data = {
                    'metadata': {
                        'timestamp': datetime.now().isoformat(),
                        'version': '1.0',
                        'tables': []
                    },
                    'data': {}
                }
                
                # Get all tables
                tables = engine.table_names()
                backup_data['metadata']['tables'] = tables
                
                # Backup each table
                for table in tables:
                    result = db.execute(f"SELECT * FROM {table}")
                    columns = result.keys()
                    rows = [dict(row) for row in result.fetchall()]
                    
                    backup_data['data'][table] = {
                        'columns': columns,
                        'rows': rows
                    }
                
                return backup_data
                
        except Exception as e:
            logger.error(f"Error creating backup data: {str(e)}\n{traceback.format_exc()}")
            return None
    
    def _cleanup_old_backups(self, keep_days: int = 7):
        """Clean up old backup files"""
        try:
            # Get current time
            now = datetime.now()
            
            # List all backup files
            backup_files = []
            for ext in ['*.json', '*.json.gz']:
                backup_files.extend(self.backup_dir.glob(ext))
            
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
JSON Size: `{self._format_size(json_path.stat().st_size)}`
GZ Size: `{self._format_size(gz_path.stat().st_size)}`
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