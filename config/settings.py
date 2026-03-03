import os
from dotenv import load_dotenv
load_dotenv()
class Settings:
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
    SYMBOL = os.getenv("SYMBOL", "DOGEUSDT")
    TIMEFRAME = os.getenv("TIMEFRAME", "1m")
    LEVERAGE = int(os.getenv("LEVERAGE", "20"))
    POSITION_ALLOC_PCT = float(os.getenv("POSITION_ALLOC_PCT", "0.7"))
    POSITION_MIN_USDT = float(os.getenv("POSITION_MIN_USDT", "5"))
    STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "1.5"))
    TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.8"))
    TRAILING_STOP = os.getenv("TRAILING_STOP", "true").lower() == "true"
    TRAILING_PCT = float(os.getenv("TRAILING_PCT", "0.3"))
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    DASHBOARD_HOST = "0.0.0.0"
    DASHBOARD_PORT = 8080
