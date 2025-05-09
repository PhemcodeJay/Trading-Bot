import os
import ccxt
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv
from ta.volatility import BollingerBands
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from datetime import datetime

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADE_USD = float(os.getenv("TRADE_USD", 1))
SYMBOL = os.getenv("SYMBOL", "DOGE/USDT")
TIMEFRAME = os.getenv("TIMEFRAME", "5m")
LIMIT = int(os.getenv("LIMIT", 500))
CSV_FILE = os.getenv("CSV_FILE", "trades.csv")

STOP_LOSS_PCT = 0.03  # 3%
TAKE_PROFIT_PCT = 0.05  # 5%

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, data=data)
    except:
        print("Telegram alert failed.")

def fetch_data():
    bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def apply_indicators(df):
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma200'] = df['close'].rolling(window=200).mean()

    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()

    macd = MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    rsi = RSIIndicator(close=df['close'])
    df['rsi'] = rsi.rsi()

    stoch = StochasticOscillator(high=df['high'], low=df['low'], close=df['close'])
    df['stoch_rsi'] = stoch.stoch()

    return df

def get_balance(symbol='USDT'):
    balance = exchange.fetch_balance()
    return balance.get(symbol, {}).get('free', 0)

def log_trade(trade_type, price, amount, reason):
    timestamp = datetime.utcnow().isoformat()
    log = f"{timestamp},{trade_type},{price},{amount},{reason}\n"
    with open(CSV_FILE, "a") as f:
        f.write(log)

def execute_trade(trade_type, price, amount, reason):
    msg = f"{trade_type} {amount:.4f} {SYMBOL} at {price:.5f} | Reason: {reason}"
    print(msg)
    send_telegram(msg)
    log_trade(trade_type, price, amount, reason)

def backtest(df):
    print("Running backtest...")
    in_position = False
    entry_price = 0
    for i in range(20, len(df)):
        row = df.iloc[i]
        price = row['close']
        if not in_position:
            if (
                row['close'] < row['bb_lower'] and
                row['macd'] > row['macd_signal'] and
                row['rsi'] < 30 and
                row['stoch_rsi'] < 20 and
                row['close'] > row['ma200']
            ):
                entry_price = price
                amount = TRADE_USD / price
                execute_trade("BUY", price, amount, "Strategy Triggered")
                in_position = True
        else:
            if price <= entry_price * (1 - STOP_LOSS_PCT):
                execute_trade("SELL", price, TRADE_USD / entry_price, "Stop Loss Hit")
                in_position = False
            elif price >= entry_price * (1 + TAKE_PROFIT_PCT):
                execute_trade("SELL", price, TRADE_USD / entry_price, "Take Profit Hit")
                in_position = False

if __name__ == "__main__":
    df = fetch_data()
    df = apply_indicators(df)
    backtest(df)
