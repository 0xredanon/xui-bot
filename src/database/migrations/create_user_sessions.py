import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Create user_sessions table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user_sessions table already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                AND table_name = 'user_sessions'
            """)
            if cursor.fetchone()[0] > 0:
                logger.info("user_sessions table already exists")
                return
            
            # Create user_sessions table
            cursor.execute("""
                CREATE TABLE user_sessions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    session_start DATETIME NOT NULL,
                    session_end DATETIME DEFAULT NULL,
                    last_activity DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            conn.commit()
            logger.info("Created user_sessions table")
            logger.info("Migration create_user_sessions completed successfully")
    except Exception as e:
        logger.error(f"Error in migration create_user_sessions: {str(e)}")
        raise 