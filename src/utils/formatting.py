from typing import Dict, Any, List, Union
from datetime import datetime
import pytz
import re
from persiantools.jdatetime import JalaliDateTime

def format_size(size_bytes: Union[int, float]) -> str:
    """Format bytes size to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def format_date(timestamp: float) -> str:
    """Format timestamp to human readable date"""
    if not timestamp:
        return "نامشخص"
    
    try:
        dt = datetime.fromtimestamp(timestamp)
        jdt = JalaliDateTime.to_jalali(dt)
        return jdt.strftime("%Y/%m/%d")
    except Exception:
        return "نامشخص"

def escape_markdown(text: str) -> str:
    """Escape special characters for Markdown V2 formatting"""
    if not text:
        return ""
    
    # First escape backslashes
    text = text.replace('\\', '\\\\')
    
    # Characters that need to be escaped in MarkdownV2
    special_chars = [
        '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', 
        '+', '-', '=', '|', '{', '}', '.', '!', '$', '&'
    ]
    
    # Escape special characters
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def format_code(text: str) -> str:
    """Format text as inline code with proper escaping"""
    escaped_text = text.replace('`', '\\`')
    return f'`{escaped_text}`'

def format_bold(text: str) -> str:
    """Format text as bold with proper escaping"""
    escaped_text = text.replace('*', '\\*')
    return f'*{escaped_text}*'

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

def format_traffic(bytes_value: int) -> str:
    """Format traffic value in human readable format."""
    gb = bytes_value / (1024 * 1024 * 1024)
    return f"{gb:.2f} GB"

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