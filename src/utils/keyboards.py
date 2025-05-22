from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def create_client_status_keyboard(client_uuid: str, is_admin: bool) -> InlineKeyboardMarkup:
    """Create keyboard for client status message"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Main refresh button
    keyboard.row(
        InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"refresh_{client_uuid}")
    )
    
    if is_admin:
        # Traffic management buttons
        keyboard.row(
            InlineKeyboardButton("🔄 ریست ترافیک", callback_data=f"reset_{client_uuid}"),
            InlineKeyboardButton("⚡️ تمدید", callback_data=f"extend_{client_uuid}")
        )
        keyboard.row(
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit_{client_uuid}"),
            InlineKeyboardButton("❌ حذف", callback_data=f"delete_{client_uuid}")
        )
        keyboard.row(
            InlineKeyboardButton("📊 آمار مصرف", callback_data=f"stats_{client_uuid}")
        )
    
    return keyboard

def create_traffic_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=3)
    traffic_options = [5, 10, 20, 50, 100, 200, 500, 1000]
    
    # Create rows with three buttons each
    for i in range(0, len(traffic_options), 3):
        row = []
        for gb in traffic_options[i:i+3]:
            row.append(InlineKeyboardButton(
                f"{gb}GB",
                callback_data=f"settraffic_{client_uuid}_{gb}"
            ))
        keyboard.row(*row)
    
    # Add unlimited and custom traffic buttons
    keyboard.row(
        InlineKeyboardButton("♾️ نامحدود", callback_data=f"setunlimited_{client_uuid}"),
        InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"customtraffic_{client_uuid}")
    )
    
    # Add back button
    keyboard.row(
        InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}")
    )
    
    return keyboard

def create_expiry_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=3)
    expiry_options = [7, 15, 30, 60, 90, 180, 365]
    
    # Create rows with three buttons each
    for i in range(0, len(expiry_options), 3):
        row = []
        for days in expiry_options[i:i+3]:
            row.append(InlineKeyboardButton(
                f"{days} روز",
                callback_data=f"setexpiry_{client_uuid}_{days}"
            ))
        keyboard.row(*row)
    
    # Add unlimited and custom expiry buttons
    keyboard.row(
        InlineKeyboardButton("♾️ نامحدود", callback_data=f"setexpiry_{client_uuid}_0"),
        InlineKeyboardButton("📅 تاریخ دلخواه", callback_data=f"customexpiry_{client_uuid}")
    )
    
    # Add back button
    keyboard.row(
        InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}")
    )
    
    return keyboard

def create_stats_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    """Create keyboard for statistics options"""
    keyboard = InlineKeyboardMarkup()
    
    # Add statistics buttons
    keyboard.row(
        InlineKeyboardButton(
            "📊 آمار کلی",
            callback_data=f"total_stats_{client_uuid}"
        ),
        InlineKeyboardButton(
            "📈 نمودار مصرف",
            callback_data=f"usage_graph_{client_uuid}"
        )
    )
    keyboard.row(
        InlineKeyboardButton(
            "👥 کاربران آنلاین",
            callback_data=f"online_users_{client_uuid}"
        ),
        InlineKeyboardButton(
            "📋 گزارش روزانه",
            callback_data=f"daily_report_{client_uuid}"
        )
    )
    
    # Add back button
    keyboard.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=f"back_{client_uuid}"
        )
    )
    
    return keyboard 