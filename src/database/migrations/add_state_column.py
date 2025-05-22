from sqlalchemy import String
from ...models.base import Base
from ...utils.logger import CustomLogger

logger = CustomLogger("migrations")

def migrate(db):
    """Add state column to telegram_users table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if column exists
            cursor.execute("SHOW COLUMNS FROM telegram_users LIKE 'state'")
            if cursor.fetchone():
                logger.info("State column already exists in telegram_users table")
                return
                
            # Add state column if it doesn't exist
            cursor.execute("""
                ALTER TABLE telegram_users
                ADD COLUMN state VARCHAR(255) DEFAULT NULL
            """)
            logger.info("Added state column to telegram_users table")
            
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        raise 