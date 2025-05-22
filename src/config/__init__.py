import os
from pathlib import Path

# Define the base directory (project root)
BASE_DIR = Path(__file__).parent.parent.parent

# Define backup directory
BACKUP_DIR = os.path.join(BASE_DIR, 'backups') 