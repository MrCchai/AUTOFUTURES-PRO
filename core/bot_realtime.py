import asyncio, json, time, logging, pandas as pd, websockets
from collections import deque
from datetime import datetime
from binance.client import Client
from config.settings import Settings
from strategies.doge_scalper import DogeScalperStrategy
from utils.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

class RealtimeBot:
    def __init__(self, settings):
        self.s = settings
        self.telegram = TelegramNotifier(settings.TELEGRAM_TOKEN, settings.TELEGRAM_CHAT_ID)
        self.client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)
        self.strategy = DogeScalperStrategy(settings)
        self.candles = deque(maxlen=200)
        self.current_price = 0.0
        self.balance = 0.0
        self.position = None
        self.logs = deque(maxlen=50)
        self.history = []
        self._callbacks = []

    def register_callback(self, cb): self._callbacks.append(cb)

    def get_state(self):
        return {
            "price": self.current_price, "balance": round(self.balance, 2),
            "position": self.position, "logs": list(self.logs),
            "history": self.history[-10:], "candles": list(self.candles)[-100:]
        }

    async def start(self):
        await self._load_history()
        self.telegram.send("🐶 *DOGE-RAPID-FIRE V14 Started*")
        asyncio.create_task(self._fetch_account())
        await self._ws_loop()

    async def _fetch_account(self):
        while True:
            try:
                acc = self.client.futures_account()
                self.balance = float(acc["totalWalletBalance"])
                pos = self.client.futures_position_information(symbol=self.s.SYMBOL)
                self.position = next((p for p in pos if float(p["positionAmt"]) != 0), None)
                for cb in self._callbacks: await cb(self.get_state())
                await asyncio.sleep(30)
            except: await asyncio.sleep(30)

    async def _ws_loop(self):
        url = f"wss://fstream.binance.com/stream?streams={self.s.SYMBOL.lower()}@aggTrade/{self.s.SYMBOL.lower()}@kline_{self.s.TIMEFRAME}"
        async with websockets.connect(url) as ws:
            async for raw in ws:
                data = json.loads(raw)["data"]
                if data["e"] == "aggTrade": self.current_price = float(data["p"])
                elif data["e"] == "kline" and data["k"]["x"]: await self._analyze()

    async def _analyze(self):
        df = pd.DataFrame(list(self.candles))
        res = self.strategy.analyze(df)
        self.logs.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "msg": res["reason"]})
        if res["action"] in ["BUY", "SELL"] and not self.position:
            self._execute(res["action"])
        elif res["action"] == "CLOSE" and self.position:
            self._execute_close(res["reason"])

    def _execute(self, side):
        qty = round((self.balance * self.s.POSITION_ALLOC_PCT * self.s.LEVERAGE) / self.current_price, 0)
        try:
            self.client.futures_create_order(symbol=self.s.SYMBOL, side=side, type="MARKET", quantity=qty)
            self.history.append({"time": datetime.now().strftime("%H:%M:%S"), "side": side, "price": self.current_price})
            self.telegram.send(f"🟢 *OPEN {side}* @ {self.current_price}")
        except Exception as e: self.logs.appendleft({"time": "ERR", "msg": str(e)})

    def _execute_close(self, reason):
        amt = float(self.position["positionAmt"])
        side = "SELL" if amt > 0 else "BUY"
        try:
            self.client.futures_create_order(symbol=self.s.SYMBOL, side=side, type="MARKET", quantity=abs(amt), reduceOnly="true")
            self.telegram.send(f"✅ *CLOSED* | {reason}")
        except Exception as e: self.logs.appendleft({"time": "ERR", "msg": str(e)})

    async def _load_history(self):
        raw = self.client.futures_klines(symbol=self.s.SYMBOL, interval=self.s.TIMEFRAME, limit=200)
        for r in raw: self.candles.append({"open_time": r[0], "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])})
