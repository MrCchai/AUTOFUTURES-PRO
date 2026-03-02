"""utils/telegram.py"""
import logging, requests
logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, chat_id
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, msg: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            r = requests.post(self.url, json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
            return r.ok
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
