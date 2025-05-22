import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add user activity columns to chat_history table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, ensure all users from chat_history exist in users table
            cursor.execute("""
                INSERT IGNORE INTO users (telegram_id, username, first_name, last_name, created_at, last_activity)
                SELECT DISTINCT user_id, 
                       (SELECT username FROM telegram_users WHERE telegram_id = chat_history.user_id LIMIT 1),
                       (SELECT first_name FROM telegram_users WHERE telegram_id = chat_history.user_id LIMIT 1),
                       (SELECT last_name FROM telegram_users WHERE telegram_id = chat_history.user_id LIMIT 1),
                       MIN(created_at),
                       MAX(created_at)
                FROM chat_history
                WHERE user_id IS NOT NULL
                GROUP BY user_id
            """)
            
            # Check which columns already exist
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'chat_history'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Build ALTER TABLE statement only for missing columns
            columns_to_add = []
            if 'user_id' not in existing_columns:
                columns_to_add.append("ADD COLUMN user_id BIGINT")
            if 'username' not in existing_columns:
                columns_to_add.append("ADD COLUMN username VARCHAR(255)")
            if 'first_name' not in existing_columns:
                columns_to_add.append("ADD COLUMN first_name VARCHAR(255)")
            if 'last_name' not in existing_columns:
                columns_to_add.append("ADD COLUMN last_name VARCHAR(255)")
            if 'is_bot' not in existing_columns:
                columns_to_add.append("ADD COLUMN is_bot BOOLEAN DEFAULT FALSE")
            if 'language_code' not in existing_columns:
                columns_to_add.append("ADD COLUMN language_code VARCHAR(10)")
            
            if columns_to_add:
                alter_sql = f"""
                    ALTER TABLE chat_history
                    {', '.join(columns_to_add)}
                """
                cursor.execute(alter_sql)
                conn.commit()
                logger.info("Added missing user activity columns to chat_history table")
            else:
                logger.info("All user activity columns already exist in chat_history table")
            
            logger.info("Migration add_user_activity_columns completed successfully")
            
    except Exception as e:
        logger.error(f"Error in migration add_user_activity_columns: {str(e)}")
        raise 