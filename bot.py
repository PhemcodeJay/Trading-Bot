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
        # Initialize configuration
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.trade_usd = float(os.getenv("TRADE_USD", 1))
        self.symbol = os.getenv("SYMBOL", "DOGE/USDT")
        self.timeframe = os.getenv("TIMEFRAME", "5m")
        self.limit = int(os.getenv("LIMIT", 500))
        
        # Initialize logging system
        self.log_dir = os.path.join(os.getcwd(), "trading_logs")
        self.trades_file = os.path.join(self.log_dir, "trades.csv")
        self.signals_file = os.path.join(self.log_dir, "signals.log")
        self._init_logging_system()

        # Trading parameters
        self.stop_loss_pct = 0.10  # 10%
        self.take_profit_min_pct = 0.50  # 50% min
        self.take_profit_max_pct = 1.00  # 100% max
        self.in_position = False
        self.entry_price = 0
        self.demo_mode = not (self.api_key and self.api_secret)

        # Initialize exchange
        self.exchange = self._init_exchange()

    def _init_logging_system(self):
        """Initialize logging directory and files"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            
            # Initialize trades CSV if doesn't exist
            if not os.path.exists(self.trades_file):
                with open(self.trades_file, 'w') as f:
                    f.write("timestamp,mode,trade_type,price,amount,reason\n")
            
            # Initialize signals log
            if not os.path.exists(self.signals_file):
                with open(self.signals_file, 'w') as f:
                    f.write("=== Trading Signals Log ===\n")
        except Exception as e:
            print(f"Failed to initialize logging system: {e}")
            raise

    def _init_exchange(self):
        """Initialize the exchange connection"""
        if self.demo_mode:
            print("Running in DEMO mode - no real trades will be executed")
            return ccxt.binance()  # Public API only
        
        try:
            exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'options': {
                    'adjustForTimeDifference': True
                }
            })
            # Test connection
            exchange.fetch_balance()
            return exchange
        except Exception as e:
            print(f"Failed to initialize exchange: {e}")
            print("Falling back to DEMO mode")
            self.demo_mode = True
            return ccxt.binance()

    def _log_signal(self, message):
        """Log a trading signal to the log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        try:
            with open(self.signals_file, 'a') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Failed to log signal: {e}")

    def send_telegram(self, message):
        if not (self.telegram_token and self.telegram_chat_id):
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {"chat_id": self.telegram_chat_id, "text": message}
            requests.post(url, data=data)
        except Exception as e:
            print(f"Telegram alert failed: {e}")

    def fetch_data(self):
        try:
            bars = self.exchange.fetch_ohlcv(
                self.symbol, 
                timeframe=self.timeframe, 
                limit=self.limit
            )
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Error fetching data: {e}")
            self._log_signal(f"Data fetch error: {str(e)}")
            return self._generate_sample_data()

    def _generate_sample_data(self):
    """Generate sample data for backtesting"""
    print("Generating sample data for backtesting")
    self._log_signal("Using generated sample data")
    
    date_rng = pd.date_range(end=datetime.now(), periods=self.limit, freq=self.timeframe)
    base_price = np.random.uniform(0.05, 0.15)
    price_series = base_price * (1 + np.cumsum(np.random.randn(self.limit) * 0.002))
    
    df = pd.DataFrame({
        'timestamp': date_rng,
        'open': price_series * 0.998,
        'high': price_series * 1.002,
        'low': price_series * 0.995,
        'close': price_series,
        'volume': np.random.uniform(1000000, 5000000, size=self.limit)
    })
    return df

    def apply_indicators(self, df):
        # Moving Averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()

        # Bollinger Bands
        bb = BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()

        # MACD
        macd = MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        # RSI
        rsi = RSIIndicator(close=df['close'])
        df['rsi'] = rsi.rsi()

        # Stochastic RSI
        stoch = StochasticOscillator(high=df['high'], low=df['low'], close=df['close'])
        df['stoch_rsi'] = stoch.stoch()

        return df

    def log_trade(self, trade_type, price, amount, reason):
        """Log a trade to the trades CSV file"""
        timestamp = datetime.utcnow().isoformat()
        mode = "DEMO" if self.demo_mode else "LIVE"
        log_line = f"{timestamp},{mode},{trade_type},{price:.8f},{amount:.8f},{reason}\n"
        
        try:
            with open(self.trades_file, 'a') as f:
                f.write(log_line)
            self._log_signal(f"Trade executed: {trade_type} {amount:.4f} {self.symbol} at {price:.8f}")
        except Exception as e:
            print(f"Failed to log trade: {e}")

    def execute_trade(self, trade_type, price, amount, reason):
        """Execute a trade (or simulate in demo mode)"""
        # Format the message
        mode = "DEMO" if self.demo_mode else "LIVE"
        msg = f"[{mode}] {trade_type} {amount:.4f} {self.symbol} at {price:.8f} | Reason: {reason}"
        
        # Output to console
        print(msg)
        
        # Send to Telegram
        self.send_telegram(msg)
        
        # Log the trade
        self.log_trade(trade_type, price, amount, reason)

    def run_strategy(self, df):
        """Run the trading strategy on the provided data"""
        for i in range(200, len(df)):
            row = df.iloc[i]
            price = row['close']

            if not self.in_position:
                # Buy conditions
                if (price < row['bb_lower'] and 
                    row['macd'] > row['macd_signal'] and 
                    row['rsi'] < 30 and 
                    row['stoch_rsi'] < 20 and 
                    price > row['ma200']):
                    
                    self.entry_price = price
                    amount = self.trade_usd / price
                    self.execute_trade("BUY", price, amount, "Strategy Triggered")
                    self.in_position = True
                    self._log_signal("Entered position")
            
            else:
                # Exit conditions
                if price <= self.entry_price * (1 - self.stop_loss_pct):
                    # Stop loss hit
                    self.execute_trade("SELL", price, self.trade_usd / self.entry_price, "Stop Loss Hit")
                    self.in_position = False
                    self._log_signal("Exited position (Stop Loss)")
                
                elif price >= self.entry_price * (1 + np.random.uniform(
                    self.take_profit_min_pct, self.take_profit_max_pct)):
                    
                    # Take profit hit
                    self.execute_trade("SELL", price, self.trade_usd / self.entry_price, "Take Profit Hit")
                    self.in_position = False
                    self._log_signal("Exited position (Take Profit)")

    def run(self):
        """Main execution method"""
        self._log_signal(f"Starting {'DEMO' if self.demo_mode else 'LIVE'} trading session")
        
        try:
            # Fetch and process data
            df = self.fetch_data()
            df = self.apply_indicators(df)
            
            # Run strategy
            self.run_strategy(df)
            
        except Exception as e:
            self._log_signal(f"Critical error: {str(e)}")
            print(f"Error in main execution: {e}")
        finally:
            self._log_signal("Trading session ended")

if __name__ == "__main__":
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        print(f"Failed to initialize bot: {e}")