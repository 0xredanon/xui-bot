import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add missing columns to telegram_users table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if telegram_users table exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                AND table_name = 'telegram_users'
            """)
            if cursor.fetchone()[0] == 0:
                logger.info("telegram_users table doesn't exist yet")
                return

            # Add language_code column if it doesn't exist
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'telegram_users'
                AND COLUMN_NAME = 'language_code'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE telegram_users
                    ADD COLUMN language_code VARCHAR(10) DEFAULT 'fa'
                """)
                logger.info("Added language_code column to telegram_users table")

            # Add last_activity column if it doesn't exist
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'telegram_users'
                AND COLUMN_NAME = 'last_activity'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE telegram_users
                    ADD COLUMN last_activity DATETIME
                """)
                logger.info("Added last_activity column to telegram_users table")

            # Add is_admin column if it doesn't exist
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'telegram_users'
                AND COLUMN_NAME = 'is_admin'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE telegram_users
                    ADD COLUMN is_admin BOOLEAN DEFAULT FALSE
                """)
                logger.info("Added is_admin column to telegram_users table")

            conn.commit()
            logger.info("Migration fix_telegram_users_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration fix_telegram_users_columns: {str(e)}")
        raise 