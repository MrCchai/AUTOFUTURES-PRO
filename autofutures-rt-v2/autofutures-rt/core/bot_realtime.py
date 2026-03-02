"""
core/bot_realtime.py — หัวใจของ Real-time Bot (Updated with Auto Status & Trailing Stop)

ใช้ asyncio + websockets เชื่อมต่อ Binance Stream โดยตรง:
  - aggTrade stream  → ราคาปัจจุบัน ทุก trade
  - kline stream     → แท่งเทียน (OHLCV) ที่กำลัง update แบบ live

เมื่อแท่งเทียน "ปิด" (kline.x == true) → วิเคราะห์ signal → execute order
"""
import asyncio
import json
import time
import logging
import pandas as pd
from collections import deque
from datetime import datetime

import websockets
from binance.client import Client
from binance.exceptions import BinanceAPIException

from strategies.trend_following import TrendFollowingStrategy
from strategies.scalping import ScalpingStrategy
from core.risk_manager import RiskManager
from utils.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

# Binance WebSocket URLs
WS_BASE      = "wss://fstream.binance.com/stream?streams="
WS_BASE_TEST = "wss://stream.binancefuture.com/stream?streams="


class RealtimeBot:
    def __init__(self, settings):
        self.settings  = settings
        self.risk_mgr  = RiskManager(settings)
        self.telegram  = TelegramNotifier(settings.TELEGRAM_TOKEN, settings.TELEGRAM_CHAT_ID)

        # REST client
        self.client = Client(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET,
            testnet=settings.TESTNET
        )

        # Strategy
        if settings.STRATEGY == "SCALP":
            self.strategy = ScalpingStrategy(settings)
        else:
            self.strategy = TrendFollowingStrategy(settings)

        # State
        self.candles: deque = deque(maxlen=200)
        self.current_price: float = 0.0
        self.current_position: dict | None = None
        self.daily_pnl: float = 0.0
        self.trade_count: int = 0
        self.is_running: bool = False
        self.last_signal: str = "HOLD"
        self.last_signal_time: str = ""
        self.indicators: dict = {}
        self.trade_history: list = []
        self.connected: bool = False
        self.reconnect_count: int = 0
        
        # Trailing Stop State
        self.trailing_sl_price: float = 0.0

        # Callbacks สำหรับส่งข้อมูลไปยัง Dashboard
        self._dashboard_callbacks: list = []

    def register_dashboard_callback(self, cb):
        self._dashboard_callbacks.append(cb)

    def get_state(self) -> dict:
        balance = self._safe_get_balance()
        return {
            "price":         self.current_price,
            "symbol":        self.settings.SYMBOL,
            "strategy":      self.settings.STRATEGY,
            "timeframe":     self.settings.TIMEFRAME,
            "leverage":      self.settings.LEVERAGE,
            "is_running":    self.is_running,
            "connected":     self.connected,
            "testnet":       self.settings.TESTNET,
            "balance":       balance,
            "daily_pnl":     self.daily_pnl,
            "trade_count":   self.trade_count,
            "last_signal":   self.last_signal,
            "last_signal_time": self.last_signal_time,
            "position":      self.current_position,
            "indicators":    self.indicators,
            "trade_history": self.trade_history[-20:],
            "candles":       list(self.candles)[-60:],
            "reconnect_count": self.reconnect_count,
            "trailing_sl":   self.trailing_sl_price,
            "timestamp":     int(time.time() * 1000),
        }

    async def start(self):
        logger.info("Loading historical candles...")
        await self._load_historical_candles()

        self.is_running = True
        try:
            self.client.futures_change_leverage(
                symbol=self.settings.SYMBOL,
                leverage=self.settings.LEVERAGE
            )
        except Exception as e:
            logger.warning(f"Leverage change info: {e}")

        mode_str = 'TESTNET' if self.settings.TESTNET else '🔴 LIVE'
        self.telegram.send(
            f"🚀 *Realtime Bot Started*\n"
            f"Symbol: `{self.settings.SYMBOL}`\n"
            f"Strategy: `{self.settings.STRATEGY}`\n"
            f"Mode: `{mode_str}`"
        )

        # Start Status Report Loop
        asyncio.create_task(self._status_report_loop())
        
        # Start WebSocket Loop
        await self._ws_loop()

    async def _status_report_loop(self):
        """รายงานสถานะทุกๆ 30 นาที"""
        logger.info("Starting Status Report Loop (30m interval)")
        while self.is_running:
            try:
                await asyncio.sleep(30 * 60)
                await self._send_pretty_status()
            except Exception as e:
                logger.error(f"Status loop error: {e}")
                await asyncio.sleep(60)

    async def _send_pretty_status(self):
        """ส่งรายงานสถานะสวยๆ ไป Telegram"""
        bal = self._safe_get_balance()
        pos = await asyncio.to_thread(self._get_position)
        self.current_position = pos
        
        status = "*HOLDING*" if pos else "*IDLE (WAITING SIGNAL)*"
        pnl = float(pos.get("unRealizedProfit", 0)) if pos else 0.0
        roe = 0.0
        if pos:
            entry = float(pos.get("entryPrice", 0))
            side  = 1 if float(pos.get("positionAmt", 0)) > 0 else -1
            if entry > 0:
                roe = (self.current_price - entry) / entry * 100 * self.settings.LEVERAGE * side

        now = datetime.now().strftime("%H:%M:%S")
        report = [
            "📊 *AutoFutures Status Report*",
            "──────────────────",
            f"Daily PnL: `+{self.daily_pnl:,.2f} USDT`",
            f"Symbol: `{self.settings.SYMBOL}` | Price: `{self.current_price:,.2f}`",
            f"Status: {status}",
            f"ROE%: `{roe:+.2f}%` | PnL: `{pnl:+.2f} USDT`" if pos else "",
            f"Balance: `{bal:,.2f} USDT`",
            f"Uptime: `{now}`",
            "──────────────────"
        ]
        msg = "
".join([line for line in report if line])
        self.telegram.send(msg)

    async def _ws_loop(self):
        sym   = self.settings.SYMBOL.lower()
        tf    = self.settings.TIMEFRAME
        streams = f"{sym}@aggTrade/{sym}@kline_{tf}"
        base    = WS_BASE_TEST if self.settings.TESTNET else WS_BASE
        url     = base + streams

        while True:
            try:
                logger.info(f"Connecting WebSocket: {url}")
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self.connected = True
                    logger.info("✅ WebSocket connected")
                    await self._notify_dashboard()
                    async for raw in ws:
                        await self._handle_message(json.loads(raw))
            except Exception as e:
                self.connected = False
                self.reconnect_count += 1
                logger.error(f"WS error: {e} — reconnecting in 10s...")
                await asyncio.sleep(10)

    async def _handle_message(self, msg: dict):
        data = msg.get("data", msg)
        event = data.get("e", "")
        if event == "aggTrade":
            await self._handle_tick(data)
        elif event == "kline":
            await self._handle_kline(data)

    async def _handle_tick(self, data: dict):
        """รับ price tick — อัพเดทราคาและเช็ค Trailing Stop"""
        self.current_price = float(data["p"])
        
        # ── Check Trailing Stop Logic ─────────────────────
        if self.settings.TRAILING_STOP and self.current_position:
            amt = float(self.current_position["positionAmt"])
            side = "BUY" if amt > 0 else "SELL"
            
            if side == "BUY":
                new_tsl = self.current_price * (1 - self.settings.TRAILING_PCT / 100)
                if new_tsl > self.trailing_sl_price:
                    self.trailing_sl_price = new_tsl
                if self.current_price <= self.trailing_sl_price:
                    logger.info(f"Trailing SL Triggered! Price {self.current_price} <= {self.trailing_sl_price}")
                    await asyncio.to_thread(self._close_position, "Trailing Stop Loss Triggered")
            
            elif side == "SELL":
                new_tsl = self.current_price * (1 + self.settings.TRAILING_PCT / 100)
                if self.trailing_sl_price == 0 or new_tsl < self.trailing_sl_price:
                    self.trailing_sl_price = new_tsl
                if self.current_price >= self.trailing_sl_price:
                    logger.info(f"Trailing SL Triggered! Price {self.current_price} >= {self.trailing_sl_price}")
                    await asyncio.to_thread(self._close_position, "Trailing Stop Loss Triggered")

        await self._notify_dashboard({"type": "tick", "price": self.current_price, "ts": data["T"]})

    async def _handle_kline(self, data: dict):
        k = data["k"]
        candle = {
            "open": float(k["o"]), "high": float(k["h"]), "low": float(k["l"]),
            "close": float(k["c"]), "volume": float(k["v"]), "open_time": k["t"],
        }
        if self.candles and self.candles[-1]["open_time"] == k["t"]:
            self.candles[-1] = candle
        else:
            self.candles.append(candle)

        if k["x"]:
            await self._analyze_and_trade()
        await self._notify_dashboard({"type": "kline", "candle": candle, "closed": k["x"]})

    async def _analyze_and_trade(self):
        """วิเคราะห์ signal และ Re-sync position"""
        if len(self.candles) < 60: return

        try:
            # Auto Re-sync: Check real position from exchange
            self.current_position = await asyncio.to_thread(self._get_position)
            has_position = self.current_position is not None

            df = pd.DataFrame(list(self.candles))
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df.set_index("open_time", inplace=True)

            signal = self.strategy.analyze(df)
            self.last_signal = signal["action"]
            self.last_signal_time = datetime.now().strftime("%H:%M:%S")
            self.indicators = signal.get("indicators", {})

            # Risk check
            risk = self.risk_mgr.check_risk(self._safe_get_balance(), self.daily_pnl)
            
            # Execute
            if signal["action"] in ("BUY", "SELL") and not has_position:
                if risk["ok"]:
                    await asyncio.to_thread(self._open_position, signal)
                else:
                    logger.warning(f"Risk skip: {risk['reason']}")
            elif signal["action"] == "CLOSE" and has_position:
                await asyncio.to_thread(self._close_position, signal["reason"])

            await self._notify_dashboard({"type": "signal", "signal": signal})

        except Exception as e:
            logger.error(f"Analyze error: {e}", exc_info=True)

    def _open_position(self, signal: dict):
        symbol = self.settings.SYMBOL
        side   = signal["action"]
        price  = self.current_price

        balance = self._safe_get_balance()
        alloc   = self.settings.POSITION_ALLOC_PCT
        usdt    = balance * alloc

        if usdt < 5: return
        qty = round((usdt * self.settings.LEVERAGE) / price, 3)
        sl_price, tp_price = self.risk_mgr.calculate_sl_tp(price, side)
        
        # Set initial trailing SL
        self.trailing_sl_price = sl_price

        try:
            # Market order
            self.client.futures_create_order(symbol=symbol, side=side, type="MARKET", quantity=qty)
            
            # Initial SL/TP Safety Net on Exchange
            close_side = "SELL" if side == "BUY" else "BUY"
            try:
                self.client.futures_create_order(
                    symbol=symbol, side=close_side, type="STOP_MARKET",
                    stopPrice=round(sl_price, 1), quantity=qty, reduceOnly="true"
                )
                self.client.futures_create_order(
                    symbol=symbol, side=close_side, type="TAKE_PROFIT_MARKET",
                    stopPrice=round(tp_price, 1), quantity=qty, reduceOnly="true"
                )
            except: pass

            self.trade_count += 1
            self.trade_history.append({
                "time": datetime.now().strftime("%H:%M:%S"), "side": side, "price": price, 
                "qty": qty, "sl": sl_price, "tp": tp_price, "status": "OPEN", "pnl": None,
            })

            emoji = "🟢" if side == "BUY" else "🔴"
            self.telegram.send(
                f"{emoji} *OPEN {side} {symbol}*\n"
                f"Entry: `{price:,.2f}` | Qty: `{qty}`\n"
                f"SL: `{sl_price:,.2f}` | TP: `{tp_price:,.2f}`\n"
                f"Trailing: `{self.settings.TRAILING_PCT}%`"
            )
            logger.info(f"✅ Order opened: {side} {qty} @ {price}")

        except Exception as e:
            logger.error(f"Open order error: {e}")
            self.telegram.send(f"❌ Order failed: `{e}`")

    def _close_position(self, reason: str):
        pos = self._get_position() 
        if not pos: 
            self.current_position = None
            self.trailing_sl_price = 0
            return
            
        amt = float(pos["positionAmt"])
        qty = abs(amt)
        side = "SELL" if amt > 0 else "BUY"

        try:
            # Cancel all open orders for this symbol
            self.client.futures_cancel_all_open_orders(symbol=self.settings.SYMBOL)
            
            # Market Close
            self.client.futures_create_order(
                symbol=self.settings.SYMBOL, side=side, type="MARKET", 
                quantity=qty, reduceOnly="true"
            )
            
            pnl = float(pos.get("unRealizedProfit", 0))
            self.daily_pnl += pnl
            self.current_position = None
            self.trailing_sl_price = 0

            for t in reversed(self.trade_history):
                if t["status"] == "OPEN":
                    t["status"], t["pnl"] = "CLOSED", round(pnl, 2)
                    break

            emoji = "✅" if pnl >= 0 else "❌"
            self.telegram.send(
                f"{emoji} *CLOSED POSITION*\n"
                f"PnL: `{pnl:+.2f} USDT` | Daily: `{self.daily_pnl:+.2f} USDT`\n"
                f"Reason: _{reason}_"
            )
            logger.info(f"Position closed: {reason} | PnL: {pnl:+.2f}")

        except Exception as e:
            logger.error(f"Close position error: {e}")

    async def _load_historical_candles(self):
        try:
            raw = self.client.futures_klines(
                symbol=self.settings.SYMBOL,
                interval=self.settings.TIMEFRAME,
                limit=200
            )
            for r in raw:
                self.candles.append({
                    "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
                    "close": float(r[4]), "volume": float(r[5]), "open_time": r[0],
                })
            self.current_price = float(raw[-1][4])
            logger.info(f"✅ Loaded {len(self.candles)} candles")
        except Exception as e:
            logger.error(f"Load history error: {e}")

    def _get_position(self) -> dict | None:
        try:
            positions = self.client.futures_position_information(symbol=self.settings.SYMBOL)
            for p in positions:
                if float(p.get("positionAmt", 0)) != 0: return p
            return None
        except: return None

    def _safe_get_balance(self) -> float:
        try:
            for b in self.client.futures_account_balance():
                if b["asset"] == "USDT": return float(b["balance"])
        except: pass
        return 0.0

    async def _notify_dashboard(self, extra: dict | None = None):
        state = self.get_state()
        if extra: state.update(extra)
        for cb in self._dashboard_callbacks:
            try: await cb(state)
            except: pass
