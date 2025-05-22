from datetime import datetime
import telebot
from typing import Optional
import uuid

from ..utils.formatting import (
    format_traffic,
    format_client_ips,
    format_online_clients,
    format_client_info
)
from ..api.xui_client import XUIClient
from ..utils.validators import is_valid_email, is_valid_uuid
from ..models.client import Client

class BotHandlers:
    def __init__(self, bot: telebot.TeleBot, xui_client: XUIClient):
        self.bot = bot
        self.xui_client = xui_client

    def register_handlers(self):
        """Register all bot handlers."""
        self.bot.message_handler(commands=['start'])(self.send_welcome)
        self.bot.message_handler(commands=['help'])(self.send_help)
        self.bot.message_handler(commands=['backup'])(self.create_backup)
        self.bot.message_handler(commands=['ips'])(self.get_client_ips)
        self.bot.message_handler(commands=['online'])(self.get_online_clients)
        self.bot.message_handler(commands=['reset'])(self.reset_traffic)
        self.bot.message_handler(commands=['add'])(self.add_client)
        self.bot.message_handler(commands=['update'])(self.update_client)
        self.bot.message_handler(func=lambda message: True)(self.handle_vless_link)

    def send_welcome(self, message):
        """Handle /start command."""
        chat_id = message.chat.id
        text = (
            "*درود کاربر عزیز*\n"
            "*به ربات پشتیبانی ما خوش آمدید*\n"
            "*برای مشاهده دستورات از /help استفاده کنید*"
        )
        self.bot.send_message(chat_id, text, parse_mode='MarkdownV2')

    def send_help(self, message):
        """Handle /help command."""
        chat_id = message.chat.id
        help_text = (
            "🤖 *راهنمای ربات X\\-UI*\n"
            "━━━━━━━━━━━━━━\n\n"
            "*دستورات اصلی:*\n"
            "🔹 `VLESS لینک`: مشاهده اطلاعات سرویس\n"
            "🔹 `/start`: شروع کار با ربات\n"
            "🔹 `/help`: نمایش این راهنما\n\n"
            
            "*مدیریت کاربران:*\n"
            "🔹 `/add` \\[email\\] \\[GB\\] \\[days\\]: افزودن کاربر\n"
            "🔹 `/update` \\[email\\] \\[GB\\] \\[days\\]: بروزرسانی\n"
            "🔹 `/reset` \\[email\\] \\[inbound\\_id\\]: ریست ترافیک\n\n"
            
            "*نظارت و گزارش:*\n"
            "🔹 `/ips` \\[email\\]: نمایش IP های فعال\n"
            "🔹 `/online`: کاربران آنلاین\n"
            "🔹 `/backup`: تهیه نسخه پشتیبان\n\n"
            
            "*مثال ها:*\n"
            "\\- افزودن کاربر با 10GB و 30 روز:\n"
            "`/add user1 10 30`\n\n"
            "\\- بروزرسانی کاربر:\n"
            "`/update user1 20 60`\n\n"
            "\\- ریست ترافیک کاربر:\n"
            "`/reset user1@example.com 1`\n\n"
            
            "⚠️ *نکته:* _تمامی مقادیر باید به انگلیسی وارد شوند_"
        )
        self.bot.send_message(chat_id, help_text, parse_mode='MarkdownV2')

    def create_backup(self, message):
        """Handle /backup command."""
        chat_id = message.chat.id
        if self.xui_client.create_backup():
            self.bot.reply_to(message, "✅ نسخه پشتیبان با موفقیت ایجاد شد")
        else:
            self.bot.reply_to(message, "❌ خطا در ایجاد نسخه پشتیبان")

    def get_client_ips(self, message):
        """Handle /ips command."""
        chat_id = message.chat.id
        try:
            email = message.text.split()[1]
            if not is_valid_email(email):
                self.bot.reply_to(message, "❌ ایمیل نامعتبر است")
                return

            ips_data = self.xui_client.get_client_ips(email)
            if ips_data:
                formatted_ips = format_client_ips(ips_data)
                self.bot.reply_to(message, formatted_ips)
            else:
                self.bot.reply_to(message, "❌ اطلاعاتی یافت نشد")
        except IndexError:
            self.bot.reply_to(message, "❌ لطفا ایمیل کاربر را وارد کنید")

    def get_online_clients(self, message):
        """Handle /online command."""
        chat_id = message.chat.id
        online_data = self.xui_client.get_online_clients()
        if online_data:
            formatted_online = format_online_clients(online_data)
            self.bot.reply_to(message, formatted_online)
        else:
            self.bot.reply_to(message, "❌ خطا در دریافت اطلاعات کاربران آنلاین")

    def reset_traffic(self, message):
        """Handle /reset command."""
        chat_id = message.chat.id
        try:
            # Parse command: /reset email inbound_id
            parts = message.text.split()
            if len(parts) < 3:
                self.bot.reply_to(message, "❌ فرمت دستور نادرست است\nمثال: /reset email@example.com 1")
                return
                
            _, email, inbound_id = parts
            inbound_id = int(inbound_id)
            
            if self.xui_client.reset_client_traffic(inbound_id, email):
                self.bot.reply_to(message, f"✅ ترافیک کاربر {email} با موفقیت ریست شد")
            else:
                self.bot.reply_to(message, "❌ خطا در ریست ترافیک")
        except ValueError:
            self.bot.reply_to(message, "❌ فرمت دستور نادرست است\nمثال: /reset email@example.com 1")
        except Exception as e:
            self.bot.reply_to(message, f"❌ خطا در ریست ترافیک: {str(e)}")

    def add_client(self, message):
        """Handle /add command."""
        chat_id = message.chat.id
        try:
            _, email, gb, days, inbound_id = message.text.split()
            gb = int(gb)
            days = int(days)
            inbound_id = int(inbound_id)

            if not is_valid_email(email):
                self.bot.reply_to(message, "❌ ایمیل نامعتبر است")
                return

            total_gb = gb * 1024 * 1024 * 1024  # Convert GB to bytes
            expiry_time = int((datetime.now().timestamp() + days * 86400) * 1000)
            new_uuid = str(uuid.uuid4())

            result = self.xui_client.add_client(
                inbound_id=inbound_id,
                email=email,
                uuid=new_uuid,
                total_gb=total_gb,
                expiry_time=expiry_time
            )

            if result:
                self.bot.reply_to(message, f"✅ کاربر {email} با موفقیت اضافه شد")
            else:
                self.bot.reply_to(message, "❌ خطا در افزودن کاربر")
        except ValueError:
            self.bot.reply_to(message, "❌ فرمت دستور نادرست است\nمثال: /add email@example.com 10 30 1")

    def update_client(self, message):
        """Handle /update command."""
        chat_id = message.chat.id
        try:
            _, uuid, email, gb, days, inbound_id = message.text.split()
            gb = int(gb)
            days = int(days)
            inbound_id = int(inbound_id)

            if not is_valid_uuid(uuid):
                self.bot.reply_to(message, "❌ UUID نامعتبر است")
                return

            if not is_valid_email(email):
                self.bot.reply_to(message, "❌ ایمیل نامعتبر است")
                return

            total_gb = gb * 1024 * 1024 * 1024  # Convert GB to bytes
            expiry_time = int((datetime.now().timestamp() + days * 86400) * 1000)

            result = self.xui_client.update_client(
                inbound_id=inbound_id,
                uuid=uuid,
                email=email,
                total_gb=total_gb,
                expiry_time=expiry_time
            )

            if result:
                self.bot.reply_to(message, f"✅ کاربر {email} با موفقیت بروزرسانی شد")
            else:
                self.bot.reply_to(message, "❌ خطا در بروزرسانی کاربر")
        except ValueError:
            self.bot.reply_to(message, "❌ فرمت دستور نادرست است\nمثال: /update UUID email@example.com 10 30 1")

    def handle_vless_link(self, message):
        """Handle VLESS link messages."""
        chat_id = message.chat.id
        try:
            vless_link = message.text
            email = self._extract_email_from_vless(vless_link)
            
            if not email:
                self.bot.reply_to(message, "❌ لینک VLESS نامعتبر است")
                return

            traffics_data = self.xui_client.get_client_traffics(email)
            if traffics_data:
                formatted_info = format_client_info(traffics_data)
                self.bot.reply_to(message, formatted_info)
            else:
                self.bot.reply_to(message, "❌ اطلاعاتی یافت نشد")
        except Exception as e:
            self.bot.reply_to(message, "❌ خطا در پردازش لینک")

    def _extract_email_from_vless(self, vless_link: str) -> Optional[str]:
        """Extract email from VLESS link."""
        import re
        match = re.search(r'-([A-Za-z0-9]+)$', vless_link)
        return match.group(1) if match else None 