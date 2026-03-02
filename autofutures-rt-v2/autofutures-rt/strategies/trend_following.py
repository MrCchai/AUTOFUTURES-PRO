"""
strategies/trend_following.py — EMA Cross + MACD
คืน indicators dict เพิ่มเติมสำหรับ Dashboard
"""
import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class TrendFollowingStrategy:
    def __init__(self, settings):
        self.s = settings

    def analyze(self, df: pd.DataFrame) -> dict:
        try:
            s = self.s
            df["ema_fast"] = ta.ema(df["close"], length=s.EMA_FAST)
            df["ema_slow"] = ta.ema(df["close"], length=s.EMA_SLOW)

            macd = ta.macd(df["close"], fast=s.MACD_FAST, slow=s.MACD_SLOW, signal=s.MACD_SIG)
            col_macd = f"MACD_{s.MACD_FAST}_{s.MACD_SLOW}_{s.MACD_SIG}"
            col_sig  = f"MACDs_{s.MACD_FAST}_{s.MACD_SLOW}_{s.MACD_SIG}"
            col_hist = f"MACDh_{s.MACD_FAST}_{s.MACD_SLOW}_{s.MACD_SIG}"
            df["macd"] = macd[col_macd]
            df["macd_signal"] = macd[col_sig]
            df["macd_hist"]   = macd[col_hist]

            # RSI เสริม
            df["rsi"] = ta.rsi(df["close"], length=14)

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            ema_bull_cross = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
            ema_bear_cross = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]
            macd_bull      = curr["macd"] > curr["macd_signal"] and curr["macd_hist"] > 0
            macd_bear      = curr["macd"] < curr["macd_signal"] and curr["macd_hist"] < 0
            above_ema      = curr["close"] > curr["ema_slow"]
            below_ema      = curr["close"] < curr["ema_slow"]

            indicators = {
                "ema_fast":    round(float(curr["ema_fast"]), 2),
                "ema_slow":    round(float(curr["ema_slow"]), 2),
                "macd":        round(float(curr["macd"]), 4),
                "macd_signal": round(float(curr["macd_signal"]), 4),
                "macd_hist":   round(float(curr["macd_hist"]), 4),
                "rsi":         round(float(curr["rsi"]), 1),
            }

            if ema_bull_cross and macd_bull and above_ema:
                return {"action": "BUY",  "reason": f"EMA{s.EMA_FAST} cross UP + MACD bullish", "indicators": indicators}
            if ema_bear_cross and macd_bear and below_ema:
                return {"action": "SELL", "reason": f"EMA{s.EMA_FAST} cross DOWN + MACD bearish", "indicators": indicators}
            if ema_bear_cross:
                return {"action": "CLOSE", "reason": "EMA bearish cross", "indicators": indicators}
            if ema_bull_cross:
                return {"action": "CLOSE", "reason": "EMA bullish cross", "indicators": indicators}

            return {"action": "HOLD", "reason": f"No signal | RSI={curr['rsi']:.1f}", "indicators": indicators}

        except Exception as e:
            logger.error(f"Strategy error: {e}", exc_info=True)
            return {"action": "HOLD", "reason": str(e), "indicators": {}}
