import os
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env-lis")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_notification(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Warning: Telegram bot token or chat ID is not set. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("Telegram notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to send Telegram notification: {e}")

def send_photo(photo_path, caption=""):
    """Sends a photo with a caption to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Warning: Telegram bot token or chat ID is not set. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            print("Telegram photo sent successfully.")
    except FileNotFoundError:
        print(f"Error: Screenshot file not found at {photo_path}")
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to send Telegram photo: {e}")