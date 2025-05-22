import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Add email column to telegram_users table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Add email column
            cursor.execute("""
                ALTER TABLE telegram_users
                ADD COLUMN email VARCHAR(255) DEFAULT NULL
            """)
            logger.info("Added email column to telegram_users table")

            conn.commit()
            logger.info("Migration add_email_column completed successfully")

    except Exception as e:
        logger.error(f"Error adding email column: {str(e)}")
        raise 