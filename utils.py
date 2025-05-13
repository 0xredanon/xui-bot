import os
import re
from datetime import datetime
import pytz
from typing import Tuple

def save_user_info(chat_id: str, first_name: str, last_name: str, username: str, email: str = "") -> None:
    """Save user information to a file."""
    now_tehran = datetime.now(pytz.timezone('Asia/Tehran'))
    current_time = now_tehran.strftime("%Y-%m-%d %H:%M:%S")
    user_data = f"Time: {current_time}\nFirst: {first_name}\nLast: {last_name}\nUsername: {username}\nUser ID: {chat_id}\nEmail: {email}\n\n"
    
    if not os.path.exists("userid"):
        os.makedirs("userid")
    file_path = "userid/usersID.txt"
    with open(file_path, "a") as file:
        file.write(user_data)

def extract_email_from_vless_link(vless_link: str) -> str:
    """Extract email from vless link."""
    email = re.search(r'-([A-Za-z0-9]+)$', vless_link).group(1)
    return email

def format_remaining_days(expiry_time: int) -> str:
    """Format remaining days until service expiration."""
    remaining_days = (expiry_time - int(datetime.now().timestamp() * 1000)) / (1000 * 60 * 60 * 24)
    return f"{int(remaining_days)} روز تا اتمام تاریخ سرویس"

def convert_bytes(byte_value: int) -> Tuple[float, float, float]:
    """Convert bytes to KB, MB, GB."""
    kb = byte_value / 1024
    mb = kb / 1024
    gb = mb / 1024
    return kb, mb, gb

def format_total(total_value: int) -> str:
    """Format total value in GB."""
    kb, mb, gb = convert_bytes(total_value)
    return f"{gb:.2f} GB"

def get_tehran_time() -> str:
    """Get current time in Tehran timezone."""
    time = datetime.now(pytz.timezone('Asia/Tehran'))
    return time.strftime('%Y/%m/%d %H:%M:%S') 