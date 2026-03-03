import requests
class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
    def send(self, msg):
        try: requests.post(self.url, json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass
