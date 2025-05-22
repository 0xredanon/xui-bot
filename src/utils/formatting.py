from typing import Dict, Any, List, Union
from datetime import datetime, timezone
import pytz
import re
from persiantools.jdatetime import JalaliDateTime

from .logger import CustomLogger

# Initialize logger
logger = CustomLogger("Formatting")

def format_size(size_bytes: float) -> str:
    """Format bytes to human readable size with proper unit"""
    try:
        if not isinstance(size_bytes, (int, float)):
            return "0 B"
            
        # Define units and their thresholds
        units = [
            ('B', 1),
            ('KB', 1024),
            ('MB', 1024 ** 2),
            ('GB', 1024 ** 3),
            ('TB', 1024 ** 4)
        ]
        
        # Find the appropriate unit
        for unit, threshold in units:
            if size_bytes < threshold * 1024:
                # Convert to the current unit
                value = size_bytes / threshold
                return f"{value:.2f} {unit}"
        
        # If size is larger than TB, use TB
        value = size_bytes / (1024 ** 4)
        return f"{value:.2f} TB"
        
    except Exception as e:
        logger.error(f"Error formatting size: {str(e)}")
        return "0 B"

def format_date(timestamp: Union[int, float, str]) -> str:
    """Format timestamp to human readable date in Tehran timezone.
    
    Args:
        timestamp: Unix timestamp in milliseconds, seconds, or string representation
        
    Returns:
        str: Formatted date string with detailed time information
    """
    try:
        logger.info(f"format_date input timestamp: {timestamp} (type: {type(timestamp)})")
        
        # Handle special cases
        if timestamp is None or timestamp == "":
            logger.info("format_date: timestamp is None or empty, returning 'نامشخص'")
            return "نامشخص"
            
        # Convert timestamp to float if it's a string
        if isinstance(timestamp, str):
            try:
                timestamp = float(timestamp)
                logger.info(f"format_date: converted string to float: {timestamp}")
            except ValueError:
                logger.error(f"format_date: invalid string timestamp: {timestamp}")
                return "نامشخص"
                
        # Handle zero or negative timestamps
        if timestamp <= 0:
            logger.info("format_date: timestamp is zero or negative, returning 'نامشخص'")
            return "نامشخص"
            
        # Determine if timestamp is in milliseconds or seconds
        if timestamp > 1e12:  # Likely milliseconds
            timestamp = timestamp / 1000
            logger.info(f"format_date: converted from milliseconds to seconds: {timestamp}")
            
        # Create datetime object in UTC
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        logger.info(f"format_date: UTC datetime: {dt}")
        
        # Convert to Tehran timezone
        tehran_tz = pytz.timezone('Asia/Tehran')
        dt_tehran = dt.astimezone(tehran_tz)
        logger.info(f"format_date: Tehran datetime: {dt_tehran}")
        
        # Convert to Jalali date
        jdate = JalaliDateTime.to_jalali(dt_tehran)
        logger.info(f"format_date: Jalali date: {jdate}")
        
        # Format the date and time
        date_str = jdate.strftime('%Y/%m/%d')
        time_str = dt_tehran.strftime('%H:%M:%S')
        
        # Always return the full date and time
        return f"{date_str} {time_str}"
            
    except Exception as e:
        logger.error(f"Error formatting date (timestamp={timestamp}, type={type(timestamp)}): {str(e)}")
        return "نامشخص"

def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2 format"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    escaped_text = str(text)
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    return escaped_text

def format_code(text: str) -> str:
    """Format text as inline code"""
    return f'`{text}`'

def format_bold(text: str) -> str:
    """Format text as bold"""
    return f'*{text}*'

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def format_duration(seconds: int) -> str:
    """Format seconds to human readable duration"""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    
    return " ".join(parts)

def format_traffic(bytes_used: int, bytes_total: int) -> str:
    """Format traffic usage with percentage"""
    used = format_size(bytes_used)
    total = format_size(bytes_total)
    percentage = (bytes_used / bytes_total * 100) if bytes_total > 0 else 0
    return f"{used}/{total} ({percentage:.1f}%)"

def format_status(status: bool) -> str:
    """Format boolean status to emoji"""
    return "🟢" if status else "🔴"

def format_number(num: Union[int, float]) -> str:
    """Format number with thousand separators"""
    return f"{num:,}"

def convert_bytes_to_unit(bytes_value: int, unit: str = 'GB') -> float:
    """Convert bytes to specified unit (default GB)"""
    try:
        if not isinstance(bytes_value, (int, float)):
            return 0.0
            
        units = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 ** 2,
            'GB': 1024 ** 3,
            'TB': 1024 ** 4,
            'PB': 1024 ** 5
        }
        
        if unit not in units:
            unit = 'GB'  # Default to GB if invalid unit
            
        return round(bytes_value / units[unit], 2)
        
    except Exception as e:
        logger.error(f"Error converting traffic: {str(e)}")
        return 0.0

def format_client_ips(ips_data: Dict[str, Any]) -> str:
    """Format client IP addresses information."""
    if not ips_data or not ips_data.get('obj') or len(ips_data['obj']) == 0:
        return "⚠️ هیچ رکورد IP برای این کاربر یافت نشد"

    ips = ips_data['obj']
    if len(ips) == 0:
        return "⚠️ هیچ رکورد IP برای این کاربر یافت نشد"

    formatted_text = "📱 *آدرس های IP استفاده شده:*\n\n"
    
    for ip in ips:
        formatted_text += f"🔹 `{ip}`\n"
    
    formatted_text += f"\n📊 *تعداد کل:* `{len(ips)}`"
    return formatted_text

def format_online_clients(online_data: List[Dict[str, Any]]) -> str:
    """Format online clients information."""
    if not online_data or not isinstance(online_data, list):
        return "⚠️ در حال حاضر هیچ کاربری آنلاین نیست"

    formatted_text = "👥 *کاربران آنلاین:*\n\n"
    total_up = 0
    total_down = 0
    
    try:
        for client in online_data:
            if not isinstance(client, dict):
                continue
                
            email = client.get('email', 'نامشخص')
            up = int(client.get('up', 0))
            down = int(client.get('down', 0))
            total_up += up
            total_down += down
            
            formatted_text += (
                f"👤 *کاربر:* `{email}`\n"
                f"🔼 *آپلود:* `{format_size(up)}`\n"
                f"🔽 *دانلود:* `{format_size(down)}`\n"
                f"━━━━━━━━━━━━━━\n"
            )
        
        # Add summary only if we have valid data
        if len(online_data) > 0:
            formatted_text += (
                f"\n📊 *آمار کلی:*\n"
                f"👥 *تعداد کاربران آنلاین:* `{len(online_data)}`\n"
                f"🔼 *مجموع آپلود:* `{format_size(total_up)}`\n"
                f"🔽 *مجموع دانلود:* `{format_size(total_down)}`\n"
            )
        else:
            return "⚠️ در حال حاضر هیچ کاربری آنلاین نیست"
            
        return formatted_text
    except Exception as e:
        return "⚠️ خطا در پردازش اطلاعات کاربران آنلاین"

def format_client_info(client_data: Dict[str, Any]) -> str:
    """Format client information for display with enhanced time information.
    
    Args:
        client_data: Dictionary containing client information
        
    Returns:
        str: Formatted client information with detailed time breakdown
    """
    try:
        # Extract client data
        email = client_data.get('email', 'نامشخص')
        up = client_data.get('up', 0)
        down = client_data.get('down', 0)
        total = client_data.get('total', 0)
        remark = client_data.get('remark', 'بدون توضیحات')
        enable = client_data.get('enable', True)
        created_at = client_data.get('created_at', 0)
        last_connection = client_data.get('last_connection', 0)
        expire_time = client_data.get('expire_time', 0)
        
        # Format traffic usage
        up_str = format_size(up)
        down_str = format_size(down)
        total_str = format_size(total)
        
        # Format dates with detailed information
        created_str = format_date(created_at)
        last_conn_str = format_date(last_connection)
        expire_str = format_date(expire_time)
        remaining_str = format_remaining_time(expire_time)
        
        # Build status strings
        status = "✅ فعال" if enable else "❌ غیرفعال"
        
        # Format the message with enhanced time information
        formatted_text = (
            f"📊 *اطلاعات کاربر*\n\n"
            f"👤 *کاربر:* `{email}`\n"
            f"📝 *توضیحات:* `{remark}`\n"
            f"📊 *وضعیت:* {status}\n\n"
            f"📈 *آمار ترافیک:*\n"
            f"🔼 *آپلود:* `{up_str}`\n"
            f"🔽 *دانلود:* `{down_str}`\n"
            f"📊 *کل:* `{total_str}`\n\n"
            f"⏰ *تاریخ‌ها:*\n"
            f"📅 *تاریخ ایجاد:* `{created_str}`\n"
            f"🕒 *آخرین اتصال:* `{last_conn_str}`\n"
            f"⏳ *تاریخ انقضا:* `{expire_str}`\n"
            f"⏱ *زمان باقیمانده:* `{remaining_str}`\n"
        )
        
        return formatted_text
        
    except Exception as e:
        logger.error(f"Error formatting client info: {str(e)}")
        return "❌ خطا در دریافت اطلاعات کاربر"

def format_remaining_time(expiry_timestamp: Union[int, float, str]) -> str:
    """Format remaining time until expiry.
    
    Args:
        expiry_timestamp: Unix timestamp in milliseconds, seconds, or string
        
    Returns:
        str: Formatted remaining time string
    """
    try:
        logger.info(f"format_remaining_time input timestamp: {expiry_timestamp} (type: {type(expiry_timestamp)})")
        
        # Handle special cases
        if expiry_timestamp is None or expiry_timestamp == "":
            logger.info("format_remaining_time: timestamp is None or empty, returning 'نامشخص'")
            return "نامشخص"
            
        # Convert to float if string
        if isinstance(expiry_timestamp, str):
            try:
                expiry_timestamp = float(expiry_timestamp)
                logger.info(f"format_remaining_time: converted string to float: {expiry_timestamp}")
            except ValueError:
                logger.error(f"format_remaining_time: invalid string timestamp: {expiry_timestamp}")
                return "نامشخص"
            
        # Handle zero or negative timestamps
        if expiry_timestamp <= 0:
            logger.info("format_remaining_time: timestamp is zero or negative, returning 'نامشخص'")
            return "نامشخص"
            
        # Convert to seconds if timestamp is in milliseconds
        if isinstance(expiry_timestamp, (int, float)) and expiry_timestamp > 1e12:
            expiry_timestamp = expiry_timestamp / 1000
            logger.info(f"format_remaining_time: converted from milliseconds to seconds: {expiry_timestamp}")
            
        # Get current time in Tehran timezone
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        
        # Convert expiry timestamp to datetime
        expiry_dt = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc)
        expiry_dt = expiry_dt.astimezone(tehran_tz)
        logger.info(f"format_remaining_time: Expiry datetime (Tehran): {expiry_dt}")
        
        # Calculate time difference
        time_diff = expiry_dt - now
        logger.info(f"format_remaining_time: Time difference: {time_diff}")
        
        # If already expired
        if time_diff.total_seconds() <= 0:
            logger.info("format_remaining_time: Time has expired")
            return "منقضی شده"
            
        # Format based on remaining time
        days = time_diff.days
        hours = time_diff.seconds // 3600
        minutes = (time_diff.seconds % 3600) // 60
        
        if days > 0:
            if hours > 0:
                return f"{days} روز و {hours} ساعت"
            return f"{days} روز"
        elif hours > 0:
            if minutes > 0:
                return f"{hours} ساعت و {minutes} دقیقه"
            return f"{hours} ساعت"
        else:
            return f"{minutes} دقیقه"
            
    except Exception as e:
        logger.error(f"Error formatting remaining time (timestamp={expiry_timestamp}, type={type(expiry_timestamp)}): {str(e)}")
        return "نامشخص"

def convert_bytes(total_value):
    """Convert bytes to KB, MB, GB"""
    kb = total_value / 1024
    mb = kb / 1024
    gb = mb / 1024
    return kb, mb, gb

def format_total(total_value):
    """Format total value in GB"""
    kb, mb, gb = convert_bytes(total_value)
    return f"{gb:.2f} GB"

def format_remaining_days(expiry_time: Union[int, float, str]) -> str:
    """Format remaining time until expiry with detailed breakdown.
    
    Args:
        expiry_time: Unix timestamp in milliseconds, seconds, or string
        
    Returns:
        str: Formatted remaining time string with days until expiry
    """
    try:
        # Handle special cases
        if expiry_time is None or expiry_time == "":
            return "نامشخص"
            
        # Convert to float if string
        if isinstance(expiry_time, str):
            try:
                expiry_time = float(expiry_time)
            except ValueError:
                return "نامشخص"
            
        # Handle zero or negative timestamps
        if expiry_time <= 0:
            return "نامشخص"
            
        # Convert to seconds if timestamp is in milliseconds
        if isinstance(expiry_time, (int, float)) and expiry_time > 1e12:
            expiry_time = expiry_time / 1000
            
        # Calculate remaining days
        remaining_days = (expiry_time - int(datetime.now().timestamp())) / (60 * 60 * 24)
        
        # If already expired
        if remaining_days <= 0:
            return "فاقد تاریخ انقضا"
            
        # Format as days
        return f"{int(remaining_days)} روز تا اتمام تاریخ سرویس"
            
    except Exception as e:
        logger.error(f"Error formatting remaining days: {str(e)}")
        return "نامشخص"