import mysql.connector
from mysql.connector import Error as MySQLError
from datetime import datetime
import json
from typing import Dict, List, Optional, Union
from pathlib import Path
import time
import traceback
from contextlib import contextmanager

from src.utils.logger import CustomLogger
from src.utils.exceptions import *
from proj import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, ADMIN_IDS

# Initialize custom logger
logger = CustomLogger("Database")

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class Database:
    def __init__(self, db_name: str = "xui_bot"):
        try:
            self.db_config = {
                'host': DB_HOST,
                'user': DB_USER,
                'password': DB_PASSWORD,
                'database': DB_NAME
            }
            
            # Create database if not exists
            self._create_database()
            self._init_db()
            logger.info(f"Database initialized successfully: {db_name}")
        except Exception as e:
            logger.critical(f"Failed to initialize database: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError("Failed to initialize database")

    def _create_database(self):
        """Create database if it doesn't exist"""
        try:
            conn = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_config['database']}")
            conn.close()
        except MySQLError as e:
            logger.error(f"Error creating database: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to create database: {str(e)}")

    def _init_db(self):
        """Initialize database tables"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        telegram_id BIGINT UNIQUE,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        email VARCHAR(255) UNIQUE,
                        language_code VARCHAR(10) DEFAULT 'fa',
                        created_at DATETIME,
                        last_activity DATETIME,
                        status VARCHAR(20) DEFAULT 'active',
                        traffic_limit BIGINT DEFAULT 0,
                        total_usage BIGINT DEFAULT 0,
                        expiry_date DATETIME,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_admin BOOLEAN DEFAULT FALSE,
                        state VARCHAR(50),
                        chat_id BIGINT,
                        last_chat_message DATETIME,
                        chat_message_count INT DEFAULT 0,
                        total_sessions INT DEFAULT 0,
                        last_session_at DATETIME,
                        active_sessions INT DEFAULT 0,
                        session_count_24h INT DEFAULT 0
                    )
                """)
                
                # Create telegram_users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        telegram_id BIGINT UNIQUE,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        language_code VARCHAR(10) DEFAULT 'fa',
                        created_at DATETIME,
                        last_activity DATETIME,
                        is_admin BOOLEAN DEFAULT FALSE,
                        status VARCHAR(20) DEFAULT 'active'
                    )
                """)
                
                # Create bot_status table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_status (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        is_enabled BOOLEAN DEFAULT TRUE,
                        last_updated DATETIME,
                        updated_by INT,
                        reason TEXT,
                        FOREIGN KEY (updated_by) REFERENCES users(telegram_id)
                    )
                """)
                
                # Create chat_history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT,
                        message_id BIGINT,
                        chat_id BIGINT,
                        message_type VARCHAR(50),
                        content TEXT,
                        reply_to_message_id BIGINT,
                        forward_from_id BIGINT,
                        timestamp DATETIME,
                        edited_at DATETIME,
                        deleted_at DATETIME,
                        is_command BOOLEAN DEFAULT FALSE,
                        command_name VARCHAR(50),
                        command_args TEXT,
                        bot_response TEXT,
                        response_time INT,
                        status VARCHAR(20) DEFAULT 'sent',
                        FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Create user_activity table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_activity (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT,
                        activity_type VARCHAR(50),
                        timestamp DATETIME,
                        details JSON,
                        FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Create logs table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME,
                        level VARCHAR(20),
                        event_type VARCHAR(50),
                        user_id BIGINT,
                        message TEXT,
                        details JSON,
                        FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Create bot_commands table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_commands (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        command_name VARCHAR(50),
                        user_id BIGINT,
                        args TEXT,
                        result TEXT,
                        execution_time INT,
                        timestamp DATETIME,
                        status VARCHAR(20),
                        error_message TEXT,
                        session_id VARCHAR(50),
                        FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Create shared_links table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS shared_links (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT,
                        link_type VARCHAR(50),
                        link_url TEXT,
                        title VARCHAR(255),
                        description TEXT,
                        message_id BIGINT,
                        chat_id BIGINT,
                        created_at DATETIME,
                        expiry_date DATETIME,
                        FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                conn.commit()
                logger.info("Database tables created/verified successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to initialize database: {str(e)}")

    @contextmanager
    def get_connection(self):
        """Get a database connection with automatic closing"""
        conn = None
        try:
            conn = mysql.connector.connect(**self.db_config)
            yield conn
        except MySQLError as e:
            error_msg = str(e)
            if "Access denied" in error_msg:
                logger.error(f"Database access denied. Please check credentials: {error_msg}")
            elif "Unknown column" in error_msg:
                logger.error(f"Database schema error: {error_msg}")
            else:
                logger.error(f"Database connection error: {error_msg}\n{traceback.format_exc()}")
            
            if conn and conn.is_connected():
                conn.close()
            raise DatabaseError(f"Database error: {error_msg}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def _execute_with_retry(self, query: str, params=None, max_retries: int = 3):
        """Execute a database query with retry logic and proper error handling"""
        last_error = None
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                    conn.commit()
                    return cursor
            except MySQLError as e:
                last_error = e
                logger.warning(
                    f"Database operation attempt {attempt + 1} failed: {str(e)}\n"
                    f"Query: {query}\nParams: {params}"
                )
                if attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                continue
        
        logger.error(
            f"Database operation failed after {max_retries} attempts: {str(last_error)}\n"
            f"Query: {query}\nParams: {params}\n{traceback.format_exc()}"
        )
        raise DatabaseError(f"Database operation failed after {max_retries} attempts")

    def add_user(self, email: str, traffic_limit: int, expiry_date: str, telegram_info: Dict = None) -> bool:
        """Add a new user with proper validation and error handling"""
        try:
            # Validate input parameters
            if not email or not isinstance(email, str):
                raise ValidationError("Invalid email address")
            if not isinstance(traffic_limit, int) or traffic_limit <= 0:
                raise ValidationError("Invalid traffic limit")
            if not expiry_date or not isinstance(expiry_date, str):
                raise ValidationError("Invalid expiry date")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user already exists
                cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    logger.warning(f"Attempted to add existing user: {email}")
                    return False
                
                # Prepare user data
                user_data = {
                    'email': email,
                    'traffic_limit': traffic_limit,
                    'expiry_date': expiry_date,
                    'created_at': datetime.now().isoformat(),
                    'status': 'active',
                    'total_usage': 0
                }
                
                # Add telegram info if provided
                if telegram_info:
                    if not isinstance(telegram_info, dict):
                        raise ValidationError("Invalid telegram info format")
                    user_data.update({
                        'telegram_id': telegram_info.get('user_id'),
                        'username': telegram_info.get('username'),
                        'first_name': telegram_info.get('first_name'),
                        'last_name': telegram_info.get('last_name'),
                        'language_code': telegram_info.get('language_code')
                    })
                
                # Build query dynamically
                fields = ', '.join(user_data.keys())
                placeholders = ', '.join(['%s'] * len(user_data))
                query = f'INSERT INTO users ({fields}) VALUES ({placeholders})'
                
                cursor.execute(query, list(user_data.values()))
                conn.commit()
                
                logger.info(f"User added successfully: {email}")
                return True
                
        except MySQLError as e:
            logger.error(f"Database integrity error adding user {email}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error adding user {email}: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to add user: {str(e)}")

    def update_user(self, email: str, **kwargs) -> bool:
        """Update user information with proper validation and error handling"""
        try:
            # Validate email
            if not email or not isinstance(email, str):
                raise ValidationError("Invalid email address")
            
            # Validate update data
            valid_fields = {
                'traffic_limit', 'expiry_date', 'status', 'total_usage',
                'telegram_id', 'username', 'first_name', 'last_name',
                'language_code', 'inbound_id'
            }
            
            invalid_fields = set(kwargs.keys()) - valid_fields
            if invalid_fields:
                raise ValidationError(f"Invalid update fields: {', '.join(invalid_fields)}")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
                if not cursor.fetchone():
                    logger.warning(f"Attempted to update non-existent user: {email}")
                    return False
                
                updates = []
                values = []
                
                # Add update timestamp
                kwargs['last_modified'] = datetime.now().isoformat()
                
                for key, value in kwargs.items():
                    updates.append(f"{key} = %s")
                    values.append(value)
                
                values.append(email)
                query = f'''
                    UPDATE users 
                    SET {", ".join(updates)}
                    WHERE email = %s
                '''
                
                cursor.execute(query, values)
                conn.commit()
                
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"User {email} updated successfully")
                else:
                    logger.warning(f"No changes made for user {email}")
                return success
                
        except MySQLError as e:
            logger.error(f"Database error updating user {email}: {str(e)}\n{traceback.format_exc()}")
            return False
        except Exception as e:
            logger.error(f"Error updating user {email}: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to update user: {str(e)}")

    def log_event(self, level: str, event_type: str, user_id: Optional[int], message: str, details: dict = None) -> bool:
        """Log event with proper error handling"""
        try:
            # Prepare event details
            event_details = {
                'message': message,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'additional_info': details or {}
            }
            
            # Try to get user context if available, but don't fail if not found
            # Skip user context lookup during initialization (when user_id is None)
            if user_id is not None:
                try:
                    user_context = self.get_user_info(user_id, by_telegram=True)
                    if user_context:
                        event_details['user_context'] = user_context
                except Exception as e:
                    logger.debug(f"Could not get user context for event logging: {str(e)}")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO logs (
                        level, event_type, user_id, message, details, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                """, (
                    level,
                    event_type,
                    user_id,
                    message,
                    json.dumps(event_details, cls=DateTimeEncoder)
                ))
                
                conn.commit()
                logger.debug(f"Event logged successfully: {event_type}")
                return True
                
        except Exception as e:
            logger.error(f"Error logging event: {str(e)}")
            return False

    def log_admin_action(self, admin_id: int, action_type: str, 
                        target_user: str, details: Dict = None,
                        ip_address: str = None, status: str = 'success'):
        """Enhanced admin action logging with proper error handling"""
        try:
            # Validate input parameters
            if not isinstance(admin_id, int) or admin_id <= 0:
                raise ValidationError("Invalid admin ID")
            if not action_type or not isinstance(action_type, str):
                raise ValidationError("Invalid action type")
            if status not in {'success', 'failed', 'pending'}:
                raise ValidationError("Invalid status")
            
            current_time = datetime.now().isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO admin_actions (
                        admin_id, action_type, target_user, 
                        timestamp, details, ip_address, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    admin_id,
                    action_type,
                    target_user,
                    current_time,
                    json.dumps(details, cls=DateTimeEncoder) if details else None,
                    ip_address,
                    status
                ))
                conn.commit()
                
                logger.info(f"Admin action logged successfully: {action_type} by {admin_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error logging admin action: {str(e)}\n{traceback.format_exc()}")
            # Don't raise here to prevent logging failures from affecting main functionality
            return False

    def get_user_info(self, identifier: Union[str, int], by_telegram: bool = False) -> Optional[Dict]:
        """Get user information with proper error handling"""
        try:
            # Handle None case gracefully
            if identifier is None:
                logger.debug("Identifier is None, returning None")
                return None
                
            if by_telegram:
                try:
                    identifier = int(identifier)
                except (ValueError, TypeError):
                    logger.debug(f"Invalid Telegram ID format: {identifier}")
                    return None
            elif not isinstance(identifier, str):
                logger.debug(f"Invalid email format: {identifier}")
                return None
                
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if by_telegram:
                    query = "SELECT * FROM users WHERE telegram_id = %s"
                else:
                    query = "SELECT * FROM users WHERE email = %s"
                
                cursor.execute(query, (identifier,))
                row = cursor.fetchone()
                
                if not row:
                    logger.debug(f"User not found: {identifier}")
                    return None
                
                # Get column names
                columns = [description[0] for description in cursor.description]
                user_data = dict(zip(columns, row))
                
                # Get additional user statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as session_count,
                        SUM(data_usage) as total_usage,
                        MAX(connected_at) as last_connection
                    FROM user_sessions 
                    WHERE email = %s
                """, (user_data['email'],))
                
                stats = cursor.fetchone()
                if stats:
                    user_data.update({
                        'session_count': stats[0],
                        'total_usage': stats[1] or 0,
                        'last_connection': stats[2]
                    })
                
                logger.debug(f"User info retrieved successfully: {identifier}")
                return user_data
                
        except MySQLError as e:
            logger.error(f"Database error getting user info: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get user info: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}\n{traceback.format_exc()}")
            return None

    def record_session(self, email: str, ip_address: str, device_info: str = None,
                      location: str = None, connection_type: str = None,
                      data_usage: int = 0):
        """Record user session with proper error handling"""
        try:
            # Validate input parameters
            if not email or not isinstance(email, str):
                raise ValidationError("Invalid email")
            if not ip_address or not isinstance(ip_address, str):
                raise ValidationError("Invalid IP address")
            if data_usage < 0:
                raise ValidationError("Data usage cannot be negative")
            
            current_time = datetime.now().isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Verify user exists
                cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
                if not cursor.fetchone():
                    logger.warning(f"Attempted to record session for non-existent user: {email}")
                    raise ValidationError("User does not exist")
                
                # Record session
                cursor.execute('''
                    INSERT INTO user_sessions (
                        email, ip_address, connected_at, data_usage,
                        device_info, location, connection_type
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    email, ip_address, current_time, data_usage,
                    device_info, location, connection_type
                ))
                
                # Update user's total usage
                cursor.execute('''
                    UPDATE users 
                    SET total_usage = total_usage + %s,
                        last_modified = %s
                    WHERE email = %s
                ''', (data_usage, current_time, email))
                
                conn.commit()
                logger.info(f"Session recorded successfully for user {email}")
                return True
                
        except MySQLError as e:
            logger.error(f"Database error recording session: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to record session: {str(e)}")
        except Exception as e:
            logger.error(f"Error recording session: {str(e)}\n{traceback.format_exc()}")
            raise

    def get_user_activity(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get user activity history with proper error handling"""
        try:
            # Validate input parameters
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValidationError("Invalid user ID")
            if not isinstance(limit, int) or limit <= 0:
                raise ValidationError("Invalid limit")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        activity_type,
                        timestamp,
                        details,
                        ip_address
                    FROM user_activity
                    WHERE user_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                ''', (user_id, min(limit, 100)))  # Cap at 100 records
                
                activities = []
                for row in cursor.fetchall():
                    activity = {
                        'type': row[0],
                        'timestamp': row[1],
                        'details': json.loads(row[2]) if row[2] else None,
                        'ip_address': row[3]
                    }
                    activities.append(activity)
                
                logger.debug(f"Retrieved {len(activities)} activities for user {user_id}")
                return activities
                
        except MySQLError as e:
            logger.error(f"Database error getting user activity: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get user activity: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting user activity: {str(e)}\n{traceback.format_exc()}")
            raise

    def get_user_stats(self, email: str) -> Dict:
        """Get comprehensive user statistics with proper error handling"""
        try:
            # Validate input parameters
            if not email or not isinstance(email, str):
                raise ValidationError("Invalid email")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get user basic info
                cursor.execute("""
                    SELECT 
                        traffic_limit,
                        total_usage,
                        status,
                        expiry_date,
                        created_at
                    FROM users 
                    WHERE email = %s
                """, (email,))
                
                user_row = cursor.fetchone()
                if not user_row:
                    logger.warning(f"Attempted to get stats for non-existent user: {email}")
                    raise ValidationError("User does not exist")
                
                traffic_limit, total_usage, status, expiry_date, created_at = user_row
                
                # Get session statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_sessions,
                        SUM(data_usage) as session_usage,
                        MAX(connected_at) as last_connection,
                        COUNT(DISTINCT ip_address) as unique_ips,
                        COUNT(DISTINCT device_info) as unique_devices
                    FROM user_sessions 
                    WHERE email = %s
                """, (email,))
                
                session_row = cursor.fetchone()
                total_sessions, session_usage, last_connection, unique_ips, unique_devices = session_row
                
                # Get recent locations
                cursor.execute("""
                    SELECT DISTINCT location 
                    FROM user_sessions 
                    WHERE email = %s AND location IS NOT NULL 
                    ORDER BY connected_at DESC 
                    LIMIT 5
                """, (email,))
                
                recent_locations = [row[0] for row in cursor.fetchall()]
                
                stats = {
                    'traffic_limit': traffic_limit * 1024**3,  # Convert to bytes
                    'total_usage': total_usage,
                    'usage_percentage': (total_usage / (traffic_limit * 1024**3) * 100) if traffic_limit > 0 else 0,
                    'status': status,
                    'expiry_date': expiry_date,
                    'account_age_days': (datetime.now() - datetime.fromisoformat(created_at)).days,
                    'total_sessions': total_sessions,
                    'session_usage': session_usage or 0,
                    'last_connection': last_connection,
                    'unique_ips': unique_ips,
                    'unique_devices': unique_devices,
                    'recent_locations': recent_locations
                }
                
                logger.debug(f"Retrieved comprehensive stats for user {email}")
                return stats
                
        except MySQLError as e:
            logger.error(f"Database error getting user stats: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get user statistics: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting user stats: {str(e)}\n{traceback.format_exc()}")
            raise

    def get_user_messages(self, user_id: int, since_timestamp: float) -> List[Dict]:
        """Get user messages for rate limiting with proper error handling"""
        try:
            # Validate input parameters
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValidationError("Invalid user ID")
            if not isinstance(since_timestamp, (int, float)):
                raise ValidationError("Invalid timestamp")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get messages within the time window
                cursor.execute('''
                    SELECT timestamp, message, details
                    FROM logs
                    WHERE user_id = %s 
                    AND event_type = 'message_received'
                    AND timestamp >= FROM_UNIXTIME(%s)
                    ORDER BY timestamp DESC
                ''', (user_id, since_timestamp))
                
                messages = []
                for row in cursor.fetchall():
                    message = {
                        'timestamp': row[0],
                        'message': row[1],
                        'details': json.loads(row[2]) if row[2] else None
                    }
                    messages.append(message)
                
                logger.debug(f"Retrieved {len(messages)} messages for user {user_id}")
                return messages
                
        except MySQLError as e:
            logger.error(f"Error getting user messages: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get user messages: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting user messages: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get user messages: {str(e)}")

    def close(self):
        """Clean up database resources"""
        try:
            logger.info("Cleaning up database resources")
            # Any cleanup code here if needed
        except Exception as e:
            logger.error(f"Error during database cleanup: {str(e)}\n{traceback.format_exc()}")
            # Don't raise here as this is cleanup code

    def ensure_user_exists(self, user_data: Dict) -> bool:
        """Ensure user exists in both users and telegram_users tables"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                current_time = datetime.now().isoformat()
                
                # Check if user exists
                cursor.execute("""
                    SELECT telegram_id FROM telegram_users 
                    WHERE telegram_id = %s
                """, (user_data['id'],))
                
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Update existing user
                    cursor.execute("""
                        UPDATE telegram_users 
                        SET 
                            username = COALESCE(%s, username),
                            first_name = COALESCE(%s, first_name),
                            last_name = COALESCE(%s, last_name),
                            language_code = COALESCE(%s, language_code),
                            last_activity = %s,
                            is_admin = %s
                        WHERE telegram_id = %s
                    """, (
                        user_data.get('username'),
                        user_data.get('first_name'),
                        user_data.get('last_name'),
                        user_data.get('language_code', 'fa'),
                        current_time,
                        user_data['id'] in ADMIN_IDS,
                        user_data['id']
                    ))
                else:
                    # Insert new user
                    cursor.execute("""
                        INSERT INTO telegram_users (
                            telegram_id, username, first_name, last_name,
                            language_code, created_at, last_activity, is_admin
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_data['id'],
                        user_data.get('username', ''),
                        user_data.get('first_name', ''),
                        user_data.get('last_name', ''),
                        user_data.get('language_code', 'fa'),
                        current_time,
                        current_time,
                        user_data['id'] in ADMIN_IDS
                    ))
                
                # Also ensure user exists in users table
                cursor.execute("""
                    SELECT telegram_id FROM users WHERE telegram_id = %s
                """, (user_data['id'],))
                
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO users (
                            telegram_id, username, first_name, last_name,
                            language_code, created_at, last_activity, status,
                            traffic_limit, total_usage
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_data['id'],
                        user_data.get('username', ''),
                        user_data.get('first_name', ''),
                        user_data.get('last_name', ''),
                        user_data.get('language_code', 'fa'),
                        current_time,
                        current_time,
                        'active',  # Default status
                        0,  # Default traffic limit
                        0   # Default usage
                    ))
                
                conn.commit()
                logger.info(f"User data {'updated' if existing_user else 'created'} for user {user_data['id']}")
                return True
                
        except MySQLError as e:
            error_msg = str(e)
            logger.error(f"Database error in ensure_user_exists: {error_msg}\n{traceback.format_exc()}")
            if "Unknown column" in error_msg:
                logger.error("Database schema mismatch. Please check table structure.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in ensure_user_exists: {str(e)}\n{traceback.format_exc()}")
            return False

    def log_bot_activity(self, user_id: int, command: str, input_data: dict = None, 
                        output_data: dict = None, process_details: dict = None, 
                        status: str = 'success', error: str = None) -> bool:
        """Log comprehensive bot activity including input, process, and output"""
        try:
            current_time = datetime.now().isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get user info for context
                cursor.execute("""
                    SELECT username, first_name, last_name, email 
                    FROM users 
                    WHERE telegram_id = %s
                """, (user_id,))
                user_info = cursor.fetchone()
                
                # Prepare activity details
                details = {
                    'timestamp': current_time,
                    'user_info': {
                        'telegram_id': user_id,
                        'username': user_info[0] if user_info else None,
                        'first_name': user_info[1] if user_info else None,
                        'last_name': user_info[2] if user_info else None,
                        'email': user_info[3] if user_info else None
                    },
                    'command': command,
                    'input': input_data,
                    'process': process_details,
                    'output': output_data,
                    'status': status,
                    'error': error
                }
                
                # Log to activity table
                cursor.execute("""
                    INSERT INTO user_activity (
                        user_id, activity_type, timestamp, details
                    ) VALUES (%s, %s, %s, %s)
                """, (
                    user_id,
                    f'command_{command}',
                    current_time,
                    json.dumps(details, cls=DateTimeEncoder)
                ))
                
                # If error occurred, also log to logs table
                if error:
                    cursor.execute("""
                        INSERT INTO logs (
                            timestamp, level, event_type, user_id, 
                            message, details
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        current_time,
                        'ERROR',
                        f'command_error_{command}',
                        user_id,
                        error,
                        json.dumps(details, cls=DateTimeEncoder)
                    ))
                
                conn.commit()
                logger.debug(f"Activity logged for user {user_id}, command: {command}")
                return True
                
        except Exception as e:
            logger.error(f"Error logging bot activity: {str(e)}\n{traceback.format_exc()}")
            return False

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users with pagination support"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT * FROM users
                    ORDER BY id DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                users = cursor.fetchall()
                return users if users else []
        except MySQLError as e:
            logger.error(f"Database error getting all users: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get all users: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}\n{traceback.format_exc()}")
            return []

    def count_users(self) -> int:
        """Count total number of users in the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                result = cursor.fetchone()
                return result[0] if result else 0
        except MySQLError as e:
            logger.error(f"Database error counting users: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to count users: {str(e)}")
        except Exception as e:
            logger.error(f"Error counting users: {str(e)}\n{traceback.format_exc()}")
            return 0

    def log_chat_message(self, user_id: int, message_id: int, chat_id: int, message_type: str, 
                        content: str, reply_to_message_id: int = None, forward_from_id: int = None,
                        is_command: bool = False, command_name: str = None, command_args: str = None,
                        bot_response: str = None, response_time: int = None) -> bool:
        """Log detailed chat message information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chat_history (
                        user_id, message_id, chat_id, message_type, content,
                        reply_to_message_id, forward_from_id, is_command,
                        command_name, command_args, bot_response, response_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, message_id, chat_id, message_type, content,
                    reply_to_message_id, forward_from_id, is_command,
                    command_name, command_args, bot_response, response_time
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error logging chat message: {str(e)}")
            return False

    def log_shared_link(self, user_id: int, link_type: str, link_url: str, title: str = None,
                       description: str = None, message_id: int = None, chat_id: int = None,
                       expiry_date: datetime = None) -> bool:
        """Log shared link information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO shared_links (
                        user_id, link_type, link_url, title, description,
                        message_id, chat_id, expiry_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, link_type, link_url, title, description,
                    message_id, chat_id, expiry_date
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error logging shared link: {str(e)}")
            return False

    def log_bot_command(self, command_name: str, user_id: int, args: str = None,
                       result: str = None, execution_time: int = None, status: str = 'success',
                       error_message: str = None, session_id: str = None) -> bool:
        """Log bot command execution with detailed information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Prepare command metadata
                command_metadata = {
                    'args': args,
                    'result': result,
                    'error_message': error_message,
                    'session_id': session_id
                }
                
                # Prepare performance metrics
                performance_metrics = {
                    'execution_time': execution_time,
                    'status': status,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Prepare user context
                user_context = self.get_user_info(user_id, by_telegram=True)
                
                cursor.execute("""
                    INSERT INTO bot_commands (
                        command_name, user_id, args, result, execution_time,
                        status, error_message, session_id, command_metadata,
                        performance_metrics, user_context, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    command_name,
                    user_id,
                    args,
                    result,
                    execution_time,
                    status,
                    error_message,
                    session_id,
                    json.dumps(command_metadata, cls=DateTimeEncoder),
                    json.dumps(performance_metrics, cls=DateTimeEncoder),
                    json.dumps(user_context, cls=DateTimeEncoder) if user_context else None
                ))
                
                conn.commit()
                logger.debug(f"Command logged successfully: {command_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error logging command: {str(e)}")
            return False

    def log_system_metric(self, metric_type: str, metric_value: float, details: dict = None) -> bool:
        """Log system performance metrics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_metrics (
                        metric_type, metric_value, details
                    ) VALUES (%s, %s, %s)
                """, (
                    metric_type, metric_value, json.dumps(details) if details else None
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error logging system metric: {str(e)}")
            return False

    def update_user_stats(self, user_id: int, message_count: int = 0, command_count: int = 0,
                         link_count: int = 0, session_count: int = 0) -> bool:
        """Update user statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET total_messages = total_messages + %s,
                        total_commands = total_commands + %s,
                        total_links = total_links + %s,
                        total_sessions = total_sessions + %s,
                        last_activity = CURRENT_TIMESTAMP
                    WHERE telegram_id = %s
                """, (message_count, command_count, link_count, session_count, user_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating user stats: {str(e)}")
            return False

    def get_user_activity_summary(self, user_id: int, days: int = 30) -> dict:
        """Get comprehensive user activity summary"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                # Get message count
                cursor.execute("""
                    SELECT COUNT(*) as message_count 
                    FROM chat_history 
                    WHERE user_id = %s 
                    AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """, (user_id, days))
                message_stats = cursor.fetchone()
                
                # Get command usage
                cursor.execute("""
                    SELECT command_name, COUNT(*) as usage_count 
                    FROM bot_commands 
                    WHERE user_id = %s 
                    AND timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    GROUP BY command_name
                """, (user_id, days))
                command_stats = cursor.fetchall()
                
                # Get link sharing stats
                cursor.execute("""
                    SELECT link_type, COUNT(*) as share_count 
                    FROM shared_links 
                    WHERE user_id = %s 
                    AND shared_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    GROUP BY link_type
                """, (user_id, days))
                link_stats = cursor.fetchall()
                
                # Get session stats
                cursor.execute("""
                    SELECT COUNT(*) as session_count,
                           SUM(data_usage) as total_data_usage,
                           AVG(duration) as avg_session_duration
                    FROM user_sessions 
                    WHERE user_id = %s 
                    AND connected_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """, (user_id, days))
                session_stats = cursor.fetchone()
                
                return {
                    'message_stats': message_stats,
                    'command_stats': command_stats,
                    'link_stats': link_stats,
                    'session_stats': session_stats
                }
        except Exception as e:
            logger.error(f"Error getting user activity summary: {str(e)}")
            return {}

    def get_system_metrics_summary(self, metric_type: str = None, hours: int = 24) -> dict:
        """Get system performance metrics summary"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                query = """
                    SELECT metric_type,
                           AVG(metric_value) as avg_value,
                           MIN(metric_value) as min_value,
                           MAX(metric_value) as max_value,
                           COUNT(*) as sample_count
                    FROM system_metrics
                    WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                """
                params = [hours]
                
                if metric_type:
                    query += " AND metric_type = %s"
                    params.append(metric_type)
                
                query += " GROUP BY metric_type"
                
                cursor.execute(query, tuple(params))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting system metrics summary: {str(e)}")
            return []

    def get_bot_status(self) -> bool:
        """Get current bot status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_enabled FROM bot_status ORDER BY id DESC LIMIT 1")
                result = cursor.fetchone()
                return bool(result[0]) if result else True
        except Exception as e:
            logger.error(f"Error getting bot status: {str(e)}")
            return True  # Default to enabled if error occurs

    def set_bot_status(self, is_enabled: bool, admin_id: int, reason: str = None) -> bool:
        """Set bot status with admin tracking"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO bot_status (is_enabled, updated_by, reason)
                    VALUES (%s, %s, %s)
                """, (is_enabled, admin_id, reason))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting bot status: {str(e)}")
            return False 