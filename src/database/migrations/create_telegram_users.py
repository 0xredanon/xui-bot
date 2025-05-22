import mysql.connector
from src.utils.logger import CustomLogger
from src.database.db import Database

logger = CustomLogger("migrations")

def migrate(db: Database):
    """Create telegram_users table if it doesn't exist"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create telegram_users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telegram_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT UNIQUE,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    state VARCHAR(255),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT FALSE,
                    INDEX idx_telegram_id (telegram_id),
                    INDEX idx_username (username),
                    INDEX idx_state (state)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            conn.commit()
            logger.info("Successfully created telegram_users table")
            return True
            
    except Exception as e:
        logger.error(f"Error creating telegram_users table: {str(e)}")
        raise 