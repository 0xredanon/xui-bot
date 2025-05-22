import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add language_code column to telegram_users table if it does not exist"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if telegram_users table exists
            cursor.execute("SHOW TABLES LIKE 'telegram_users'")
            if not cursor.fetchone():
                logger.info("telegram_users table doesn't exist yet, skipping language_code column addition")
                return

            # Check if language_code column already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'telegram_users'
                AND COLUMN_NAME = 'language_code'
            """)
            if cursor.fetchone()[0] > 0:
                logger.info("language_code column already exists")
                return

            # Add language_code column
            cursor.execute("""
                ALTER TABLE telegram_users
                ADD COLUMN language_code VARCHAR(10) DEFAULT NULL
            """)
            logger.info("Added language_code column to telegram_users table")

            conn.commit()
            logger.info("Migration add_language_code_column completed successfully")

    except Exception as e:
        logger.error(f"Error adding language_code column: {str(e)}")
        raise 