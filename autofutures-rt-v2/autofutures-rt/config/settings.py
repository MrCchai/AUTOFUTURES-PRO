"""
config/settings.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # ── Binance ───────────────────────────────────────────
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    TESTNET            = os.getenv("TESTNET", "true").lower() == "true"

    # ── Trading ───────────────────────────────────────────
    SYMBOL     = os.getenv("SYMBOL", "BTCUSDT")
    TIMEFRAME  = os.getenv("TIMEFRAME", "15m")   # 1m 5m 15m 1h
    LEVERAGE   = int(os.getenv("LEVERAGE", "5"))
    STRATEGY   = os.getenv("STRATEGY", "TREND")  # TREND | SCALP

    # ── Position Sizing ───────────────────────────────────
    POSITION_ALLOC_PCT = float(os.getenv("POSITION_ALLOC_PCT", "0.80"))  # 80% ของ balance
    POSITION_MIN_USDT  = float(os.getenv("POSITION_MIN_USDT", "10"))     # ขั้นต่ำ 10 USDT
    MAX_POSITIONS      = int(os.getenv("MAX_POSITIONS", "1"))

    # ── Risk ─────────────────────────────────────────────
    STOP_LOSS_PCT   = float(os.getenv("STOP_LOSS_PCT", "1.5"))
    TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "3.0"))
    MAX_DAILY_LOSS  = float(os.getenv("MAX_DAILY_LOSS", "50"))
    TRAILING_STOP   = os.getenv("TRAILING_STOP", "true").lower() == "true"
    TRAILING_PCT    = float(os.getenv("TRAILING_PCT", "0.8"))

    # ── Strategy Params ───────────────────────────────────
    EMA_FAST       = int(os.getenv("EMA_FAST", "20"))
    EMA_SLOW       = int(os.getenv("EMA_SLOW", "50"))
    MACD_FAST      = int(os.getenv("MACD_FAST", "12"))
    MACD_SLOW      = int(os.getenv("MACD_SLOW", "26"))
    MACD_SIG       = int(os.getenv("MACD_SIG", "9"))
    RSI_PERIOD     = int(os.getenv("RSI_PERIOD", "14"))
    RSI_OVERSOLD   = float(os.getenv("RSI_OVERSOLD", "30"))
    RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
    BB_PERIOD      = int(os.getenv("BB_PERIOD", "20"))
    BB_STD         = float(os.getenv("BB_STD", "2.0"))

    # ── Telegram ──────────────────────────────────────────
    TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── Dashboard ─────────────────────────────────────────
    DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
    DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "changeme")  # password เข้า dashboard

    def validate(self):
        assert self.BINANCE_API_KEY,    "❌ BINANCE_API_KEY missing"
        assert self.BINANCE_API_SECRET, "❌ BINANCE_API_SECRET missing"
        assert self.LEVERAGE <= 20,     "❌ Leverage > 20x"
        print("✅ Settings OK")
