import pandas_ta as ta
import pandas as pd
import logging
import joblib
import os
import numpy as np

logger = logging.getLogger(__name__)

class DogeScalperStrategy:
    def __init__(self, settings):
        self.s = settings
        self.models = {}
        self._load_models()

    def _load_models(self):
        # Handle both list (SYMBOLS) and single (SYMBOL) from settings
        symbols = getattr(self.s, 'SYMBOLS', [self.s.SYMBOL])
        for sym in symbols:
            symbol_name = sym.split('USDT')[0].lower()
            # Try to find model in common paths - FIXED for V14
            paths = [
                f'/home/ubuntu/autofutures-rt/data/{symbol_name}_ai_model_v1.pkl',
                f'/home/ubuntu/autofutures-rt/data/{sym.lower()}_ai_model_v1.pkl',
                f'./data/{symbol_name}_ai_model_v1.pkl',
                f'./data/{sym.lower()}_ai_model_v1.pkl'
            ]
            
            loaded = False
            for path in paths:
                try:
                    if os.path.exists(path):
                        self.models[sym] = joblib.load(path)
                        logger.info(f'V AI Model for {sym} Loaded from {path}')
                        loaded = True
                        break
                except Exception as e:
                    logger.error(f'AI Load Attempt {path} Failed: {e}')
            
            if not loaded:
                logger.warning(f'AI Model for {sym} NOT FOUND (Checked: {paths})')

    def analyze(self, df):
        try:
            # 1. Basic Indicators
            df['rsi'] = ta.rsi(df['close'], length=7)
            bb = ta.bbands(df['close'], length=20, std=2.0)
            df['bbl'] = bb.iloc[:, 0]
            df['bbu'] = bb.iloc[:, 2]
            df['vol_sma'] = ta.sma(df['volume'], length=20)
            df['vol_ratio'] = df['volume'] / df['vol_sma']
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

            # 2. AI Features
            df['bb_width'] = (df['bbu'] - df['bbl']) / df['close'] * 100
            df['body_size'] = abs(df['close'] - df['open']) / df['open'] * 100
            df['prev_change'] = df['close'].pct_change() * 100

            df = df.fillna(0)
            curr = df.iloc[-1]

            rsi = float(curr['rsi'])
            vol_ratio = float(curr['vol_ratio'])
            atr = float(curr['atr']) if curr['atr'] != 0 else (curr['close'] * 0.01)
            symbol = df.attrs.get('symbol', self.s.SYMBOL)

            # 3. AI Prediction Logic
            ai_prob = 0.0
            model_data = self.models.get(symbol)

            if model_data:
                features = model_data['features']
                # Create DataFrame for prediction to avoid feature name warning
                X = pd.DataFrame([curr[features].values], columns=features)
                probs = model_data['model'].predict_proba(X)[0]
                ai_prob = float(probs[1]) if len(probs) > 1 else 0.0
            else:
                ai_prob = -1.0

            # AI Dynamic Parameters
            dynamic_sl_pct = (atr * 1.2 / curr['close']) * 100
            dynamic_tp_pct = (atr * 2.2 / curr['close']) * 100

            # AI Aggressive Mode
            if ai_prob > 0.6:
                dynamic_tp_pct *= 1.5
                dynamic_sl_pct *= 0.8
            elif ai_prob > 0.4:
                dynamic_tp_pct *= 1.2

            dynamic_sl_pct = max(0.5, min(dynamic_sl_pct, 2.5))
            dynamic_tp_pct = max(0.8, min(dynamic_tp_pct, 5.0))

            indicators = {
                'rsi': round(rsi, 2),
                'vol_ratio': round(vol_ratio, 1),
                'ai_status': f'Prob: {ai_prob:.2f}' if ai_prob >= 0 else 'Rule-Only',
                'dynamic_sl': round(dynamic_sl_pct, 2),
                'dynamic_tp': round(dynamic_tp_pct, 2)
            }

            ai_exit = False
            if rsi > 85 or rsi < 15: ai_exit = True

            # ENTRY LOGIC (AI Adjusted)
            # Buy Condition: Low RSI + Good AI Prob OR High Vol Ratio
            if rsi < 35 and (ai_prob > 0.35 or ai_prob == -1.0) and vol_ratio > 1.2:
                return {
                    'action': 'BUY',
                    'reason': f'AI Dip Detect ({ai_prob:.2f})',
                    'indicators': indicators,
                    'sl_pct': dynamic_sl_pct,
                    'tp_pct': dynamic_tp_pct
                }

            # Sell Condition: High RSI + AI Peak Detect
            if rsi > 70 and vol_ratio > 1.3:
                 return {
                    'action': 'SELL',
                    'reason': 'AI Peak Detect',
                    'indicators': indicators,
                    'sl_pct': dynamic_sl_pct,
                    'tp_pct': dynamic_tp_pct
                }

            if ai_exit:
                return {'action': 'CLOSE', 'reason': 'AI Early Exit (Extreme)', 'indicators': indicators}

            return {'action': 'HOLD', 'reason': 'Wait', 'indicators': indicators}

        except Exception as e:
            logger.error(f'Strategy Error: {e}')
            return {'action': 'HOLD', 'reason': f'Err: {e}', 'indicators': {}}
