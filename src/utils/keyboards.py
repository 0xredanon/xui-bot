from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def create_client_status_keyboard(client_uuid: str, is_admin: bool) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("🔄 بروزرسانی وضعیت", callback_data=f"refresh_{client_uuid}")
    )
    
    if is_admin:
        # Traffic control buttons
        keyboard.row(
            InlineKeyboardButton("🎯 تنظیم حجم", callback_data=f"traffic_{client_uuid}"),
            InlineKeyboardButton("♻️ ریست حجم", callback_data=f"reset_{client_uuid}")
        )
        keyboard.row(
            InlineKeyboardButton("♾️ حجم نامحدود", callback_data=f"unlimited_{client_uuid}"),
            InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"custom_traffic_{client_uuid}")
        )
        
        # Expiry control buttons
        keyboard.row(
            InlineKeyboardButton("🗓️ تنظیم تاریخ انقضا", callback_data=f"expiry_{client_uuid}")
        )
        
        # IP management buttons
        keyboard.row(
            InlineKeyboardButton("👀 مشاهده IPها", callback_data=f"ips_{client_uuid}")
        )
    
    return keyboard

def create_traffic_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    traffic_options = [10, 20, 30, 50, 100]
    
    # Create rows with two buttons each
    for i in range(0, len(traffic_options), 2):
        row = []
        row.append(InlineKeyboardButton(
            f"{traffic_options[i]}GB",
            callback_data=f"settraffic_{client_uuid}_{traffic_options[i]}"
        ))
        if i + 1 < len(traffic_options):
            row.append(InlineKeyboardButton(
                f"{traffic_options[i+1]}GB",
                callback_data=f"settraffic_{client_uuid}_{traffic_options[i+1]}"
            ))
        keyboard.row(*row)
    
    # Add custom traffic input button
    keyboard.row(
        InlineKeyboardButton("🔢 حجم دلخواه", callback_data=f"custom_traffic_{client_uuid}")
    )
    
    # Add back button
    keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}"))
    return keyboard

def create_expiry_options_keyboard(client_uuid: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    days_options = [1, 2, 3, 5, 10, 30, 60, 90, 120, 180]
    
    # Create rows with three buttons each
    for i in range(0, len(days_options), 3):
        row = []
        for j in range(3):
            if i + j < len(days_options):
                row.append(InlineKeyboardButton(
                    f"{days_options[i+j]} روز",
                    callback_data=f"setexpiry_{client_uuid}_{days_options[i+j]}"
                ))
        keyboard.row(*row)
    
    # Add unlimited option
    keyboard.row(
        InlineKeyboardButton("♾️ نامحدود", callback_data=f"setexpiry_{client_uuid}_0")
    )
    
    # Add back button
    keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{client_uuid}"))
    return keyboard 