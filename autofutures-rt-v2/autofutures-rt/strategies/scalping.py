"""
strategies/scalping.py — RSI + Bollinger Bands
"""
import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class ScalpingStrategy:
    def __init__(self, settings):
        self.s = settings

    def analyze(self, df: pd.DataFrame) -> dict:
        try:
            s = self.s
            df["rsi"] = ta.rsi(df["close"], length=s.RSI_PERIOD)
            bb = ta.bbands(df["close"], length=s.BB_PERIOD, std=s.BB_STD)
            df["bb_upper"] = bb[f"BBU_{s.BB_PERIOD}_{s.BB_STD}"]
            df["bb_mid"]   = bb[f"BBM_{s.BB_PERIOD}_{s.BB_STD}"]
            df["bb_lower"] = bb[f"BBL_{s.BB_PERIOD}_{s.BB_STD}"]
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

            curr = df.iloc[-1]
            rsi, close = float(curr["rsi"]), float(curr["close"])
            bb_upper, bb_lower = float(curr["bb_upper"]), float(curr["bb_lower"])
            bb_width = float(curr["bb_width"])

            indicators = {
                "rsi":      round(rsi, 1),
                "bb_upper": round(bb_upper, 2),
                "bb_mid":   round(float(curr["bb_mid"]), 2),
                "bb_lower": round(bb_lower, 2),
                "bb_width": round(bb_width, 4),
            }

            if rsi < s.RSI_OVERSOLD and close <= bb_lower * 1.002:
                return {"action": "BUY",  "reason": f"RSI oversold ({rsi:.1f}) + BB lower", "indicators": indicators}
            if rsi > s.RSI_OVERBOUGHT and close >= bb_upper * 0.998:
                return {"action": "SELL", "reason": f"RSI overbought ({rsi:.1f}) + BB upper", "indicators": indicators}
            if 45 <= rsi <= 55:
                return {"action": "CLOSE", "reason": f"RSI neutral ({rsi:.1f})", "indicators": indicators}

            return {"action": "HOLD", "reason": f"No signal | RSI={rsi:.1f}", "indicators": indicators}

        except Exception as e:
            logger.error(f"Scalping error: {e}", exc_info=True)
            return {"action": "HOLD", "reason": str(e), "indicators": {}}
