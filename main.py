import telebot
from config import X_UI_URL, X_UI_USERNAME, X_UI_PASSWORD, BOT_TOKEN
from xui_client import XUIClient
from bot_handlers import BotHandlers

def main():
    # Initialize X-UI client
    xui_client = XUIClient(X_UI_URL, X_UI_USERNAME, X_UI_PASSWORD)

    # Initialize Telegram bot
    bot = telebot.TeleBot(BOT_TOKEN)

    # Initialize and register handlers
    handlers = BotHandlers(bot, xui_client)
    handlers.register_handlers()

    try:
        # Start the bot
        print("Bot started successfully!")
        bot.polling()
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        # Clean up
        xui_client.close()

if __name__ == "__main__":
    main()