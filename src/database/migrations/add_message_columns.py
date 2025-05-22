import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add message-related columns to chat_history table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check which columns already exist
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'chat_history'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Build ALTER TABLE statement only for missing columns
            columns_to_add = []
            if 'message_type' not in existing_columns:
                columns_to_add.append("ADD COLUMN message_type VARCHAR(50)")
            if 'content' not in existing_columns:
                columns_to_add.append("ADD COLUMN content TEXT")
            if 'reply_to_message_id' not in existing_columns:
                columns_to_add.append("ADD COLUMN reply_to_message_id BIGINT")
            if 'forward_from_id' not in existing_columns:
                columns_to_add.append("ADD COLUMN forward_from_id BIGINT")
            if 'edited_at' not in existing_columns:
                columns_to_add.append("ADD COLUMN edited_at DATETIME")
            if 'deleted_at' not in existing_columns:
                columns_to_add.append("ADD COLUMN deleted_at DATETIME")
            
            if columns_to_add:
                alter_sql = f"""
                    ALTER TABLE chat_history
                    {', '.join(columns_to_add)}
                """
                cursor.execute(alter_sql)
                conn.commit()
                logger.info("Added missing message columns to chat_history table")
            else:
                logger.info("All message columns already exist in chat_history table")
            
            logger.info("Migration add_message_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_message_columns: {str(e)}")
        raise 