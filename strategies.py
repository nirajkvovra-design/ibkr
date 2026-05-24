from utils import get_logger
import config
from datetime import datetime
import pandas as pd
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

        # Get market regime and scale sizes/risk levels dynamically
        regime = self.data_fetcher.get_market_regime()
        size_multiplier = 1.0
        sl_percent = config.STOP_LOSS_PERCENT
        tp_percent = config.TAKE_PROFIT_PERCENT

        if regime == 'NEUTRAL':
            size_multiplier = config.REGIME_NEUTRAL_SIZE_MULTIPLIER
            sl_percent = config.STOP_LOSS_PERCENT * config.REGIME_NEUTRAL_SL_TP_MULTIPLIER
            tp_percent = config.TAKE_PROFIT_PERCENT * config.REGIME_NEUTRAL_SL_TP_MULTIPLIER
            logger.info(f"[Market Regime Executor] NEUTRAL market: Scaling position size by {size_multiplier}x, SL to {sl_percent:.2f}%, TP to {tp_percent:.2f}%")
        elif regime == 'BEARISH':
            size_multiplier = config.REGIME_BEARISH_SIZE_MULTIPLIER
            sl_percent = config.STOP_LOSS_PERCENT * config.REGIME_BEARISH_SL_MULTIPLIER
            logger.info(f"[Market Regime Executor] BEARISH market: Scaling position size by {size_multiplier}x, SL to {sl_percent:.2f}% (capital preservation active)")

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
                max_pos_cap = config.MAX_POSITION_SIZE
                account_val = self.ib_connection.get_account_value()
                if getattr(config, "DYNAMIC_RISK_SCALING", True) and account_val > 0:
                    max_pos_cap = account_val * config.MAX_PORTFOLIO_POSITION_PERCENT

                position_size = min(
                    max_pos_cap,
                    buying_funds * config.POSITION_SIZE_PERCENT
                ) * size_multiplier
                
                if position_size > 0:
                    current_price = self.data_fetcher.get_current_price(symbol)
                    
                    if current_price is not None and current_price > 0:
                        # Sizing adjustments: scale by multipliers for futures, support fractionals for crypto
                        import os
                        multiplier = 1
                        clean_sym = symbol.upper().replace("-USD", "").replace("=F", "")
                        crypto_list = getattr(config, "CRYPTO_SYMBOLS", ["BTC", "ETH", "LTC", "BCH"])
                        futures_list = getattr(config, "FUTURE_SYMBOLS", ["ES", "NQ", "YM", "CL", "GC"])
                        
                        is_crypto = symbol.upper() in crypto_list or symbol.upper().endswith("-USD") or os.getenv(f"CRYPTO_EXCHANGE_{clean_sym}") is not None
                        is_future = symbol.upper() in futures_list or symbol.upper().endswith("=F") or os.getenv(f"FUTURE_EXCHANGE_{clean_sym}") is not None

                        if is_future:
                            multipliers = getattr(config, "FUTURE_MULTIPLIERS", {})
                            env_val = os.getenv(f"FUTURE_MULTIPLIER_{clean_sym}")
                            multiplier = int(env_val) if env_val is not None else multipliers.get(clean_sym, 1)
                            quantity = max(1, int(position_size / (current_price * multiplier)))
                        elif is_crypto:
                            quantity = round(position_size / current_price, 4)
                        else:
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
                                self.risk_manager.set_stop_loss(symbol, current_price, sl_percent)
                                self.risk_manager.set_take_profit(symbol, current_price, tp_percent)
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


class MachineLearningStrategy(MomentumStrategy):
    """
    Machine Learning and Stochastic Forecasting Strategy.
    Uses Monte Carlo Geometric Brownian Motion, LSTM, or RNN models to generate signals.
    Inherits execution and data pipeline features from MomentumStrategy.
    """

    def __init__(self, ib_connection, risk_manager=None):
        super().__init__(ib_connection, risk_manager)
        logger.info(f"Initialized MachineLearningStrategy with model: {config.ML_MODEL_TYPE}")

    def generate_signals(self, symbols):
        """
        Generate trading signals using predictive ML models.
        Returns dict with symbol -> signal ('BUY', 'SELL', or 'HOLD')
        """
        import ml_models
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
                
                if data is None or len(data) < 25:
                    logger.warning(f"Skipping {symbol}: insufficient historical data (length={0 if data is None else len(data)})")
                    signals[symbol] = 'HOLD'
                    continue
                
                # Check news sentiment safety
                if not self.sentiment_analyzer.should_trade_based_on_news(symbol):
                    logger.warning(f"Skipping {symbol} due to negative news")
                    signals[symbol] = 'HOLD'
                    continue

                sentiment = self.sentiment_analyzer.get_news_sentiment(symbol, limit=5)
                if config.REQUIRE_BULLISH_NEWS_FOR_BUY and sentiment != 'BULLISH':
                    logger.info(f"Skipping {symbol}: latest news sentiment is {sentiment}, not BULLISH")
                    signals[symbol] = 'HOLD'
                    continue
                
                # Run the selected predictive model
                model_type = config.ML_MODEL_TYPE.upper()
                expected_return = 0.0
                
                if model_type == 'MONTE_CARLO':
                    _, metrics = ml_models.MonteCarloGBMModel.simulate_gbm(
                        data['Close'], 
                        forecast_period=config.ML_FORECAST_PERIOD, 
                        num_simulations=config.ML_MONTE_CARLO_SIMULATIONS
                    )
                    expected_return = metrics['expected_return_pct']
                    logger.info(f"ML [Monte Carlo GBM] {symbol}: Current=${metrics['latest_actual_price']:.2f} | Expected=${metrics['expected_final_price']:.2f} | Chg={expected_return:+.2f}% | ProbProfit={metrics['probability_of_profit']:.1f}%")
                    
                elif model_type in ('LSTM', 'RNN'):
                    forecaster = ml_models.LSTMForecaster if model_type == 'LSTM' else ml_models.RNNForecaster
                    
                    if not forecaster.is_supported():
                        logger.warning(f"Model {model_type} is configured, but TensorFlow or scikit-learn is not installed. Falling back to Monte Carlo GBM.")
                        _, metrics = ml_models.MonteCarloGBMModel.simulate_gbm(
                            data['Close'], 
                            forecast_period=config.ML_FORECAST_PERIOD, 
                            num_simulations=config.ML_MONTE_CARLO_SIMULATIONS
                        )
                        expected_return = metrics['expected_return_pct']
                        logger.info(f"ML [Monte Carlo GBM Fallback] {symbol}: Current=${metrics['latest_actual_price']:.2f} | Expected=${metrics['expected_final_price']:.2f} | Chg={expected_return:+.2f}%")
                    else:
                        _, metrics = forecaster.forecast_next_price(
                            data['Close'],
                            window_size=config.ML_NEURAL_WINDOW_SIZE,
                            epochs=config.ML_NEURAL_EPOCHS
                        )
                        expected_return = metrics['expected_return_pct']
                        logger.info(f"ML [{model_type}] {symbol}: Current=${metrics['latest_actual_price']:.2f} | Expected=${metrics['expected_final_price']:.2f} | Expected Return={expected_return:+.2f}%")
                else:
                    logger.error(f"Unknown ML model type configured: {model_type}. Skipping signal generation.")
                    signals[symbol] = 'HOLD'
                    continue

                # Generate signals based on predictive thresholds
                if expected_return >= config.ML_BUY_THRESHOLD_PERCENT:
                    signals[symbol] = 'BUY'
                elif expected_return <= config.ML_SELL_THRESHOLD_PERCENT:
                    signals[symbol] = 'SELL'
                else:
                    signals[symbol] = 'HOLD'
                
            except Exception as e:
                logger.error(f"Error generating ML signal for {symbol}: {e}")
                signals[symbol] = 'HOLD'
        
        return signals


class PairsTradingStrategy(TradingStrategy):
    """
    Hedge-Fund Grade Cointegrated Pairs Trading (Statistical Arbitrage) Strategy.
    Monitors relative asset ratios and executes mean-reversion trades.
    """

    def __init__(self, ib_connection, risk_manager=None):
        super().__init__(ib_connection, risk_manager)
        logger.info(f"Initialized PairsTradingStrategy with pairs: {config.PAIRS_WATCHLIST}")

    def check_trading_conditions(self):
        """Standard market open check"""
        from utils import is_market_open
        return is_market_open() and self.check_risk_limits()

    def generate_signals(self, symbols):
        """
        Generate paired BUY/SELL signals based on rolling Z-Scores.
        """
        signals = {symbol: 'HOLD' for symbol in symbols}
        positions = self.ib_connection.get_positions()

        # Step through each configured cointegrated pair
        for sym_a, sym_b in config.PAIRS_WATCHLIST:
            # We must have both symbols in our active watchlist to trade them
            if sym_a not in symbols or sym_b not in symbols:
                continue

            try:
                # Get historical prices
                data_a = self.data_fetcher.get_stock_data(sym_a, period='3mo', interval='1d')
                data_b = self.data_fetcher.get_stock_data(sym_b, period='3mo', interval='1d')

                if data_a is None or data_b is None or len(data_a) < config.PAIRS_LOOKBACK or len(data_b) < config.PAIRS_LOOKBACK:
                    continue

                # Align datasets by index
                aligned_df = pd.DataFrame({
                    'close_a': data_a['Close'],
                    'close_b': data_b['Close']
                }).dropna()

                if len(aligned_df) < config.PAIRS_LOOKBACK:
                    continue

                # Calculate price ratio (A / B)
                ratios = aligned_df['close_a'] / aligned_df['close_b']
                current_ratio = ratios.iloc[-1]

                # Compute rolling Z-Score of the ratio
                rolling_mean = ratios.rolling(window=config.PAIRS_LOOKBACK).mean()
                rolling_std = ratios.rolling(window=config.PAIRS_LOOKBACK).std()
                
                latest_std = rolling_std.iloc[-1]
                if latest_std == 0:
                    latest_std = 0.0001
                    
                z_score = (current_ratio - rolling_mean.iloc[-1]) / latest_std

                logger.info(f"Pairs Trade [{sym_a} vs {sym_b}]: PriceA=${aligned_df['close_a'].iloc[-1]:.2f} | PriceB=${aligned_df['close_b'].iloc[-1]:.2f} | Ratio={current_ratio:.4f} | Z-Score={z_score:+.2f}")

                has_a = sym_a in positions
                has_b = sym_b in positions

                # Trading Decision Rules
                if z_score >= config.PAIRS_ENTRY_ZSCORE:
                    # Stock A is overvalued relative to Stock B
                    # Action: SELL A (close long if we have it), BUY B (open long if we don't have it)
                    if has_a:
                        signals[sym_a] = 'SELL'
                    if not has_b:
                        signals[sym_b] = 'BUY'
                        
                elif z_score <= -config.PAIRS_ENTRY_ZSCORE:
                    # Stock A is undervalued relative to Stock B
                    # Action: BUY A (open long if we don't have it), SELL B (close long if we have it)
                    if not has_a:
                        signals[sym_a] = 'BUY'
                    if has_b:
                        signals[sym_b] = 'SELL'
                        
                elif abs(z_score) <= config.PAIRS_EXIT_ZSCORE:
                    # Cointegration reverted back to mean. Close both positions to lock in gains!
                    if has_a:
                        signals[sym_a] = 'SELL'
                    if has_b:
                        signals[sym_b] = 'SELL'

            except Exception as e:
                logger.error(f"Error calculating pairs signals for {sym_a}-{sym_b}: {e}")

        return signals

    def execute_trades(self, signals):
        """Leverage the MomentumStrategy's robust sequential execute pass"""
        # Instantiate a helper momentum strategy to run the exact same execute pipeline
        executor = MomentumStrategy(self.ib_connection, self.risk_manager)
        executor.daily_trades = self.daily_trades
        executor.execute_trades(signals)
        self.daily_trades = executor.daily_trades


class VolatilityBreakoutStrategy(MomentumStrategy):
    """
    Volatility Breakout Strategy (ATR + Donchian Channels).
    Identifies high-velocity breakouts from compressed pricing bands.
    """

    def __init__(self, ib_connection, risk_manager=None):
        super().__init__(ib_connection, risk_manager)
        logger.info(f"Initialized VolatilityBreakoutStrategy with lookback: {config.BREAKOUT_LOOKBACK}")

    def generate_signals(self, symbols):
        """
        Generate breakout trading signals.
        """
        signals = {}
        
        for symbol in symbols:
            try:
                if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                    signals[symbol] = 'HOLD'
                    continue

                if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                    signals[symbol] = 'HOLD'
                    continue

                # Get historical data
                data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                
                if data is None or len(data) < config.BREAKOUT_LOOKBACK + 5:
                    signals[symbol] = 'HOLD'
                    continue
                
                # Check news sentiment safety
                if not self.sentiment_analyzer.should_trade_based_on_news(symbol):
                    signals[symbol] = 'HOLD'
                    continue

                close = data['Close']
                high = data['High']
                low = data['Low']
                atr = data['ATR']
                volume_ratio = data.get('Volume_Ratio', 1)

                latest_close = float(close.iloc[-1])
                latest_atr = float(atr.iloc[-1])

                # Donchian channel calculation (excluding the current day to prevent look-ahead bias)
                upper_channel = high.iloc[-(config.BREAKOUT_LOOKBACK + 1):-1].max()
                lower_channel = low.iloc[-(config.BREAKOUT_LOOKBACK + 1):-1].min()

                # Trigger Threshold: Upper channel + K * ATR
                buy_trigger = upper_channel + (config.BREAKOUT_ATR_MULTIPLIER * latest_atr)

                logger.info(f"Breakout Check [{symbol}]: Price=${latest_close:.2f} | UpperBand=${upper_channel:.2f} | BuyTrigger=${buy_trigger:.2f} | LowerBand=${lower_channel:.2f}")

                # Check BUY trigger (breakout on above-average volume)
                if latest_close >= buy_trigger and volume_ratio is not None and float(volume_ratio) >= 1.1:
                    signals[symbol] = 'BUY'
                # Check SELL trigger (exit when drops below lower band)
                elif latest_close <= lower_channel:
                    signals[symbol] = 'SELL'
                else:
                    signals[symbol] = 'HOLD'

            except Exception as e:
                logger.error(f"Error checking volatility breakout for {symbol}: {e}")
                signals[symbol] = 'HOLD'

        return signals


class IPOBreakoutStrategy(MomentumStrategy):
    """
    IPO Momentum Breakout & Chart Reading Strategy.
    Identifies newly listed stocks breaking out of range highs on expanding volume
    and utilizes a trailing 10-day EMA for support exits.
    """

    def __init__(self, ib_connection, risk_manager=None):
        super().__init__(ib_connection, risk_manager)
        logger.info(f"Initialized IPOBreakoutStrategy. Max listing age: {config.IPO_MAX_HISTORY_DAYS} days.")

    def generate_signals(self, symbols):
        """Generate IPO momentum signals based on stock chart breakouts"""
        signals = {}
        
        for symbol in symbols:
            try:
                if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                    signals[symbol] = 'HOLD'
                    continue

                if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                    signals[symbol] = 'HOLD'
                    continue

                # Fetch quotes (6 months)
                data = self.data_fetcher.get_stock_data(symbol, period='6mo', interval='1d')
                
                if data is None or len(data) < config.IPO_MIN_BASE_DAYS:
                    signals[symbol] = 'HOLD'
                    continue
                
                # Sieve IPO criteria: must have fewer than max history days
                history_days = len(data)
                if history_days > config.IPO_MAX_HISTORY_DAYS:
                    logger.debug(f"Skipping {symbol} IPO Strategy: listing age is {history_days} days (exceeds cap of {config.IPO_MAX_HISTORY_DAYS})")
                    signals[symbol] = 'HOLD'
                    continue

                # Check news sentiment safety
                if not self.sentiment_analyzer.should_trade_based_on_news(symbol):
                    signals[symbol] = 'HOLD'
                    continue

                close = data['Close']
                high = data['High']
                volume_ratio = data.get('Volume_Ratio', 1.0)

                latest_close = float(close.iloc[-1])
                
                # Check for listing high (excluding first 2 days to bypass extreme listing day frenzy)
                if history_days <= 3:
                    logger.info(f"Skipping {symbol} IPO: forming early base (age: {history_days} days)")
                    signals[symbol] = 'HOLD'
                    continue

                listing_high = high.iloc[2:-1].max()
                
                # Compute 10-day Exponential Moving Average (EMA) as support
                ema_10 = close.ewm(span=10, adjust=False).mean()
                latest_ema = float(ema_10.iloc[-1])

                logger.info(f"IPO Chart Sentry [{symbol}]: Price=${latest_close:.2f} | Base High=${listing_high:.2f} | 10D-EMA=${latest_ema:.2f} | VolRatio={volume_ratio:.2f}x")

                # Trigger BUY on breakout over maximum base high on expanding volume
                if latest_close >= listing_high and volume_ratio is not None and float(volume_ratio) >= config.IPO_BREAKOUT_VOLUME_RATIO and latest_close >= latest_ema:
                    signals[symbol] = 'BUY'
                # Trigger SELL on cross under 10-day EMA support
                elif latest_close < latest_ema:
                    signals[symbol] = 'SELL'
                else:
                    signals[symbol] = 'HOLD'

            except Exception as e:
                logger.error(f"Error checking IPO breakout for {symbol}: {e}")
                signals[symbol] = 'HOLD'

        return signals


