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
                'host': 'localhost',
                'user': 'root',
                'password': 'fsociety',
                'database': db_name
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
        """Initialize database tables with proper error handling"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Users table for storing client information
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        email VARCHAR(255) UNIQUE,
                        traffic_limit BIGINT,  -- in GB
                        expiry_date VARCHAR(50),
                        created_at VARCHAR(50),
                        last_modified VARCHAR(50),
                        status VARCHAR(20),
                        total_usage BIGINT,    -- in bytes
                        inbound_id INT,
                        telegram_id BIGINT,    -- Added telegram_id for linking
                        username VARCHAR(255),  -- Telegram username
                        first_name VARCHAR(255),-- Telegram first name
                        last_name VARCHAR(255), -- Telegram last name
                        language_code VARCHAR(10)-- User's language
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
                
                # Logs table for comprehensive logging
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp VARCHAR(50),
                        level VARCHAR(20),
                        event_type VARCHAR(50),
                        user_id BIGINT,
                        message TEXT,
                        details TEXT,
                        ip_address VARCHAR(50),    -- Added IP tracking
                        user_agent VARCHAR(255)    -- Added user agent tracking
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
                
                # Admin actions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admin_actions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        admin_id BIGINT,
                        action_type VARCHAR(50),
                        target_user VARCHAR(255),
                        timestamp VARCHAR(50),
                        details TEXT,
                        ip_address VARCHAR(50),    -- Added IP tracking
                        status VARCHAR(20)         -- Added status tracking
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
                
                # User sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        email VARCHAR(255),
                        ip_address VARCHAR(50),
                        connected_at VARCHAR(50),
                        disconnected_at VARCHAR(50),
                        data_usage BIGINT,      -- in bytes
                        device_info TEXT,       -- Added device tracking
                        location VARCHAR(255),   -- Added location tracking
                        connection_type VARCHAR(50), -- Added connection type
                        FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
                
                # User activity tracking
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_activity (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT,
                        activity_type VARCHAR(50),
                        timestamp VARCHAR(50),
                        details TEXT,
                        ip_address VARCHAR(50)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ''')
                
                conn.commit()
                logger.info("Database tables created/verified successfully")
                
        except MySQLError as e:
            logger.error(f"Error initializing database tables: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to initialize database tables: {str(e)}")

    @contextmanager
    def get_connection(self):
        """Get a database connection with automatic closing"""
        conn = None
        try:
            conn = mysql.connector.connect(**self.db_config)
            yield conn
        except MySQLError as e:
            logger.error(f"Database connection error: {str(e)}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to connect to database: {str(e)}")
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

    def log_event(self, level: str, event_type: str, user_id: Optional[int], 
                  message: str, details: Dict = None, ip_address: str = None,
                  user_agent: str = None):
        """Enhanced event logging with proper error handling"""
        try:
            # Validate input parameters
            if not level or level not in {'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
                raise ValidationError("Invalid log level")
            if not event_type or not isinstance(event_type, str):
                raise ValidationError("Invalid event type")
            if not message or not isinstance(message, str):
                raise ValidationError("Invalid message")
            
            current_time = datetime.now().isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Log the event
                cursor.execute('''
                    INSERT INTO logs (
                        timestamp, level, event_type, user_id, 
                        message, details, ip_address, user_agent
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    current_time,
                    level,
                    event_type,
                    user_id,
                    message,
                    json.dumps(details, cls=DateTimeEncoder) if details else None,
                    ip_address,
                    user_agent
                ))
                
                # Also log to user_activity if user_id is provided
                if user_id:
                    cursor.execute('''
                        INSERT INTO user_activity (
                            user_id, activity_type, timestamp, 
                            details, ip_address
                        )
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (
                        user_id,
                        event_type,
                        current_time,
                        json.dumps(details, cls=DateTimeEncoder) if details else None,
                        ip_address
                    ))
                
                conn.commit()
                logger.debug(f"Event logged successfully: {event_type}")
                
        except Exception as e:
            logger.error(f"Error logging event: {str(e)}\n{traceback.format_exc()}")
            # Don't raise here to prevent logging failures from affecting main functionality
            return False
        return True

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
            # Validate input parameters
            if by_telegram and not isinstance(identifier, int):
                raise ValidationError("Telegram ID must be an integer")
            if not by_telegram and not isinstance(identifier, str):
                raise ValidationError("Email must be a string")
            
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
            raise

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

    def ensure_user_exists(self, user_data: dict) -> bool:
        """Ensure user exists in database and update their information if needed"""
        try:
            # Validate user data
            if not isinstance(user_data, dict):
                logger.warning("Invalid user data type provided")
                return False
                
            if not user_data.get('id'):
                logger.warning("Missing user ID in user data")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute("""
                    SELECT telegram_id, username, first_name, last_name, language_code, status
                    FROM users 
                    WHERE telegram_id = %s
                """, (user_data['id'],))
                
                existing_user = cursor.fetchone()
                current_time = datetime.now().isoformat()
                
                if existing_user:
                    # Update user information if changed
                    cursor.execute("""
                        UPDATE users 
                        SET 
                            username = COALESCE(%s, username),
                            first_name = COALESCE(%s, first_name),
                            last_name = COALESCE(%s, last_name),
                            language_code = COALESCE(%s, language_code),
                            last_modified = %s
                        WHERE telegram_id = %s
                    """, (
                        user_data.get('username'),
                        user_data.get('first_name'),
                        user_data.get('last_name'),
                        user_data.get('language_code'),
                        current_time,
                        user_data['id']
                    ))
                else:
                    # Insert new user with default values
                    cursor.execute("""
                        INSERT INTO users (
                            telegram_id, username, first_name, last_name,
                            language_code, created_at, last_modified, status,
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
                
        except Exception as e:
            logger.error(f"Error ensuring user exists: {str(e)}\n{traceback.format_exc()}")
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