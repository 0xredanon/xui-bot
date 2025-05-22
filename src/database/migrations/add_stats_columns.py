import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add statistics-related columns to users table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check which columns already exist
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'users'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Build ALTER TABLE statement only for missing columns
            columns_to_add = []
            if 'total_messages' not in existing_columns:
                columns_to_add.append("ADD COLUMN total_messages INT DEFAULT 0")
            if 'total_responses' not in existing_columns:
                columns_to_add.append("ADD COLUMN total_responses INT DEFAULT 0")
            if 'avg_response_time' not in existing_columns:
                columns_to_add.append("ADD COLUMN avg_response_time FLOAT DEFAULT 0.0")
            if 'last_activity' not in existing_columns:
                columns_to_add.append("ADD COLUMN last_activity DATETIME")
            
            if columns_to_add:
                alter_sql = f"""
                    ALTER TABLE users
                    {', '.join(columns_to_add)}
                """
                cursor.execute(alter_sql)
                conn.commit()
                logger.info("Added missing stats columns to users table")
            else:
                logger.info("All stats columns already exist in users table")
            
            logger.info("Migration add_stats_columns completed successfully")
    except Exception as e:
        logger.error(f"Error in migration add_stats_columns: {str(e)}")
        raise 