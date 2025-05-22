import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Fix foreign key constraints in the database"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Drop existing foreign keys if they exist
            cursor.execute("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'chat_history'
                AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            """)
            for (constraint_name,) in cursor.fetchall():
                cursor.execute(f"ALTER TABLE chat_history DROP FOREIGN KEY {constraint_name}")
            
            # Add foreign key constraints
            cursor.execute("""
                ALTER TABLE chat_history
                ADD CONSTRAINT chat_history_ibfk_1
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                ON DELETE CASCADE
            """)
            
            conn.commit()
            logger.info("Migration fix_foreign_keys completed successfully")
    except Exception as e:
        logger.error(f"Error in migration fix_foreign_keys: {str(e)}")
        raise 