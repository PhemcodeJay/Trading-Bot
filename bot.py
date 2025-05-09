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

# Load environment variables
load_dotenv()

class TradingBot:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.trade_usd = float(os.getenv("TRADE_USD", 1))
        self.symbol = os.getenv("SYMBOL", "DOGE/USDT")
        self.timeframe = os.getenv("TIMEFRAME", "5m")
        self.limit = int(os.getenv("LIMIT", 500))
        self.csv_file = os.getenv("CSV_FILE", "trades.csv")

        self.stop_loss_pct = 0.10  # 10%
        self.take_profit_min_pct = 0.50  # 50% min
        self.take_profit_max_pct = 1.00  # 100% max
        self.in_position = False
        self.entry_price = 0

        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        })

    def send_telegram(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {"chat_id": self.telegram_chat_id, "text": message}
            requests.post(url, data=data)
        except Exception as e:
            print(f"Telegram alert failed: {e}")

    def fetch_data(self):
        bars = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=self.limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def apply_indicators(self, df):
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

    def get_balance(self, symbol='USDT'):
        balance = self.exchange.fetch_balance()
        return balance.get(symbol, {}).get('free', 0)

    def log_trade(self, trade_type, price, amount, reason):
        timestamp = datetime.utcnow().isoformat()
        log_line = f"{timestamp},{trade_type},{price},{amount},{reason}\n"
        with open(self.csv_file, "a") as f:
            f.write(log_line)

    def execute_trade(self, trade_type, price, amount, reason):
        msg = f"{trade_type} {amount:.4f} {self.symbol} at {price:.5f} | Reason: {reason}"
        print(msg)
        self.send_telegram(msg)
        self.log_trade(trade_type, price, amount, reason)

    def backtest(self, df):
        print("Running backtest...")
        for i in range(200, len(df)):
            row = df.iloc[i]
            price = row['close']

            if not self.in_position:
                if (
                    price < row['bb_lower'] and
                    row['macd'] > row['macd_signal'] and
                    row['rsi'] < 30 and
                    row['stoch_rsi'] < 20 and
                    price > row['ma200']
                ):
                    self.entry_price = price
                    amount = self.trade_usd / price
                    self.execute_trade("BUY", price, amount, "Strategy Triggered")
                    self.in_position = True
            else:
                # Stop Loss Condition (10%)
                if price <= self.entry_price * (1 - self.stop_loss_pct):
                    self.execute_trade("SELL", price, self.trade_usd / self.entry_price, "Stop Loss Hit")
                    self.in_position = False
                # Take Profit Condition (50% to 100%)
                elif price >= self.entry_price * (1 + np.random.uniform(self.take_profit_min_pct, self.take_profit_max_pct)):
                    self.execute_trade("SELL", price, self.trade_usd / self.entry_price, "Take Profit Hit")
                    self.in_position = False

    def run(self):
        df = self.fetch_data()
        df = self.apply_indicators(df)
        self.backtest(df)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
