import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Create user_activities table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user_activities table already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                AND table_name = 'user_activities'
            """)
            if cursor.fetchone()[0] > 0:
                logger.info("user_activities table already exists")
                return
            
            # Create user_activities table
            cursor.execute("""
                CREATE TABLE user_activities (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    activity_type VARCHAR(50) NOT NULL,
                    target_uuid VARCHAR(36) DEFAULT NULL,
                    details JSON DEFAULT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            conn.commit()
            logger.info("Created user_activities table")
            logger.info("Migration create_user_activities completed successfully")
    except Exception as e:
        logger.error(f"Error in migration create_user_activities: {str(e)}")
        raise 