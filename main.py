import telebot
import logging
from src.config.config import X_UI_CONFIG, TELEGRAM_CONFIG
from src.api.xui_client import XUIClient
from src.handlers.bot_handlers import BotHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    try:
        # Initialize X-UI client
        xui_client = XUIClient(
            base_url=X_UI_CONFIG["URL"],
            username=X_UI_CONFIG["USERNAME"],
            password=X_UI_CONFIG["PASSWORD"]
        )

        # Initialize Telegram bot
        bot = telebot.TeleBot(TELEGRAM_CONFIG["BOT_TOKEN"])

        # Initialize and register handlers
        handlers = BotHandlers(bot, xui_client)
        handlers.register_handlers()

        logger.info("Bot started successfully!")
        
        # Start the bot
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        # Clean up
        xui_client.close()

if __name__ == "__main__":
    main() 