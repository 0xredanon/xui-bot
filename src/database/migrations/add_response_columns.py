import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add response-related columns to chat_history table"""
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
            if 'response_time' not in existing_columns:
                columns_to_add.append("ADD COLUMN response_time FLOAT")
            if 'response_type' not in existing_columns:
                columns_to_add.append("ADD COLUMN response_type VARCHAR(50)")
            if 'response_content' not in existing_columns:
                columns_to_add.append("ADD COLUMN response_content TEXT")
            if 'response_error' not in existing_columns:
                columns_to_add.append("ADD COLUMN response_error TEXT")
            
            if columns_to_add:
                alter_sql = f"""
                    ALTER TABLE chat_history
                    {', '.join(columns_to_add)}
                """
                cursor.execute(alter_sql)
                conn.commit()
                logger.info("Added missing response columns to chat_history table")
            else:
                logger.info("All response columns already exist in chat_history table")
            
            logger.info("Migration add_response_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_response_columns: {str(e)}")
        raise 