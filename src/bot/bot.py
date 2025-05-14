import os
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import Session
from typing import Optional

from ..models.base import SessionLocal
from ..models.models import TelegramUser, UserActivity, ChatHistory, VPNClient
from ..api.xui_client import XUIClient

# Initialize bot with hardcoded token
BOT_TOKEN = "7131562124:AAE_IRcN0UJHXSrChUCfD0e7TZvLg_7s5mk"  # Replace with your Telegram bot token
bot = telebot.TeleBot(BOT_TOKEN)
xui_client = XUIClient()

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def save_user_activity(db: Session, user_id: int, activity_type: str, target_uuid: Optional[str] = None, details: dict = None):
    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        target_uuid=target_uuid,
        details=details or {}
    )
    db.add(activity)
    db.commit()

def save_chat_message(db: Session, user_id: int, message_id: int, message_type: str, content: str):
    chat = ChatHistory(
        user_id=user_id,
        message_id=message_id,
        message_type=message_type,
        content=content
    )
    db.add(chat)
    db.commit()

def get_or_create_user(db: Session, telegram_user) -> TelegramUser:
    user = db.query(TelegramUser).filter_by(telegram_id=telegram_user.id).first()
    if not user:
        user = TelegramUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

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

@bot.message_handler(commands=['start'])
def start_command(message):
    with get_db() as db:
        user = get_or_create_user(db, message.from_user)
        save_chat_message(db, user.id, message.message_id, "COMMAND", "/start")
        
        welcome_text = (
            "Welcome to XUI VPN Bot!\n\n"
            "Use /usage to check your VPN status"
        )
        if user.is_admin:
            welcome_text += "\nYou have admin privileges."
        
        bot.reply_to(message, welcome_text)
        save_user_activity(db, user.id, "START_COMMAND")

@bot.message_handler(commands=['status'])
def status_command(message):
    with get_db() as db:
        user = get_or_create_user(db, message.from_user)
        save_chat_message(db, user.id, message.message_id, "COMMAND", "/status")
        
        # Get client info from API
        clients = xui_client.get_clients(user.telegram_id)
        
        if not clients:
            bot.reply_to(message, "You don't have any active VPN clients.")
            return
        
        for client in clients:
            status_text = (
                f"📊 Client Status:\n"
                f"Email: {client['email']}\n"
                f"Traffic: {client['used_traffic']}/{client['total_traffic']} GB\n"
                f"Expires: {client['expire_date']}\n"
                f"Status: {'🟢 Active' if client['enable'] else '🔴 Disabled'}"
            )
            
            keyboard = create_client_status_keyboard(client['uuid'], user.is_admin)
            bot.reply_to(message, status_text, reply_markup=keyboard)
        
        save_user_activity(db, user.id, "STATUS_CHECK")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    with get_db() as db:
        user = get_or_create_user(db, call.from_user)
        action, *params = call.data.split('_')
        
        if action == "refresh":
            client_uuid = params[0]
            client_info = xui_client.get_client(client_uuid)
            
            status_text = (
                f"📊 Updated Client Status:\n"
                f"Email: {client_info['email']}\n"
                f"Traffic: {client_info['used_traffic']}/{client_info['total_traffic']} GB\n"
                f"Expires: {client_info['expire_date']}\n"
                f"Status: {'🟢 Active' if client_info['enable'] else '🔴 Disabled'}"
            )
            
            keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
            bot.edit_message_text(
                status_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
            save_user_activity(db, user.id, "REFRESH_STATUS", client_uuid)
        
        elif action == "traffic" and user.is_admin:
            client_uuid = params[0]
            keyboard = create_traffic_options_keyboard(client_uuid)
            bot.edit_message_text(
                "Select new traffic limit:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
        
        elif action == "expiry" and user.is_admin:
            client_uuid = params[0]
            keyboard = create_expiry_options_keyboard(client_uuid)
            bot.edit_message_text(
                "Select new expiry period:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
        
        elif action == "settraffic" and user.is_admin:
            client_uuid, gb = params
            xui_client.set_traffic(client_uuid, int(gb))
            save_user_activity(db, user.id, "SET_TRAFFIC", client_uuid, {"gb": gb})
            bot.answer_callback_query(call.id, f"Traffic limit set to {gb}GB")
            
            # Refresh status display
            client_info = xui_client.get_client(client_uuid)
            status_text = (
                f"📊 Updated Client Status:\n"
                f"Email: {client_info['email']}\n"
                f"Traffic: {client_info['used_traffic']}/{client_info['total_traffic']} GB\n"
                f"Expires: {client_info['expire_date']}\n"
                f"Status: {'🟢 Active' if client_info['enable'] else '🔴 Disabled'}"
            )
            keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
            bot.edit_message_text(
                status_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
        
        elif action == "setexpiry" and user.is_admin:
            client_uuid, days = params
            xui_client.set_expiry(client_uuid, int(days))
            save_user_activity(db, user.id, "SET_EXPIRY", client_uuid, {"days": days})
            bot.answer_callback_query(call.id, f"Expiry set to {days} days")
            
            # Refresh status display
            client_info = xui_client.get_client(client_uuid)
            status_text = (
                f"📊 Updated Client Status:\n"
                f"Email: {client_info['email']}\n"
                f"Traffic: {client_info['used_traffic']}/{client_info['total_traffic']} GB\n"
                f"Expires: {client_info['expire_date']}\n"
                f"Status: {'🟢 Active' if client_info['enable'] else '🔴 Disabled'}"
            )
            keyboard = create_client_status_keyboard(client_uuid, user.is_admin)
            bot.edit_message_text(
                status_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )

def run_bot():
    print("Bot started...")
    bot.infinity_polling() 