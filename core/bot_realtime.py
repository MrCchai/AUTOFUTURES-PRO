import asyncio, json, time, logging, pandas as pd, csv, os
from collections import deque
from datetime import datetime, timezone, timedelta
from binance.client import Client
import websockets
from strategies.doge_scalper import DogeScalperStrategy
from utils.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

class RealtimeBot:
    def __init__(self, settings):
        self.s = settings
        self.telegram = TelegramNotifier(settings.TELEGRAM_TOKEN, settings.TELEGRAM_CHAT_ID)
        self.client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)
        self.strategy = DogeScalperStrategy(settings)
        
        self.symbols = settings.SYMBOLS
        self.candles = {sym: deque(maxlen=300) for sym in self.symbols}
        self.prices = {sym: 0.0 for sym in self.symbols}
        self.positions = {sym: None for sym in self.symbols}
        self.indicators = {sym: {} for sym in self.symbols}
        self.trailing_sls = {sym: 0.0 for sym in self.symbols}
        
        self.balance = 0.0
        self.real_daily_pnl = 0.0
        self.demo_daily_pnl = 0.0
        self.error_count = 0
        self.trade_history = deque(maxlen=30)
        self.logs = deque(maxlen=100)
        self.is_running = False

    def get_now_th(self): return datetime.now(timezone(timedelta(hours=7)))
    
    def _save_stats(self):
        try:
            data = {
                'demo_daily_pnl': self.demo_daily_pnl,
                'error_count': self.error_count,
                'trade_history': list(self.trade_history),
                'last_update': self.get_now_th().strftime('%Y-%m-%d')
            }
            with open('/home/ubuntu/autofutures-rt/data/stats.json', 'w') as f:
                json.dump(data, f)
        except: pass

    def _load_stats(self):
        try:
            p = '/home/ubuntu/autofutures-rt/data/stats.json'
            if os.path.exists(p):
                with open(p, 'r') as f: data = json.load(f)
                if data.get('last_update') == self.get_now_th().strftime('%Y-%m-%d'):
                    self.demo_daily_pnl = data.get('demo_daily_pnl', 0.0)
                    self.error_count = data.get('error_count', 0)
                    self.trade_history = deque(data.get('trade_history', []), maxlen=30)
        except: pass

    def get_state(self, full=True, symbol=None):
        target = symbol if symbol in self.symbols else self.symbols[0]
        return {
            'price': self.prices[target], 'balance': round(self.balance, 2),
            'real_daily_pnl': round(self.real_daily_pnl, 4),
            'demo_daily_pnl': round(self.demo_daily_pnl, 4),
            'daily_pnl': round(self.demo_daily_pnl, 4),
            'logs': list(self.logs),
            'trade_history': list(self.trade_history),
            'timestamp': int(time.time()*1000),
            'all_symbols': self.symbols,
            'all_prices': self.prices,
            'all_indicators': self.indicators,
            'all_positions': {s: (p['unRealizedProfit'] if p else None) for s, p in self.positions.items()},
            'candles': list(self.candles[target])[-120:] if full else None
        }

    async def start(self):
        await self._load_history()
        await self._calc_daily_pnl()
        self._load_stats()
        self.is_running = True
        for sym in self.symbols: await self._analyze(sym)
        self.telegram.send(f'🚀 *🧪 AI-MANAGED DEMO ACTIVE* | Multi-Symbol V14.41')
        asyncio.create_task(self._fetcher_loop())
        asyncio.create_task(self._command_loop())
        asyncio.create_task(self._report_loop())
        await self._ws_loop()

    async def _calc_daily_pnl(self):
        try:
            now_th = self.get_now_th()
            start_ts = int(now_th.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
            total_pnl = 0.0
            for sym in self.symbols:
                trades = self.client.futures_account_trades(symbol=sym, startTime=start_ts)
                total_pnl += sum(float(t['realizedPnl']) for t in trades)
            self.real_daily_pnl = total_pnl
        except: pass

    async def _fetcher_loop(self):
        while self.is_running:
            try:
                acc = self.client.futures_account()
                self.balance = float(acc['totalWalletBalance'])
                all_pos = self.client.futures_position_information()
                for sym in self.symbols:
                    pos = next((p for p in all_pos if p['symbol'] == sym), None)
                    if pos and float(pos['positionAmt']) != 0:
                        self.positions[sym] = pos
                    else:
                        self.positions[sym] = None
                        self.trailing_sls[sym] = 0.0
                await asyncio.sleep(15)
            except Exception as e:
                self.error_count += 1
                await asyncio.sleep(10)

    async def _ws_loop(self):
        streams = '/'.join([s.lower() + '@aggTrade/' + s.lower() + '@kline_5m' for s in self.symbols])
        url = f'wss://fstream.binance.com/stream?streams={streams}'
        async with websockets.connect(url) as ws:
            async for raw in ws:
                if not self.is_running: break
                try:
                    data = json.loads(raw)['data']
                    sym = data['s']
                    if data['e'] == 'aggTrade':
                        self.prices[sym] = float(data['p'])
                        if self.candles[sym]: self.candles[sym][-1]['close'] = self.prices[sym]
                        if self.positions[sym] and self.trailing_sls[sym] > 0:
                            amt = float(self.positions[sym]['positionAmt'])
                            if (amt > 0 and self.prices[sym] <= self.trailing_sls[sym]) or (amt < 0 and self.prices[sym] >= self.trailing_sls[sym]):
                                await self._close(sym, 'AI TSL Hit')
                    elif data['e'] == 'kline' and data['k']['x']:
                        k = data['k']
                        self.candles[sym].append({'open_time': k['t'], 'open': float(k['o']), 'high': float(k['h']), 'low': float(k['l']), 'close': float(k['c']), 'volume': float(k['v'])})
                        await self._analyze(sym)
                except Exception as e:
                    self.error_count += 1

    async def _analyze(self, symbol):
        try:
            if len(self.candles[symbol]) < 20: return
            df = pd.DataFrame(list(self.candles[symbol]))
            df.attrs['symbol'] = symbol
            res = self.strategy.analyze(df)
            self.indicators[symbol] = res.get('indicators', {})

            if self.real_daily_pnl + self.demo_daily_pnl <= -abs(self.s.MAX_DAILY_LOSS_USDT): return

            if res['action'] in ['BUY', 'SELL'] and not self.positions[symbol]:
                await self._open(symbol, res['action'], res.get('sl_pct'), res.get('tp_pct'))
            elif res['action'] == 'CLOSE' and self.positions[symbol]:
                await self._close(symbol, f'AI-Exit: {res['reason']}')

            self._collect_data(symbol, res)
        except Exception as e:
            self.error_count += 1

    def _collect_data(self, symbol, res):
        try:
            fp = '/home/ubuntu/autofutures-rt/data/trading_data_multi.csv'
            ex = os.path.isfile(fp)
            with open(fp, mode='a', newline='') as f:
                w = csv.writer(f)
                if not ex: w.writerow(['time', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'bbu', 'bbl', 'vol_ratio', 'action'])
                if self.candles[symbol]:
                    c = self.candles[symbol][-1]
                    i = res.get('indicators', {})
                    w.writerow([self.get_now_th().strftime('%Y-%m-%d %H:%M:%S'), symbol, c.get('open'), c.get('high'), c.get('low'), c.get('close'), c.get('volume'), i.get('rsi'), i.get('bbu'), i.get('bbl'), i.get('vol_ratio'), res.get('action')])
        except: pass

    async def _open(self, symbol, side, sl_pct=None, tp_pct=None):
        try:
            sl_to_use = sl_pct if sl_pct else self.s.STOP_LOSS_PCT
            capital = self.balance * self.s.POSITION_ALLOC_PCT / len(self.symbols)
            qty = round((capital * self.s.LEVERAGE) / self.prices[symbol], 1 if 'USDT' in symbol else 0)
            if symbol in ['XRPUSDT', 'DOGEUSDT']: qty = round(qty, 0)

            self.logs.appendleft({'time': self.get_now_th().strftime('%H:%M:%S'), 'msg': f'🧪 [AI-DEMO] OPEN {side} {symbol} | SL: {sl_to_use:.2f}%'})    
            self.telegram.send(f'🧪 *[AI-OPEN] {side} {symbol}*\nPrice: {self.prices[symbol]}\nDynamic SL: {sl_to_use:.2f}%')

            self.positions[symbol] = {
                'entryPrice': self.prices[symbol],
                'positionAmt': qty if side == 'BUY' else -qty,
                'unRealizedProfit': '0.00',
                'margin_used': capital,
                'sl_pct': sl_to_use
            }
            if side == 'BUY': self.trailing_sls[symbol] = self.prices[symbol] * (1 - sl_to_use / 100)
            else: self.trailing_sls[symbol] = self.prices[symbol] * (1 + sl_to_use / 100)
        except Exception as e: 
            self.error_count += 1
            self.logs.appendleft({'time': 'ERR', 'msg': f'Open {symbol} Error: {e}'})

    async def _close(self, symbol, reason):
        if not self.positions[symbol]: return
        try:
            entry = float(self.positions[symbol]['entryPrice'])
            exit_p = self.prices[symbol]
            amt = float(self.positions[symbol]['positionAmt'])
            margin = self.positions[symbol].get('margin_used', 5.0)
            pnl_pct = (exit_p - entry) / entry * 100 if amt > 0 else (entry - exit_p) / entry * 100
            pnl_usdt = margin * (pnl_pct / 100) * self.s.LEVERAGE

            self.demo_daily_pnl += pnl_usdt
            self.trade_history.appendleft({'time': self.get_now_th().strftime('%H:%M:%S'), 'symbol': symbol, 'pnl': round(pnl_pct, 2), 'pnl_usdt': round(pnl_usdt, 4), 'entry': entry, 'exit': exit_p})
            self.logs.appendleft({'time': self.get_now_th().strftime('%H:%M:%S'), 'msg': f'🧪 [AI-DEMO] CLOSED {symbol} | PnL: {pnl_usdt:.4f} USDT ({pnl_pct:.2f}%)'})

            emoji = '🟢' if pnl_usdt >= 0 else '🔴'
            report = (f'{emoji} *[AI-CLOSE] {symbol}*\nPnL: {pnl_usdt:.4f} USDT ({pnl_pct:.2f}%)\nDaily: {self.demo_daily_pnl:.4f}\nReason: _{reason}_') 
            self.telegram.send(report)
            self.positions[symbol] = None
            self.trailing_sls[symbol] = 0.0
            self._save_stats()
        except Exception as e: 
            self.error_count += 1
            logger.error(f'Close {symbol} Error: {e}')

    async def _command_loop(self):
        while self.is_running:
            try:
                updates = self.telegram.get_updates()
                for upd in updates:
                    msg = upd.get('message', {})
                    text = msg.get('text', '')
                    if text and text.startswith('/'): await self._handle_command(text)
                await asyncio.sleep(3)
            except: await asyncio.sleep(5)

    async def _handle_command(self, cmd):
        c = cmd.lower().split()
        if c[0] == '/status':
            p_info = ''.join([f'📦 {s}: {'LONG' if float(p['positionAmt'])>0 else 'SHORT'} ({p.get('unRealizedProfit','0')}) USDT\n' for s,p in self.positions.items() if p]) or '📦 No active positions\n'
            stat = (f'🤖 *🧪 AI-MANAGED Status*\n💰 Balance: {self.balance:.2f} USDT\n📈 Daily: {self.demo_daily_pnl:.4f} USDT\n⚠️ Errors Today: {self.error_count}\n{p_info}')
            self.telegram.send(stat)
        elif c[0] == '/report':
            await self.send_daily_summary()
        elif c[0] == '/stop': self.is_running = False; self.telegram.send('🔴 *Bot Halted.*')

    async def _report_loop(self):
        while self.is_running:
            now = self.get_now_th()
            # Send report at 23:55 before retraining
            if now.hour == 23 and now.minute == 55:
                await self.send_daily_summary()
                await asyncio.sleep(65) # Avoid double send
            await asyncio.sleep(30)

    async def send_daily_summary(self):
        try:
            emoji = '💰' if self.demo_daily_pnl >= 0 else '📉'
            report = (f'📊 *AI TRADING DAILY SUMMARY*\n'
                      f'━━━━━━━━━━━━━━━━━━\n'
                      f'{emoji} *Net PnL:* {self.demo_daily_pnl:.4f} USDT\n'
                      f'🔄 *Total Trades:* {len(self.trade_history)}\n'
                      f'⚠️ *System Errors:* {self.error_count}\n'
                      f'💰 *Wallet Balance:* {self.balance:.2f} USDT\n'
                      f'━━━━━━━━━━━━━━━━━━\n'
                      f'✅ *Status:* AI Active & Learning')
            self.telegram.send(report)
        except: pass

    async def _load_history(self):
        for sym in self.symbols:
            try:
                raw = self.client.futures_klines(symbol=sym, interval='5m', limit=200)
                for r in raw: self.candles[sym].append({'open_time': r[0], 'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]), 'close': float(r[4]), 'volume': float(r[5])})
                self.prices[sym] = float(raw[-1][4])
            except: pass
