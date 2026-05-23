from utils import get_logger
import config
from datetime import datetime
from pandas import isna as pd_isna
from data_fetcher import DataFetcher
from news_sentiment import NewsSentiment

logger = get_logger(__name__)

class TradingStrategy:
    """Base trading strategy class"""
    
    def __init__(self, ib_connection, risk_manager=None):
        self.ib_connection = ib_connection
        self.risk_manager = risk_manager
        self.daily_trades = 0
        self.daily_profit_loss = 0
        self.active_positions = {}
        self.data_fetcher = DataFetcher()
        self.sentiment_analyzer = NewsSentiment()
        
    def check_trading_conditions(self):
        """Check if strategy should execute trades"""
        raise NotImplementedError("Subclasses must implement check_trading_conditions")
        
    def generate_signals(self):
        """Generate trading signals"""
        raise NotImplementedError("Subclasses must implement generate_signals")
        
    def execute_trades(self, signals):
        """Execute trades based on signals"""
        raise NotImplementedError("Subclasses must implement execute_trades")
        
    def check_risk_limits(self):
        """Verify position is within risk limits"""
        if self.daily_profit_loss < -config.MAX_DAILY_LOSS:
            logger.warning(f"Daily loss limit reached: ${self.daily_profit_loss:.2f}")
            return False
        if self.daily_trades >= config.MAX_DAILY_TRADES:
            logger.warning(f"Daily trade limit reached: {self.daily_trades}")
            return False
        if self.risk_manager and not self.risk_manager.is_trading_allowed():
            return False
        return True
        
    def reset_daily_stats(self):
        """Reset daily statistics"""
        self.daily_trades = 0
        self.daily_profit_loss = 0


class MomentumStrategy(TradingStrategy):
    """Momentum-based trading strategy with real data and technical indicators"""
    
    def __init__(self, ib_connection, risk_manager=None):
        super().__init__(ib_connection, risk_manager)
        self.price_history = {}
        self.last_signals = {}
        self.data_cache = {}
        
    def get_trading_blockers(self):
        """Human-readable reasons new trades are blocked (empty list = OK to trade)."""
        from utils import is_market_open

        blockers = []
        if not is_market_open():
            blockers.append("market_closed")
        if not self.check_risk_limits():
            blockers.append("risk_limits")
        if config.REQUIRE_NEWS_CHECK and not self.sentiment_analyzer.market_news_allows_trading():
            blockers.append("market_news_risk")
        if not self.data_fetcher.market_regime_allows_long_trades():
            blockers.append("market_regime")
        return blockers

    def check_trading_conditions(self):
        """Check if market conditions are favorable for trading"""
        blockers = self.get_trading_blockers()
        if blockers:
            logger.warning("Trading conditions not met: %s", ", ".join(blockers))
            return False
        return True
        
    def generate_signals(self, symbols):
        """
        Generate trading signals using real data and technical indicators
        Returns dict with symbol -> signal ('BUY', 'SELL', or 'HOLD')
        """
        signals = {}
        
        for symbol in symbols:
            try:
                if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                    logger.warning(f"Skipping {symbol}: excluded event-sensitive stock")
                    signals[symbol] = 'HOLD'
                    continue

                if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                    logger.warning(f"Skipping {symbol}: not in configured US free-trade stock universe")
                    signals[symbol] = 'HOLD'
                    continue

                calendar_risk = self.data_fetcher.get_calendar_risk(symbol)
                if calendar_risk['blocked']:
                    logger.warning(f"Skipping {symbol}: {calendar_risk['reason']}")
                    signals[symbol] = 'HOLD'
                    continue

                # Get real data from Yahoo Finance
                data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                
                if data is None or len(data) < 50:
                    signals[symbol] = 'HOLD'
                    continue
                
                # Check news sentiment (skip if risky)
                if not self.sentiment_analyzer.should_trade_based_on_news(symbol):
                    logger.warning(f"Skipping {symbol} due to negative news")
                    signals[symbol] = 'HOLD'
                    continue

                sentiment = self.sentiment_analyzer.get_news_sentiment(symbol, limit=5)
                if config.REQUIRE_BULLISH_NEWS_FOR_BUY and sentiment != 'BULLISH':
                    logger.info(f"Skipping {symbol}: latest news sentiment is {sentiment}, not BULLISH")
                    signals[symbol] = 'HOLD'
                    continue
                
                # Analyze with technical indicators
                signal = self._analyze_technical(symbol, data)
                signals[symbol] = signal
                
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                signals[symbol] = 'HOLD'
        
        return signals
    
    def _analyze_technical(self, symbol, data):
        """
        Analyze technical indicators to generate signal
        
        Returns: 'BUY', 'SELL', or 'HOLD'
        """
        try:
            if data is None or len(data) < 50:
                return 'HOLD'
            
            latest = data.iloc[-1]
            price = float(latest['Close'])
            
            # Technical indicators
            rsi = latest.get('RSI')
            sma_20 = latest.get('SMA_20')
            sma_50 = latest.get('SMA_50')
            sma_200 = latest.get('SMA_200')
            macd = latest.get('MACD')
            macd_signal = latest.get('MACD_Signal')
            volume_ratio = latest.get('Volume_Ratio', 1)
            previous_close = float(data.iloc[-2]['Close'])
            five_day_close = float(data.iloc[-6]['Close']) if len(data) >= 6 else previous_close
            one_day_change = (price - previous_close) / previous_close
            five_day_change = (price - five_day_close) / five_day_close

            if one_day_change < config.MIN_BUY_1D_CHANGE or five_day_change < config.MIN_BUY_5D_CHANGE:
                return 'HOLD'
            if volume_ratio is None or pd_isna(volume_ratio) or float(volume_ratio) < config.MIN_BUY_VOLUME_RATIO:
                return 'HOLD'
            
            buy_signals = 0
            sell_signals = 0
            
            # Signal 1: RSI Oversold (< 30) = BUY signal
            if rsi is not None and rsi < 30:
                buy_signals += 2
            elif rsi is not None and rsi > 70:
                sell_signals += 2
            elif rsi is not None and 40 < rsi < 60:
                buy_signals += 1  # Neutral zone
            
            # Signal 2: Price above moving averages = BUY
            if sma_20 is not None and not pd_isna(sma_20) and price > float(sma_20):
                buy_signals += 1
            elif sma_20 is not None and not pd_isna(sma_20):
                sell_signals += 1
            
            if sma_50 is not None and not pd_isna(sma_50) and price > float(sma_50):
                buy_signals += 1
            elif sma_50 is not None and not pd_isna(sma_50):
                sell_signals += 1
            
            # Signal 3: Price above 200-day MA = Strong uptrend
            if sma_200 is not None and not pd_isna(sma_200) and price > float(sma_200):
                buy_signals += 1
            
            # Signal 4: MACD crossover
            if macd is not None and macd_signal is not None and not pd_isna(macd) and not pd_isna(macd_signal):
                if float(macd) > float(macd_signal):
                    buy_signals += 1
                else:
                    sell_signals += 1
            
            # Signal 5: Volume above average = Strength confirmation
            if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) > 1.2:
                if buy_signals > sell_signals:
                    buy_signals += 1
            elif volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) < 0.8:
                if sell_signals > buy_signals:
                    sell_signals += 1
            
            # Decision logic
            if buy_signals >= config.MIN_BUY_SIGNALS_FOR_ENTRY:
                return 'BUY'
            elif sell_signals >= config.MIN_SELL_SIGNALS_FOR_ENTRY:
                return 'SELL'
            elif buy_signals > sell_signals:
                return 'BUY' if buy_signals >= config.MIN_WEAK_BUY_SIGNALS else 'HOLD'
            elif sell_signals > buy_signals:
                return 'SELL' if sell_signals >= config.MIN_WEAK_BUY_SIGNALS else 'HOLD'
            else:
                return 'HOLD'
                
        except Exception as e:
            logger.error(f"Error analyzing technical signals for {symbol}: {e}")
            return 'HOLD'
        
    def execute_trades(self, signals):
        """Execute trades based on signals"""
        from engine_control import is_shutting_down

        if is_shutting_down():
            signals = {symbol: action for symbol, action in signals.items() if action == "SELL"}

        # Separate into SELL and BUY signals
        sell_signals = {sym: sig for sym, sig in signals.items() if sig == 'SELL'}
        buy_signals = {sym: sig for sym, sig in signals.items() if sig == 'BUY'}

        # 1. Process all SELL signals first in a separate pass to clear positions and free up capital.
        positions = self.ib_connection.get_positions()
        
        for symbol in sell_signals:
            if symbol in positions:
                try:
                    qty = positions[symbol]['quantity']
                    if qty <= 0:
                        continue
                    limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                    if limit_price is None:
                        logger.warning(f"Skipping {symbol}: unable to calculate SELL limit price")
                        continue
                    order_id = self.ib_connection.place_order(
                        symbol,
                        "SELL",
                        qty,
                        order_type="LMT",
                        limit_price=limit_price,
                        metadata={
                            "entry_price": positions[symbol].get("avg_cost"),
                        },
                    )
                    
                    if order_id:
                        self.daily_trades += 1
                        logger.info(f"SELL signal executed for {symbol}")
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                        if self.risk_manager:
                            self.risk_manager.remove_position(symbol)
                        try:
                            from daily_positions import record_close
                            record_close(symbol)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Error executing SELL for {symbol}: {e}")

        # 2. Refresh positions and available buying funds.
        positions = self.ib_connection.get_positions()
        buying_funds = self.ib_connection.get_available_funds_for_buys()
        
        # 3. Process BUY signals in a second pass
        for symbol in buy_signals:
            # Re-check daily trade limits dynamically
            if self.daily_trades >= config.MAX_DAILY_TRADES:
                logger.info(f"Daily trade limit reached during execution: {self.daily_trades}/{config.MAX_DAILY_TRADES}")
                break
                
            # Re-check position limit dynamically
            if len(positions) >= config.MAX_OPEN_POSITIONS:
                logger.info(
                    f"Max open positions reached: {len(positions)}/{config.MAX_OPEN_POSITIONS} — new buys blocked"
                )
                break

            if symbol in positions:
                # Already own this stock, skip
                continue

            if self.ib_connection.has_active_order(symbol, "BUY"):
                logger.info(f"Skipping BUY for {symbol}: BUY order is already pending.")
                continue

            try:
                if buying_funds <= 0:
                    logger.warning("No settled/available funds reported by IB; blocking BUY")
                    break

                # Check if we have sufficient cash
                position_size = min(
                    config.MAX_POSITION_SIZE,
                    buying_funds * config.POSITION_SIZE_PERCENT
                )
                
                if position_size > 0:
                    # Get current price
                    current_price = self.data_fetcher.get_current_price(symbol)
                    
                    if current_price is not None and current_price > 0:
                        quantity = max(1, int(position_size / current_price))
                        if self.risk_manager and not self.risk_manager.is_within_limits(symbol, quantity, current_price):
                            continue

                        limit_price = self.data_fetcher.get_limit_price(symbol, "BUY")
                        if limit_price is None:
                            logger.warning(f"Skipping {symbol}: unable to calculate BUY limit price")
                            continue

                        order_id = self.ib_connection.place_order(
                            symbol,
                            "BUY",
                            quantity,
                            order_type="LMT",
                            limit_price=limit_price,
                            metadata={
                                "entry_price": current_price,
                            },
                        )
                        
                        if order_id:
                            self.active_positions[symbol] = {
                                'entry_price': current_price,
                                'quantity': quantity,
                                'order_id': order_id
                            }
                            if self.risk_manager:
                                self.risk_manager.add_position(symbol, quantity, current_price)
                                self.risk_manager.set_stop_loss(symbol, current_price, config.STOP_LOSS_PERCENT)
                                self.risk_manager.set_take_profit(symbol, current_price, config.TAKE_PROFIT_PERCENT)
                            try:
                                from daily_positions import record_open
                                record_open(symbol, quantity, current_price, order_id)
                            except Exception:
                                pass
                            self.daily_trades += 1
                            logger.info(f"BUY signal submitted for {symbol} @ limit ${limit_price:.2f}")
                            
                            # Update local tracker variables so subsequent loop iterations are correct
                            positions[symbol] = {
                                'quantity': quantity,
                                'avg_cost': current_price
                            }
                            buying_funds -= (quantity * limit_price)
                            
            except Exception as e:
                logger.error(f"Error executing BUY for {symbol}: {e}")
        
        
class GridTradingStrategy(TradingStrategy):
    """Grid trading strategy - buys at regular intervals"""
    
    def __init__(self, ib_connection, symbol, grid_size=10, grid_interval=50):
        super().__init__(ib_connection)
        self.symbol = symbol
        self.grid_size = grid_size  # Number of grid levels
        self.grid_interval = grid_interval  # Price difference between grids
        self.grid_orders = {}  # Track grid orders
        self.base_price = None
        
    def check_trading_conditions(self):
        """Check if market conditions allow grid trading"""
        from utils import is_market_open
        return is_market_open() and self.check_risk_limits()
        
    def generate_signals(self):
        """Generate grid trading signals"""
        # Get current price and establish grid if needed
        current_price = self._get_current_price(self.symbol)
        
        if self.base_price is None and current_price:
            self.base_price = current_price
            return self._create_grid()
            
        return {}
        
    def execute_trades(self, signals):
        """Execute grid trades"""
        for price_level, signal in signals.items():
            try:
                if signal == 'BUY':
                    order_id = self.ib_connection.place_order(
                        self.symbol, "BUY", 100, order_type="LMT", limit_price=price_level
                    )
                    if order_id:
                        self.grid_orders[price_level] = order_id
                        
            except Exception as e:
                logger.error(f"Error in grid trading: {e}")
                
    def _create_grid(self):
        """Create grid price levels"""
        signals = {}
        for i in range(self.grid_size):
            price = self.base_price - (i * self.grid_interval)
            if price > 0:
                signals[price] = 'BUY'
        return signals
        
    def _get_current_price(self, symbol):
        """Get current price for a symbol"""
        return None
