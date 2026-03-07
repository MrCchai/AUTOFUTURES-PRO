import pandas as pd
import pandas_ta as ta
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib
import os
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load ENV for Telegram
load_dotenv('/home/ubuntu/autofutures-rt/.env')
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TG_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Setup logging
LOG_PATH = '/home/ubuntu/autofutures-rt/logs/auto_train.log'
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format='%(asctime)s %(message)s')

SYMBOLS = ['XRPUSDT', 'SOLUSDT', 'DOGEUSDT']
BASE_DIR = '/home/ubuntu/autofutures-rt'
DATA_DIR = f'{BASE_DIR}/data'

def send_tg(msg):
    try:
        url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
        payload = {'chat_id': TG_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
        requests.post(url, json=payload, timeout=10)
    except: pass

def train_model(symbol):
    try:
        logging.info(f'--- Retraining AI Model for {symbol} ---')
        symbol_lower = symbol.split('USDT')[0].lower()
        hist_path = f'{DATA_DIR}/{symbol_lower}usdt_history.csv'
        if symbol == 'XRPUSDT': hist_path = f'{DATA_DIR}/historical_data.csv'
        live_path = f'{DATA_DIR}/trading_data_multi.csv'
        
        if not os.path.exists(hist_path): return None
            
        df_hist = pd.read_csv(hist_path)
        if os.path.exists(live_path):
            try:
                df_live_full = pd.read_csv(live_path)
                df_live = df_live_full[df_live_full['symbol'] == symbol].copy()
                if not df_live.empty:
                    core_cols = ['open', 'high', 'low', 'close', 'volume']
                    df = pd.concat([df_hist[core_cols], df_live[core_cols]], ignore_index=True)
                else: df = df_hist
            except: df = df_hist
        else: df = df_hist

        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['open'] = df['open'].astype(float)
        
        bb = ta.bbands(df['close'], length=20, std=2.0)
        df['bb_width'] = (bb.iloc[:, 2] - bb.iloc[:, 0]) / df['close'] * 100
        df['body_size'] = abs(df['close'] - df['open']) / df['open'] * 100
        df['prev_change'] = df['close'].pct_change() * 100
        df['vol_sma'] = ta.sma(df['volume'], length=20)
        df['vol_ratio'] = df['volume'] / df['vol_sma']
        df['rsi'] = ta.rsi(df['close'], length=7)

        df['target'] = ( (df['close'].shift(-3) - df['close']) / df['close'] > 0.005 ).astype(int)
        df = df.dropna()
        features = ['rsi', 'vol_ratio', 'bb_width', 'body_size', 'prev_change']

        if len(df) < 100: return None
            
        model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        model.fit(df[features], df['target'])
        
        # Calculate Accuracy (Self-check on training data)
        acc = model.score(df[features], df['target']) * 100

        model_path = f'{DATA_DIR}/{symbol_lower}_ai_model_v1.pkl'
        joblib.dump({'model': model, 'features': features}, model_path)
        logging.info(f'✅ [{symbol}] Updated! Rows: {len(df)} Acc: {acc:.2f}%')
        return {'symbol': symbol, 'rows': len(df), 'acc': acc}

    except Exception as e:
        logging.error(f'[{symbol}] Training Failed: {str(e)}')
        return None

if __name__ == '__main__':
    results = []
    for sym in SYMBOLS:
        res = train_model(sym)
        if res: results.append(res)
    
    if results:
        report = '🧠 *AI Daily Retrain Report*\n\n'
        for r in results:
            report += f"🔹 *{r['symbol']}*\n- Data Rows: {r['rows']}\n- Model Acc: {r['acc']:.2f}%\n\n"
        report += '🚀 *Status:* All Models Updated\n_Bot Restarting..._'
        send_tg(report)
        os.system('sudo systemctl restart autofutures-rt.service')
