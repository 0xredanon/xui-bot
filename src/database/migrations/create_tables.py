import mysql.connector
from src.utils.logger import CustomLogger

logger = CustomLogger("migrations")

def migrate():
    """Create initial database tables"""
    try:
        # Connect to database
        conn = mysql.connector.connect(
            host="localhost",
            user="xui_bot",
            password="XuiBot@2024#Secure",
            database="xui_bot"
        )
        cursor = conn.cursor()

        # Create telegram_users table first
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                email VARCHAR(255),
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                state VARCHAR(50) DEFAULT NULL
            )
        """)
        logger.info("Created telegram_users table")

        # Create chat_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                message_id BIGINT,
                chat_id BIGINT,
                message_text TEXT,
                response_text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES telegram_users(telegram_id) ON DELETE CASCADE
            )
        """)
        logger.info("Created chat_history table")

        # Create user_stats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT,
                total_messages INT DEFAULT 0,
                total_responses INT DEFAULT 0,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES telegram_users(telegram_id) ON DELETE CASCADE
            )
        """)
        logger.info("Created user_stats table")

        conn.commit()
        logger.info("Migration create_tables completed successfully")

    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        raise
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close() 