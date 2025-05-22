import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Drop and recreate user_activities table with correct foreign key"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Drop user_activities table if exists
            cursor.execute("""
                DROP TABLE IF EXISTS user_activities
            """)
            logger.info("Dropped user_activities table if existed")
            
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
            logger.info("Created user_activities table with correct foreign key")
            logger.info("Migration recreate_user_activities completed successfully")
    except Exception as e:
        logger.error(f"Error in migration recreate_user_activities: {str(e)}")
        raise 