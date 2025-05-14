# XUI Telegram Bot V1.4.1(Security Patch)🤖

A powerful Telegram bot for managing XUI VPN panel with advanced features and real-time monitoring capabilities.

[🇮🇷 راهنمای فارسی](#راهنمای-فارسی)

## Features ✨

### Admin Features 👑
- Real-time system monitoring (`/system`)
- User traffic management and statistics
- Automated backup system with scheduling
- Broadcast messages to users
- Detailed logging and monitoring
- User management and control

### User Features 👤
- View VPN connection status
- Monitor traffic usage
- Check account expiry
- Real-time statistics
- Easy subscription management

## Installation 🚀

1. Clone the repository:
```bash
git clone https://github.com/yourusername/xui-bot.git
cd xui-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the bot:
```bash
python main.py
```

## Configuration ⚙️

Required environment variables:
```
BOT_TOKEN=your_telegram_bot_token
PANEL_URL=your_xui_panel_url
PANEL_USERNAME=admin_username
PANEL_PASSWORD=admin_password
DB_HOST=localhost
DB_USER=dbuser
DB_PASSWORD=dbpassword
DB_NAME=xuibot
```

## Commands 📝

### Admin Commands
- `/system` - View system status and resources
- `/users` - List online users
- `/broadcast` - Send message to all users
- `/backup` - Create system backup
- `/logs` - View system logs

### User Commands
- `/start` - Start the bot
- `/help` - Show help message
- `/info` - Show account information
- `/usage` - Check traffic usage

## Contributing 🤝

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

# راهنمای فارسی

## ربات تلگرام XUI V1.4.0 (Security patch)🤖

یک ربات قدرتمند تلگرام برای مدیریت پنل XUI VPN با قابلیت‌های پیشرفته و نظارت بلادرنگ.

## امکانات ✨

### امکانات مدیر 👑
- نظارت بلادرنگ سیستم (`/system`)
- مدیریت ترافیک و آمار کاربران
- سیستم پشتیبان‌گیری خودکار
- ارسال پیام به کاربران
- ثبت جزئیات و نظارت
- مدیریت و کنترل کاربران

### امکانات کاربران 👤
- مشاهده وضعیت اتصال VPN
- نظارت بر مصرف ترافیک
- بررسی تاریخ انقضا
- آمار بلادرنگ
- مدیریت آسان اشتراک

## نصب و راه‌اندازی 🚀

1. کلون کردن مخزن:
```bash
git clone https://github.com/yourusername/xui-bot.git
cd xui-bot
```

2. نصب وابستگی‌ها:
```bash
pip install -r requirements.txt
```

3. تنظیم متغیرهای محیطی:
```bash
cp .env.example .env
# ویرایش فایل .env با تنظیمات خود
```

4. اجرای مهاجرت‌های پایگاه داده:
```bash
alembic upgrade head
```

5. اجرای ربات:
```bash
python main.py
```

## پیکربندی ⚙️

متغیرهای محیطی مورد نیاز:
```
BOT_TOKEN=توکن_ربات_تلگرام
PANEL_URL=آدرس_پنل_شما
PANEL_USERNAME=نام_کاربری_ادمین
PANEL_PASSWORD=رمز_عبور_ادمین
DB_HOST=localhost
DB_USER=نام_کاربری_دیتابیس
DB_PASSWORD=رمز_عبور_دیتابیس
DB_NAME=نام_دیتابیس
```

## دستورات ربات 📝

### دستورات مدیر
- `/system` - مشاهده وضعیت و منابع سیستم
- `/users` - لیست کاربران آنلاین
- `/broadcast` - ارسال پیام به همه کاربران
- `/backup` - ایجاد پشتیبان سیستم
- `/logs` - مشاهده لاگ‌های سیستم

### دستورات کاربران
- `/start` - شروع کار با ربات
- `/help` - نمایش راهنما
- `/info` - نمایش اطلاعات حساب
- `/usage` - بررسی مصرف ترافیک

## پشتیبانی 💬
برای گزارش مشکلات یا پیشنهادات، لطفاً یک Issue ایجاد کنید.

## مجوز 📄
این پروژه تحت مجوز MIT منتشر شده است - برای جزئیات بیشتر فایل [LICENSE](LICENSE) را مشاهده کنید. 