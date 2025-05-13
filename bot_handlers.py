from datetime import datetime
import telebot
from utils import (
    save_user_info,
    extract_email_from_vless_link,
    format_remaining_days,
    convert_bytes,
    format_total,
    get_tehran_time
)
from xui_client import XUIClient

class BotHandlers:
    def __init__(self, bot: telebot.TeleBot, xui_client: XUIClient):
        self.bot = bot
        self.xui_client = xui_client

    def register_handlers(self):
        """Register all bot handlers."""
        self.bot.message_handler(commands=['start'])(self.send_welcome)
        self.bot.message_handler(func=lambda message: True)(self.handle_vless_link)

    def send_welcome(self, message):
        """Handle /start command."""
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        username = message.from_user.username
        chat_id = message.chat.id
        
        save_user_info(chat_id, first_name, last_name, username)
        text_bold = "*درود کاربر عزیز*\n*به ربات پشتیبانی ما خوش آمدید*\n*برای اطلاعات از مشخصات سرویس فعال خود، لینک را ارسال بفرمایید*"
        self.bot.send_message(chat_id, text_bold, parse_mode='MarkdownV2')

    def handle_vless_link(self, message):
        """Handle VLESS link messages."""
        try:
            chat_id = message.chat.id
            vless_link = message.text
            email_from_vless = extract_email_from_vless_link(vless_link)
            
            # Save user info
            first_name = message.from_user.first_name
            last_name = message.from_user.last_name
            username = message.from_user.username
            save_user_info(chat_id, first_name, last_name, username, email_from_vless)

            # Get traffic data
            traffics_data = self.xui_client.get_client_traffics(email_from_vless)
            if traffics_data:
                self._display_client_traffics(traffics_data, chat_id)
            else:
                self.bot.send_message(chat_id, "لینک ارسال شده معتبر نمیباشد⭕\nلطفا مجددا بررسی و لینک خود را ارسال بفرمایید")
        except Exception as e:
            self.bot.send_message(chat_id, "لینک ارسال شده معتبر نمیباشد⭕\nلطفا مجددا بررسی و لینک خود را ارسال بفرمایید")

    def _display_client_traffics(self, traffics, chat_id):
        """Display client traffic information."""
        down_bytes = traffics['obj']['down']
        up_bytes = traffics['obj']['up']
        formatted_remaining_days = format_remaining_days(traffics['obj']['expiryTime'])
        formatted_total = format_total(traffics['obj']['total'])
        
        _, _, down_gb = convert_bytes(down_bytes)
        _, _, up_gb = convert_bytes(up_bytes)
        total_use = down_gb + up_gb

        Enable = traffics['obj']['enable']
        Enable = "فعال 🟢" if Enable else "غیرفعال 🔴"

        if traffics['obj']['total'] == 0:
            formatted_total = "نامحدود"

        if traffics['obj']['expiryTime'] <= int(datetime.now().timestamp() * 1000):
            formatted_remaining_days = "فاقد تاریخ انقضا"

        info_message = (
            f"وضعیت : {Enable}\n"
            f"🔼آپلود : {up_gb:.2f} GB\n"
            f"🔽دانلود : {down_gb:.2f} GB\n"
            f"➕مصرف کلی : {total_use:.2f} GB\n"
            f"🟥حجم خریداری شده : {formatted_total}\n"
            f"📅انقضا : {formatted_remaining_days}\n"
            f"\n⏳آخرین آپدیت مقادیر : {get_tehran_time()}"
        )

        self.bot.send_message(chat_id, info_message) 