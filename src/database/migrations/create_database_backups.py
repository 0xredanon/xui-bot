import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

def migrate(db: Database):
    """Create database_backups table"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if database_backups table already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                AND table_name = 'database_backups'
            """)
            if cursor.fetchone()[0] > 0:
                logger.info("database_backups table already exists")
                return
            
            # Create database_backups table
            cursor.execute("""
                CREATE TABLE database_backups (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    size_bytes BIGINT,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    error_message TEXT,
                    is_automatic BOOLEAN DEFAULT FALSE,
                    created_by_id BIGINT,
                    file_path VARCHAR(255),
                    FOREIGN KEY (created_by_id) REFERENCES telegram_users(telegram_id)
                )
            """)
            conn.commit()
            logger.info("Created database_backups table")
            logger.info("Migration create_database_backups completed successfully")
    except Exception as e:
        logger.error(f"Error in migration create_database_backups: {str(e)}")
        raise