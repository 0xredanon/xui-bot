# 🤖 XUI Bot v2.0

A powerful Telegram bot for managing X-UI panel with advanced features and robust error handling.

## ✨ Features

### 🛡️ Security
- Advanced authentication system
- Rate limiting and flood protection
- Secure backup system with encryption
- IP-based access control
- Session management

### 📊 User Management
- User registration and verification
- Role-based access control (Admin/User)
- User activity tracking
- Usage statistics and monitoring
- Custom user states and workflows

### 🔧 Panel Management
- Real-time panel status monitoring
- Automated backup system
- Traffic monitoring and statistics
- Client management
- Server resource monitoring

### 💾 Database Features
- Automatic database backups
- Data integrity checks
- Migration system
- Query optimization
- Connection pooling

### 📱 Bot Features
- Interactive menus and keyboards
- Multi-language support
- Rich media messages
- Command handling
- Callback query support

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/xui-bot.git
cd xui-bot
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Initialize the database:
```bash
python -m src.database.migrations
```

6. Run the bot:
```bash
python main.py
```

## ⚙️ Configuration

### Environment Variables
- `BOT_TOKEN`: Your Telegram bot token
- `ADMIN_ID`: Admin's Telegram ID
- `DB_HOST`: Database host
- `DB_PORT`: Database port
- `DB_NAME`: Database name
- `DB_USER`: Database user
- `DB_PASS`: Database password
- `PANEL_URL`: X-UI panel URL
- `PANEL_USERNAME`: Panel username
- `PANEL_PASSWORD`: Panel password

### Database Configuration
The bot uses SQLAlchemy ORM with MySQL/MariaDB. Configure your database settings in `.env` file.

## 📁 Project Structure

```
xui-bot/
├── src/
│   ├── handlers/         # Bot command handlers
│   ├── models/          # Database models
│   ├── utils/           # Utility functions
│   ├── database/        # Database management
│   └── config.py        # Configuration
├── migrations/          # Database migrations
├── backups/            # Backup storage
├── logs/               # Log files
├── tests/              # Test files
├── main.py            # Entry point
├── requirements.txt    # Dependencies
└── README.md          # Documentation
```

## 🔄 Database Migrations

The bot includes a migration system for database schema updates:

```bash
# Run all pending migrations
python -m src.database.migrations

# Create new migration
python -m src.database.migrations create_migration
```

## 📊 Monitoring

The bot includes comprehensive monitoring features:

- User activity tracking
- System resource monitoring
- Error logging and reporting
- Performance metrics
- Backup status monitoring

## 🔒 Security Features

- Rate limiting
- IP blocking
- Session management
- Secure password handling
- Backup encryption

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [X-UI Panel](https://github.com/vaxilu/x-ui)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [SQLAlchemy](https://www.sqlalchemy.org/)

## 📞 Support

For support, please open an issue in the GitHub repository or contact the maintainers.

## 🔄 Updates

### v2.0.0
- Complete rewrite with improved architecture
- Enhanced security features
- Advanced backup system
- Improved error handling
- Better user management
- Real-time monitoring
- Migration system
- Performance optimizations

### v1.5.0
- Initial public release
- Basic bot functionality
- User management
- Panel integration
- Backup system 