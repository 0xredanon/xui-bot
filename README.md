# X-UI Telegram Bot

A Telegram bot for monitoring X-UI VPN service usage and statistics.

## Features

- Monitor VPN service status
- Track upload and download usage
- Check remaining days of service
- View total data allocation
- User information logging

## Project Structure

```
.
├── README.md
├── requirements.txt
├── config.py           # Configuration settings
├── main.py            # Main application entry point
├── xui_client.py      # X-UI API client
├── bot_handlers.py    # Telegram bot handlers
└── utils.py           # Utility functions
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the bot:
- Update `config.py` with your X-UI server details and Telegram bot token

3. Run the bot:
```bash
python main.py
```

## Usage

1. Start the bot by sending `/start`
2. Send your VLESS link to check service status
3. The bot will respond with:
   - Service status (active/inactive)
   - Upload usage
   - Download usage
   - Total usage
   - Data allocation
   - Expiry date
   - Last update time

## Requirements

- Python 3.7+
- pyTelegramBotAPI
- requests
- pytz 