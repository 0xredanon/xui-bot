import os
import requests
import re
from datetime import datetime, timedelta
import pytz
import time

def format_remaining_days(expiry_time):
    """Format remaining days until expiry using first version's calculation"""
    try:
        # Convert string to int if needed
        if isinstance(expiry_time, str):
            expiry_time = int(expiry_time)
        
        # Get current timestamp in milliseconds
        current_time = int(datetime.now().timestamp() * 1000)
        
        # Log values for debugging
        print(f"Expiry time: {expiry_time}, Current time: {current_time}")
        
        # Handle zero or negative expiry time
        if expiry_time <= 0:
            return "نامحدود"
            
        if expiry_time <= current_time:
            return "فاقد تاریخ انقضا"
        else:
            remaining_milliseconds = expiry_time - current_time
            remaining_seconds = remaining_milliseconds / 1000
            remaining_hours = remaining_seconds / 3600
            
            if remaining_hours < 24:
                return f"{int(remaining_hours)} ساعت تا اتمام تاریخ سرویس"
            else:
                remaining_days = remaining_hours / 24
                return f"{int(remaining_days)} روز تا اتمام تاریخ سرویس"
    except Exception as e:
        print(f"Error in format_remaining_days: {str(e)}")
        return "نامشخص"

def convert_bytes(byte_value):
    """Convert bytes to KB, MB, GB"""
    kb = byte_value / 1024
    mb = kb / 1024
    gb = mb / 1024
    return kb, mb, gb

def format_total(total_value):
    """Format total value in GB"""
    kb, mb, gb = convert_bytes(total_value)
    return f"{gb:.2f} GB" 