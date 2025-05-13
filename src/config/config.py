import os
from typing import Dict, Any

# X-UI Configuration
X_UI_CONFIG: Dict[str, Any] = {
    "URL": "http://iran.olympusm.ir:7886",
    "USERNAME": "mahdiaria",
    "PASSWORD": "mahdiaria9531",
    "DEFAULT_INBOUND_ID": 1
}

# Telegram Configuration
TELEGRAM_CONFIG: Dict[str, Any] = {
    "BOT_TOKEN": "7131562124:AAE_IRcN0UJHXSrChUCfD0e7TZvLg_7s5mk",
    "ADMIN_IDS": []  # Add admin Telegram IDs here
}

# File paths
FILE_PATHS: Dict[str, str] = {
    "USER_DATA_DIR": "userid",
    "USER_DATA_FILE": os.path.join("userid", "usersID.txt"),
    "BACKUP_DIR": "backups"
}

# Create necessary directories
for directory in [FILE_PATHS["USER_DATA_DIR"], FILE_PATHS["BACKUP_DIR"]]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Traffic limits (in GB)
TRAFFIC_LIMITS: Dict[str, int] = {
    "DEFAULT": 0,  # Unlimited
    "MIN": 1,
    "MAX": 1000
}

# Time limits (in days)
TIME_LIMITS: Dict[str, int] = {
    "DEFAULT": 30,
    "MIN": 1,
    "MAX": 365
}

# IP limits
IP_LIMITS: Dict[str, int] = {
    "DEFAULT": 0,  # Unlimited
    "MIN": 0,
    "MAX": 100
} 