import pandas_ta as ta
class DogeScalperStrategy:
    def __init__(self, settings): self.s = settings
    def analyze(self, df):
        df["rsi"] = ta.rsi(df["close"], length=7)
        bb = ta.bbands(df["close"], length=20, std=2.0)
        curr = df.iloc[-1]
        rsi, close = float(curr["rsi"]), float(curr["close"])
        bbu, bbl = float(bb.iloc[-1, 2]), float(bb.iloc[-1, 0])
        indicators = {"rsi": round(rsi, 2), "bbl": round(bbl, 5), "bbu": round(bbu, 5)}
        if rsi < 30 and close <= bbl * 1.001: return {"action": "BUY", "reason": "DOGE Oversold", "indicators": indicators}
        if rsi > 70 and close >= bbu * 0.999: return {"action": "SELL", "reason": "DOGE Overbought", "indicators": indicators}
        if 48 <= rsi <= 52: return {"action": "CLOSE", "reason": "DOGE Neutral", "indicators": indicators}
        return {"action": "HOLD", "reason": "Waiting", "indicators": indicators}
