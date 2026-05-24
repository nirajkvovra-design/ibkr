"""
Data fetcher module - retrieves real-time and historical data from multiple sources
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils import get_logger
import config

logger = get_logger(__name__)

class DataFetcher:
    """Fetches and processes financial data from Yahoo Finance and IB"""
    
    def __init__(self):
        self.cache = {}  # Cache for stock data to reduce API calls
        self.cache_time = {}  # Track when cache was updated
        self.fundamental_cache = {}
        self.fundamental_cache_time = {}
        self.calendar_cache = {}
        self.calendar_cache_time = {}
        self.cache_duration = 300  # Cache for 5 minutes
        self.regime_cache = None
        self.regime_cache_time = None
        
    def is_cache_valid(self, symbol):
        """Check if cached data is still fresh"""
        if symbol not in self.cache_time:
            return False
        
        age = datetime.now() - self.cache_time[symbol]
        return age.total_seconds() < self.cache_duration
        
    def get_stock_data(self, symbol, period='3mo', interval='1d'):
        """
        Fetch stock data from Yahoo Finance
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            period: Data period ('1d', '5d', '1mo', '3mo', '1y', etc.)
            interval: Data interval ('1m', '5m', '15m', '1h', '1d', etc.)
        
        Returns:
            DataFrame with OHLCV data and technical indicators
        """
        try:
            # Check cache first
            cache_key = f"{symbol}_{interval}"
            if self.is_cache_valid(cache_key):
                logger.debug(f"Using cached data for {symbol}")
                return self.cache[cache_key]
            
            logger.debug(f"Fetching data for {symbol} from Yahoo Finance")
            
            # Download data
            data = yf.download(symbol, period=period, interval=interval, 
                             progress=False, threads=False)
            
            if data.empty:
                logger.warning(f"No data returned for {symbol}")
                return None

            data = self._normalize_yfinance_data(data, symbol)
            
            # Add technical indicators
            data = self._add_indicators(data)
            
            # Cache it
            self.cache[cache_key] = data
            self.cache_time[cache_key] = datetime.now()
            
            logger.debug(f"Successfully fetched {len(data)} bars for {symbol}")
            return data
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    def _normalize_yfinance_data(self, data, symbol):
        """Return single-symbol OHLCV columns from yfinance output."""
        if isinstance(data.columns, pd.MultiIndex):
            if symbol in data.columns.get_level_values(-1):
                data = data.xs(symbol, axis=1, level=-1)
            else:
                data.columns = data.columns.get_level_values(0)
        return data
    
    def _add_indicators(self, data):
        """Add technical indicators to OHLCV data"""
        try:
            close = data['Close'].astype(float)
            
            # Moving Averages
            data['SMA_20'] = close.rolling(window=20, min_periods=20).mean()
            data['SMA_50'] = close.rolling(window=50, min_periods=50).mean()
            data['SMA_200'] = close.rolling(window=200, min_periods=200).mean()
            data['EMA_12'] = close.ewm(span=12, adjust=False).mean()
            data['EMA_26'] = close.ewm(span=26, adjust=False).mean()
            
            # Momentum Indicators
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(window=14, min_periods=14).mean()
            loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=14).mean()
            rs = gain / loss.replace(0, np.nan)
            data['RSI'] = 100 - (100 / (1 + rs))
            data.loc[loss == 0, 'RSI'] = 100

            data['MACD'] = data['EMA_12'] - data['EMA_26']
            data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
            data['MACD_Histogram'] = data['MACD'] - data['MACD_Signal']
            
            # Volume Indicators
            data['Volume_SMA'] = data['Volume'].rolling(window=20, min_periods=20).mean()
            data['Volume_Ratio'] = data['Volume'] / data['Volume_SMA']
            
            # Volatility
            high_low = data['High'] - data['Low']
            high_close = (data['High'] - close.shift()).abs()
            low_close = (data['Low'] - close.shift()).abs()
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            data['ATR'] = true_range.rolling(window=14, min_periods=14).mean()
            rolling_std = close.rolling(window=20, min_periods=20).std()
            data['BBands_Upper'] = data['SMA_20'] + (2 * rolling_std)
            data['BBands_Lower'] = data['SMA_20'] - (2 * rolling_std)
            
            return data
            
        except Exception as e:
            logger.error(f"Error adding indicators: {e}")
            return data
    
    def get_current_price(self, symbol):
        """Get current price for a symbol"""
        try:
            # Try to get cached stock data first to avoid network hits
            data = self.get_stock_data(symbol, period='5d', interval='1d')
            if data is not None and not data.empty:
                return float(data['Close'].iloc[-1])

            # Fallback to fundamentals cache or ticker.info
            fundamentals = self.get_fundamental_data(symbol)
            if fundamentals and fundamentals.get('price') is not None:
                return float(fundamentals['price'])

            ticker = yf.Ticker(symbol)
            price = ticker.info.get('currentPrice') or ticker.info.get('regularMarketPrice')
            if price is not None:
                return float(price)

            return None
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None

    def get_limit_price(self, symbol, action):
        """Build a conservative limit price around the current quote."""
        current_price = self.get_current_price(symbol)
        if current_price is None or current_price <= 0:
            return None

        if action.upper() == "BUY":
            multiplier = 1 + (config.MAX_ENTRY_SLIPPAGE_PERCENT / 100)
        else:
            multiplier = 1 - (config.MAX_EXIT_SLIPPAGE_PERCENT / 100)
        return round(current_price * multiplier, 2)

    def get_market_regime(self):
        """
        Classifies the daily broad market direction into BULLISH, NEUTRAL, or BEARISH.
        Uses cached regime state if updated within the last 30 minutes.
        """
        if self.regime_cache is not None and self.regime_cache_time is not None:
            age = datetime.now() - self.regime_cache_time
            if age.total_seconds() < 1800:  # 30 minutes
                return self.regime_cache

        logger.info("[Market Regime Sentry] Evaluating broad market direction...")
        bullish_indicators = 0
        total_indicators = 0
        bearish_indicators = 0

        for symbol in config.MARKET_REGIME_SYMBOLS:
            try:
                data = self.get_stock_data(symbol, period='6mo', interval='1d')
                if data is None or len(data) < 50:
                    continue

                latest = data.iloc[-1]
                close = float(latest['Close'])
                prev_close = float(data.iloc[-2]['Close'])
                sma_20 = latest.get('SMA_20')
                sma_50 = latest.get('SMA_50')
                sma_200 = latest.get('SMA_200')
                macd = latest.get('MACD')
                macd_signal = latest.get('MACD_Signal')

                five_day_close = float(data.iloc[-6]['Close']) if len(data) >= 6 else prev_close
                five_day_return = (close - five_day_close) / five_day_close

                # 1. Short-term trend (Price vs SMA_20)
                if sma_20 is not None and not pd.isna(sma_20):
                    total_indicators += 1
                    if close > float(sma_20):
                        bullish_indicators += 1
                    else:
                        bearish_indicators += 1

                # 2. Medium-term trend (Price vs SMA_50)
                if sma_50 is not None and not pd.isna(sma_50):
                    total_indicators += 1
                    if close > float(sma_50):
                        bullish_indicators += 1
                    else:
                        bearish_indicators += 1

                # 3. Long-term trend (Price vs SMA_200)
                if sma_200 is not None and not pd.isna(sma_200):
                    total_indicators += 2
                    if close > float(sma_200):
                        bullish_indicators += 2
                    else:
                        bearish_indicators += 2

                # 4. MACD trend
                if macd is not None and macd_signal is not None and not pd.isna(macd) and not pd.isna(macd_signal):
                    total_indicators += 1
                    if macd >= macd_signal:
                        bullish_indicators += 1
                    else:
                        bearish_indicators += 1

                # 5. Short-term momentum
                total_indicators += 1
                if five_day_return >= 0.005:
                    bullish_indicators += 1
                elif five_day_return <= -0.01:
                    bearish_indicators += 1

            except Exception as e:
                logger.error(f"Error evaluating regime for {symbol}: {e}")

        if total_indicators == 0:
            logger.warning("No index data available; assuming BULLISH regime fallback")
            self.regime_cache = 'BULLISH'
            self.regime_cache_time = datetime.now()
            return 'BULLISH'

        bullish_ratio = bullish_indicators / total_indicators
        bearish_ratio = bearish_indicators / total_indicators

        logger.info(f"[Market Regime Sentry] Score: Bullish={bullish_ratio:.2f}, Bearish={bearish_ratio:.2f} (Total indicators evaluated: {total_indicators})")

        if bullish_ratio >= 0.60:
            regime = 'BULLISH'
        elif bearish_ratio >= 0.60:
            regime = 'BEARISH'
        else:
            regime = 'NEUTRAL'

        logger.info(f"[Market Regime Sentry] Classified daily broad market direction as: {regime}")
        self.regime_cache = regime
        self.regime_cache_time = datetime.now()
        return regime

    def market_regime_allows_long_trades(self):
        """Require broad-market confirmation before opening long positions."""
        if not config.REQUIRE_MARKET_REGIME_CONFIRMATION:
            return True

        regime = self.get_market_regime()
        if regime == 'BEARISH':
            logger.warning("[Market Regime Sentry] Long trades are restricted during a BEARISH market regime.")
            return False
        return True
    
    def get_fundamental_data(self, symbol):
        """Fetch fundamental data (P/E, market cap, etc.)"""
        try:
            ticker = yf.Ticker(symbol)
            cache_key = symbol.upper()
            if cache_key in self.fundamental_cache:
                age = datetime.now() - self.fundamental_cache_time[cache_key]
                if age.total_seconds() < self.cache_duration:
                    return self.fundamental_cache[cache_key]

            info = ticker.info
            
            fundamentals = {
                'symbol': symbol,
                'price': info.get('currentPrice'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'eps': info.get('trailingEps'),
                'dividend_yield': info.get('dividendYield'),
                '52_week_high': info.get('fiftyTwoWeekHigh'),
                '52_week_low': info.get('fiftyTwoWeekLow'),
                'avg_volume': info.get('averageVolume'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'currency': info.get('currency'),
                'quote_type': info.get('quoteType'),
                'exchange': info.get('exchange'),
                'ex_dividend_date': info.get('exDividendDate') or info.get('dividendDate'),
            }
            
            self.fundamental_cache[cache_key] = fundamentals
            self.fundamental_cache_time[cache_key] = datetime.now()
            return fundamentals
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return None

    def get_calendar_data(self, symbol):
        """Fetch and cache calendar data for 1 hour to prevent redundant API calls"""
        symbol = symbol.upper()
        if symbol in self.calendar_cache:
            age = datetime.now() - self.calendar_cache_time[symbol]
            if age.total_seconds() < 3600:  # 1 hour cache duration
                return self.calendar_cache[symbol]

        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar
            self.calendar_cache[symbol] = calendar
            self.calendar_cache_time[symbol] = datetime.now()
            return calendar
        except Exception as e:
            logger.debug(f"Error fetching calendar for {symbol}: {e}")
            return None

    def is_trade_free_us_stock_candidate(self, symbol):
        """Check whether a symbol fits the low-fee US stock-only universe."""
        if not config.TRADE_FREE_US_STOCKS_ONLY:
            return True

        symbol = symbol.upper()
        starter_symbols = set(config.STARTER_STOCKS) if config.STARTER_ACCOUNT_MODE else set()
        allowed_symbols = set(config.ALLOWED_US_STOCKS) | set(config.AI_INFRA_STOCKS) | starter_symbols
        if symbol not in allowed_symbols or symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
            return False

        fundamentals = self.get_fundamental_data(symbol)
        if not fundamentals:
            return False

        price = fundamentals.get('price') or self.get_current_price(symbol)
        market_cap = fundamentals.get('market_cap')
        avg_volume = fundamentals.get('avg_volume')
        currency = fundamentals.get('currency')
        quote_type = fundamentals.get('quote_type')
        exchange = fundamentals.get('exchange')
        allowed_exchanges = {'NMS', 'NYQ', 'NCM', 'NGM', 'ASE', 'PCX', 'BTS'}
        max_price = min(config.MAX_PRICE, config.STARTER_MAX_PRICE) if config.STARTER_ACCOUNT_MODE else config.MAX_PRICE

        passes = (
            quote_type == 'EQUITY'
            and currency == 'USD'
            and exchange in allowed_exchanges
            and price is not None
            and config.MIN_PRICE <= float(price) <= max_price
            and avg_volume is not None
            and avg_volume >= config.VOLUME_THRESHOLD
        )
        if config.STARTER_ACCOUNT_MODE:
            passes = passes and market_cap is not None and market_cap >= config.STARTER_MIN_MARKET_CAP
        return passes
    
    def get_earnings_date(self, symbol):
        """Get next earnings date using 1-hour cached calendar data"""
        try:
            calendar = self.get_calendar_data(symbol)
            if calendar is None:
                return None

            if isinstance(calendar, dict):
                earnings_date = calendar.get('Earnings Date') or calendar.get('Earnings Date Start')
                if isinstance(earnings_date, list):
                    earnings_date = earnings_date[0] if earnings_date else None
                return self._to_naive_date(earnings_date)

            if hasattr(calendar, "empty") and not calendar.empty:
                if 'Earnings Date' in calendar.columns:
                    earnings_date = calendar.iloc[0]['Earnings Date']
                else:
                    earnings_date = calendar.iloc[0].iloc[0]
                return self._to_naive_date(earnings_date)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get earnings date for {symbol}: {e}")
            return None

    def get_ex_dividend_date(self, symbol):
        """Get the next ex-dividend date using cached calendar or fundamentals data."""
        try:
            # 1. Check cached calendar first
            calendar = self.get_calendar_data(symbol)
            if calendar is not None and isinstance(calendar, dict):
                ex_div = calendar.get('Ex-Dividend Date')
                if ex_div:
                    return self._to_naive_date(ex_div)

            # 2. Check cached/fetched fundamentals
            fundamentals = self.get_fundamental_data(symbol)
            if fundamentals:
                raw_date = fundamentals.get('ex_dividend_date')
                if raw_date:
                    return self._to_naive_date(raw_date)

            return None
        except Exception as e:
            logger.debug(f"Could not get dividend date for {symbol}: {e}")
            return None

    def get_calendar_risk(self, symbol):
        """Return whether earnings/dividend calendar risk should block a new BUY."""
        today = datetime.now().date()
        risk = {
            'blocked': False,
            'reason': '',
            'earnings_date': None,
            'ex_dividend_date': None,
        }

        earnings_date = self.get_earnings_date(symbol)
        if earnings_date:
            risk['earnings_date'] = earnings_date.isoformat()
            days = (earnings_date - today).days
            if -config.EARNINGS_BLACKOUT_DAYS_AFTER <= days <= config.EARNINGS_BLACKOUT_DAYS_BEFORE:
                risk['blocked'] = True
                risk['reason'] = f"earnings blackout: {days} days from earnings"
                return risk

        ex_dividend_date = self.get_ex_dividend_date(symbol)
        if ex_dividend_date:
            risk['ex_dividend_date'] = ex_dividend_date.isoformat()
            days = (ex_dividend_date - today).days
            if -config.DIVIDEND_BLACKOUT_DAYS_AFTER <= days <= config.DIVIDEND_BLACKOUT_DAYS_BEFORE:
                risk['blocked'] = True
                risk['reason'] = f"dividend blackout: {days} days from ex-dividend date"
                return risk

        return risk

    def _to_naive_date(self, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value).date()
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            return value.date()
        try:
            return pd.to_datetime(value).date()
        except Exception:
            return None
    
    def calculate_momentum(self, data, lookback=5):
        """
        Calculate momentum score
        
        Returns value between -1 and 1:
        -1: Strong downward momentum
        0: No momentum
        1: Strong upward momentum
        """
        try:
            if data is None or len(data) < lookback + 1:
                return 0
            
            recent_prices = data['Close'].tail(lookback + 1)
            start_price = recent_prices.iloc[0]
            end_price = recent_prices.iloc[-1]
            
            if start_price == 0:
                return 0
            
            momentum = (end_price - start_price) / start_price
            # Normalize to -1 to 1
            momentum = np.clip(momentum * 100, -1, 1)
            return momentum
            
        except Exception as e:
            logger.error(f"Error calculating momentum: {e}")
            return 0
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()
        self.fundamental_cache.clear()
        self.fundamental_cache_time.clear()
        self.calendar_cache.clear()
        self.calendar_cache_time.clear()
        logger.info("Data cache cleared")
    
    def get_data_summary(self, symbol, data):
        """Get summary of latest data for a stock"""
        try:
            if data is None or data.empty:
                return None
            
            latest = data.iloc[-1]
            
            summary = {
                'symbol': symbol,
                'price': latest['Close'],
                'change': ((latest['Close'] - data.iloc[-2]['Close']) / data.iloc[-2]['Close'] * 100) if len(data) > 1 else 0,
                'volume': latest['Volume'],
                'volume_ratio': latest.get('Volume_Ratio', 1),
                'rsi': latest.get('RSI'),
                'macd': latest.get('MACD'),
                'macd_signal': latest.get('MACD_Signal'),
                'sma_20': latest.get('SMA_20'),
                'sma_50': latest.get('SMA_50'),
                'sma_200': latest.get('SMA_200'),
                '52_week_high': data['Close'].max(),
                '52_week_low': data['Close'].min(),
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting data summary: {e}")
            return None
