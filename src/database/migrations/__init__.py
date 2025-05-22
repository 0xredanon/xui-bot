# Migrations package 
from .create_tables import migrate as create_tables
from .create_telegram_users import migrate as create_telegram_users
from .create_user_activities import migrate as create_user_activities
from .add_user_columns import migrate as add_user_columns
from .add_state_column import migrate as add_state_column
from .fix_foreign_keys import migrate as fix_foreign_keys
from .fix_telegram_users_columns import migrate as fix_telegram_users_columns
from .add_user_activity_columns import migrate as add_user_activity_columns
from .add_response_columns import migrate as add_response_columns
from .add_message_columns import migrate as add_message_columns
from .add_stats_columns import migrate as add_stats_columns
from .add_status_column import migrate as add_status_column
from .add_chat_columns import migrate as add_chat_columns
from .add_data_usage_column import migrate as add_data_usage_column
from .recreate_user_activities import migrate as recreate_user_activities
from .recreate_telegram_users import migrate as recreate_telegram_users
from .add_language_code_column import migrate as add_language_code_column
from .add_email_column import migrate as add_email_column
from .create_database_backups import migrate as create_database_backups

import logging
from src.database.db import Database

logger = logging.getLogger(__name__)

# List of migrations in order
migrations = [
    create_tables,
    create_telegram_users,
    create_user_activities,
    add_user_columns,
    add_state_column,
    fix_foreign_keys,
    fix_telegram_users_columns,
    add_user_activity_columns,
    add_response_columns,
    add_message_columns,
    add_stats_columns,
    add_status_column,
    add_chat_columns,
    add_data_usage_column,
    recreate_user_activities,
    recreate_telegram_users,
    add_language_code_column,
    add_email_column,
    create_database_backups
]

def run_migrations():
    """Run all migrations in order"""
    db = Database()
    successful = 0
    failed = 0
    
    for migration in migrations:
        try:
            # Run the migration with the db instance
            migration(db)
            successful += 1
            logger.info(f"Migration {migration.__name__} completed successfully")
        except Exception as e:
            failed += 1
            logger.error(f"Migration failed: {str(e)}")
            # Don't raise the exception, continue with next migration
            continue
    
    logger.info(f"Migration complete: {successful} successful, {failed} failed")
    return successful > 0 and failed == 0

if __name__ == "__main__":
    # Run migrations when this file is executed directly
    run_migrations() 