import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Drop and recreate telegram_users table with all required columns"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Drop telegram_users table if exists
            cursor.execute("""
                DROP TABLE IF EXISTS telegram_users
            """)
            logger.info("Dropped telegram_users table if existed")
            
            # Create telegram_users table with all required columns
            cursor.execute("""
                CREATE TABLE telegram_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT UNIQUE,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    language_code VARCHAR(10) DEFAULT 'fa',
                    created_at DATETIME,
                    last_activity DATETIME,
                    is_admin BOOLEAN DEFAULT FALSE,
                    status VARCHAR(20) DEFAULT 'active'
                )
            """)
            conn.commit()
            logger.info("Created telegram_users table with all required columns")
            logger.info("Migration recreate_telegram_users completed successfully")
    except Exception as e:
        logger.error(f"Error in migration recreate_telegram_users: {str(e)}")
        raise 