import logging
from src.database.db import Database

# Initialize logger
logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add chat-related columns to users table"""
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
                logger.info("users table doesn't exist yet, skipping chat columns addition")
                return
            
            # Check which columns already exist
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'users'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Build ALTER TABLE statement only for missing columns
            columns_to_add = []
            if 'chat_id' not in existing_columns:
                columns_to_add.append("ADD COLUMN chat_id BIGINT DEFAULT NULL")
            if 'last_chat_message' not in existing_columns:
                columns_to_add.append("ADD COLUMN last_chat_message DATETIME DEFAULT NULL")
            if 'chat_message_count' not in existing_columns:
                columns_to_add.append("ADD COLUMN chat_message_count INT DEFAULT 0")
            
            if columns_to_add:
                alter_sql = f"""
                    ALTER TABLE users
                    {', '.join(columns_to_add)}
                """
                cursor.execute(alter_sql)
                conn.commit()
                logger.info("Added missing chat columns to users table")
            else:
                logger.info("All chat columns already exist in users table")
            
            logger.info("Migration add_chat_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_chat_columns: {str(e)}")
        raise 