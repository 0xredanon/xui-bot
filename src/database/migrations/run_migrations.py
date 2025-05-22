from src.database.migrations.add_state_column import migrate as add_state_column
from src.database.migrations.add_chat_columns import migrate as add_chat_columns
from src.database.migrations.add_message_columns import migrate as add_message_columns
from src.database.migrations.add_response_columns import migrate as add_response_columns
from src.database.migrations.add_stats_columns import migrate as add_stats_columns
from src.database.migrations.add_user_activity_columns import migrate as add_user_activity_columns
from src.database.migrations.fix_foreign_keys import migrate as fix_foreign_keys
from src.database.db import Database
import logging
import importlib
import os
import sys
from pathlib import Path

# Initialize logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("migrations")

def run_migrations():
    """Run all database migrations in order"""
    try:
        db = Database()
        migrations = [
            add_state_column,
            add_chat_columns,
            add_message_columns,
            add_response_columns,
            add_stats_columns,
            add_user_activity_columns,
            fix_foreign_keys
        ]
        
        successful = 0
        failed = 0
        
        for migration in migrations:
            try:
                migration(db)
                successful += 1
                logger.info(f"Migration {migration.__name__} completed successfully")
            except Exception as e:
                logger.error(f"Migration failed: {str(e)}")
                failed += 1
        
        logger.info(f"Migration complete: {successful} successful, {failed} failed")
        return failed == 0
        
    except Exception as e:
        logger.error(f"Error running migrations: {str(e)}")
        return False

if __name__ == "__main__":
    if run_migrations():
        print("All migrations completed successfully")
        sys.exit(0)
    else:
        print("Some migrations failed")
        sys.exit(1) 