"""core/risk_manager.py"""
import logging
logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, settings):
        self.s = settings

    def calculate_sl_tp(self, price: float, side: str) -> tuple:
        sl = self.s.STOP_LOSS_PCT / 100
        tp = self.s.TAKE_PROFIT_PCT / 100
        if side == "BUY":
            return price * (1 - sl), price * (1 + tp)
        return price * (1 + sl), price * (1 - tp)

    def calculate_trailing_sl(self, price: float, side: str) -> float:
        t = self.s.TRAILING_PCT / 100
        return price * (1 - t) if side == "BUY" else price * (1 + t)

    def check_risk(self, balance: float, daily_pnl: float) -> dict:
        if daily_pnl <= -self.s.MAX_DAILY_LOSS:
            return {"ok": False, "reason": f"Daily loss limit reached: {daily_pnl:.2f} USDT"}
        min_needed = self.s.POSITION_MIN_USDT
        if balance < min_needed:
            return {"ok": False, "reason": f"Balance too low: {balance:.2f} USDT (min {min_needed:.0f})"}
        return {"ok": True, "reason": "OK"}
