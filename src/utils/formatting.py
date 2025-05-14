from typing import Dict, Any, List, Union
from datetime import datetime
import pytz
import re
from persiantools.jdatetime import JalaliDateTime

from .logger import CustomLogger

# Initialize logger
logger = CustomLogger("Formatting")

def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size with proper unit conversion"""
    try:
        if not isinstance(size_bytes, (int, float)):
            return "0 B"
            
        if size_bytes == 0:
            return "0 B"
            
        # Define size units
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        
        # Calculate the appropriate unit
        unit_index = 0
        size = float(size_bytes)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
            
        # Format with appropriate precision
        if unit_index == 0:  # Bytes
            return f"{int(size)} {units[unit_index]}"
        elif size >= 100:  # Large numbers, no decimal
            return f"{int(size)} {units[unit_index]}"
        elif size >= 10:   # Medium numbers, one decimal
            return f"{size:.1f} {units[unit_index]}"
        else:              # Small numbers, two decimals
            return f"{size:.2f} {units[unit_index]}"
            
    except Exception as e:
        logger.error(f"Error formatting size: {str(e)}")
        return "0 B"

def format_date(timestamp: Union[str, int, float, datetime]) -> str:
    """Format timestamp to human readable date"""
    try:
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
            except ValueError:
                dt = datetime.fromtimestamp(float(timestamp))
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return "نامشخص"
            
        # Convert to local timezone (Tehran)
        tehran_tz = pytz.timezone('Asia/Tehran')
        dt = dt.astimezone(tehran_tz)
        
        # Format date in Persian style
        return dt.strftime("%Y/%m/%d %H:%M:%S")
        
    except Exception as e:
        logger.error(f"Error formatting date: {str(e)}")
        return "نامشخص"

def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2 format"""
    if not isinstance(text, str):
        text = str(text)
        
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_code(text: str) -> str:
    """Format text as inline code for MarkdownV2"""
    return escape_markdown(str(text))

def format_bold(text: str) -> str:
    """Format text as bold for MarkdownV2"""
    return f"*{escape_markdown(str(text))}*"

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

def format_traffic(bytes_value: int, unit: str = 'GB') -> float:
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
            
        return bytes_value / units[unit]
        
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
                f"🔼 *آپلود:* `{format_traffic(up)}`\n"
                f"🔽 *دانلود:* `{format_traffic(down)}`\n"
                f"━━━━━━━━━━━━━━\n"
            )
        
        # Add summary only if we have valid data
        if len(online_data) > 0:
            formatted_text += (
                f"\n📊 *آمار کلی:*\n"
                f"👥 *تعداد کاربران آنلاین:* `{len(online_data)}`\n"
                f"🔼 *مجموع آپلود:* `{format_traffic(total_up)}`\n"
                f"🔽 *مجموع دانلود:* `{format_traffic(total_down)}`\n"
            )
        else:
            return "⚠️ در حال حاضر هیچ کاربری آنلاین نیست"
            
        return formatted_text
    except Exception as e:
        return "⚠️ خطا در پردازش اطلاعات کاربران آنلاین"

def format_client_info(traffic_data: Dict[str, Any]) -> str:
    """Format client traffic information."""
    if not traffic_data.get('obj'):
        return "⚠️ اطلاعاتی برای این کاربر یافت نشد"

    data = traffic_data['obj']
    
    # Calculate traffic values
    down_gb = data['down'] / (1024 * 1024 * 1024)
    up_gb = data['up'] / (1024 * 1024 * 1024)
    total_use = down_gb + up_gb
    
    # Format total traffic
    if data['total'] == 0:
        total_traffic = "نامحدود ♾️"
    else:
        total_traffic = format_traffic(data['total'])
    
    # Format status
    status = "فعال 🟢" if data['enable'] else "غیرفعال 🔴"
    
    # Format expiry
    if data['expiryTime'] <= int(datetime.now().timestamp() * 1000):
        expiry_status = "فاقد تاریخ انقضا ⚠️"
    else:
        remaining_days = (data['expiryTime'] - int(datetime.now().timestamp() * 1000)) / (1000 * 60 * 60 * 24)
        expiry_status = f"{int(remaining_days)} روز باقیمانده 📅"
    
    # Get current time in Tehran timezone
    tehran_time = datetime.now(pytz.timezone('Asia/Tehran')).strftime('%Y/%m/%d %H:%M:%S')
    
    # Format the message
    info_message = (
        f"*وضعیت سرویس:* {status}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔼 *آپلود:* `{up_gb:.2f} GB`\n"
        f"🔽 *دانلود:* `{down_gb:.2f} GB`\n"
        f"➕ *مصرف کل:* `{total_use:.2f} GB`\n"
        f"💠 *حجم کل:* `{total_traffic}`\n"
        f"⏳ *انقضا:* `{expiry_status}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"🕒 *آخرین بروزرسانی:* `{tehran_time}`"
    )
    
    return info_message 