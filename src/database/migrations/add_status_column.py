import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add status column to users table"""
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
                logger.info("users table doesn't exist yet, skipping status column addition")
                return
            
            # Check if status column already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'users'
                AND COLUMN_NAME = 'status'
            """)
            if cursor.fetchone()[0] > 0:
                logger.info("status column already exists in users table")
                return
            
            # Add status column if it doesn't exist
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN status VARCHAR(20) DEFAULT 'active'
            """)
            conn.commit()
            logger.info("Added status column to users table")
            logger.info("Migration add_status_column completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_status_column: {str(e)}")
        raise 