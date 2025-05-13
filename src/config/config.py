import os
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for the bot"""
    
    # Base paths
    BASE_DIR = Path(__file__).parent.parent.parent
    DATA_DIR = BASE_DIR / 'data'
    LOGS_DIR = BASE_DIR / 'logs'
    BACKUP_DIR = BASE_DIR / 'backups'
    
    # Create required directories
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Database
    DATABASE_PATH = DATA_DIR / 'xui_bot.db'
    
    # Telegram Bot
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set")
    
    # Admin configuration
    ADMIN_IDS = [int(id_) for id_ in os.getenv('ADMIN_IDS', '').split(',') if id_.strip()]
    if not ADMIN_IDS:
        raise ValueError("ADMIN_IDS environment variable is not set")
    
    # X-UI Panel
    PANEL_URL = os.getenv('PANEL_URL')
    PANEL_USERNAME = os.getenv('PANEL_USERNAME')
    PANEL_PASSWORD = os.getenv('PANEL_PASSWORD')
    INBOUND_ID = int(os.getenv('INBOUND_ID', '1'))
    
    if not all([PANEL_URL, PANEL_USERNAME, PANEL_PASSWORD]):
        raise ValueError("X-UI panel configuration is incomplete")
    
    # Timezone
    TIMEZONE = os.getenv('TZ', 'Asia/Tehran')
    
    # Logging
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = LOGS_DIR / 'bot.log'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Backup
    BACKUP_SCHEDULE = os.getenv('BACKUP_SCHEDULE', '0 0 * * *')  # Daily at midnight
    MAX_BACKUPS = int(os.getenv('MAX_BACKUPS', '7'))  # Keep last 7 backups
    
    # API Configuration
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', '30'))  # 30 seconds timeout
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    
    # Security
    SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', '3600'))  # 1 hour
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', '3'))
    RATE_LIMIT = int(os.getenv('RATE_LIMIT', '30'))  # Requests per minute
    
    # User Defaults
    DEFAULT_TRAFFIC_LIMIT = int(os.getenv('DEFAULT_TRAFFIC_LIMIT', '50'))  # GB
    DEFAULT_DURATION = int(os.getenv('DEFAULT_DURATION', '30'))  # Days
    
    # Feature Flags
    ENABLE_BACKUP = os.getenv('ENABLE_BACKUP', 'true').lower() == 'true'
    ENABLE_MONITORING = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
    ENABLE_NOTIFICATIONS = os.getenv('ENABLE_NOTIFICATIONS', 'true').lower() == 'true'
    
    @classmethod
    def get_api_config(cls) -> Dict:
        """Get API configuration"""
        return {
            'url': cls.PANEL_URL,
            'username': cls.PANEL_USERNAME,
            'password': cls.PANEL_PASSWORD,
            'timeout': cls.API_TIMEOUT,
            'max_retries': cls.MAX_RETRIES
        }
    
    @classmethod
    def get_backup_config(cls) -> Dict:
        """Get backup configuration"""
        return {
            'schedule': cls.BACKUP_SCHEDULE,
            'max_backups': cls.MAX_BACKUPS,
            'backup_dir': str(cls.BACKUP_DIR),
            'enabled': cls.ENABLE_BACKUP
        }
    
    @classmethod
    def get_security_config(cls) -> Dict:
        """Get security configuration"""
        return {
            'session_timeout': cls.SESSION_TIMEOUT,
            'max_login_attempts': cls.MAX_LOGIN_ATTEMPTS,
            'rate_limit': cls.RATE_LIMIT
        }
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in cls.ADMIN_IDS 