import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add status and data_usage columns to users table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if users table exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                AND table_name = 'users'
            """)
            if cursor.fetchone()[0] == 0:
                logger.info("users table doesn't exist yet, skipping column additions")
                return

            # Add status column if it doesn't exist
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'users'
                AND COLUMN_NAME = 'status'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN status VARCHAR(50) DEFAULT 'active'
                """)
                logger.info("Added status column to users table")

            # Add data_usage column if it doesn't exist
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'users'
                AND COLUMN_NAME = 'data_usage'
            """)
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN data_usage BIGINT DEFAULT 0
                """)
                logger.info("Added data_usage column to users table")

            conn.commit()
            logger.info("Migration add_user_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_user_columns: {str(e)}")
        raise 