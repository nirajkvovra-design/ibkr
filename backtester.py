import os
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Local imports
import config
from data_fetcher import DataFetcher
from risk_manager import RiskManager
from utils import get_logger, calculate_transaction_cost

logger = get_logger("backtester")

class MockIBConnection:
    """Mock Interactive Brokers Connection layer for virtual portfolio tracking"""
    
    def __init__(self, starting_cash=10000.0):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions = {}
        self.trades = []
        self.active_orders = {}
        self.connected = True
        self.account_value = starting_cash

    def get_positions(self):
        return self.positions

    def get_available_funds_for_buys(self):
        return self.cash

    def has_active_order(self, symbol, side):
        return self.active_orders.get(f"{symbol}_{side}", False)

    def get_account_value(self):
        return self.account_value

    def get_cash(self):
        return self.cash

    def get_account_snapshot(self):
        return {
            'net_liquidation': self.account_value,
            'total_cash': self.cash,
            'available_funds': self.cash,
            'settled_cash': self.cash,
            'funds_for_new_buys': self.cash
        }

    def place_order(self, symbol, side, quantity, order_type="LMT", limit_price=0, metadata=None):
        trade_date = metadata.get("date") if metadata else None
        
        # Calculate commission fee
        fee = calculate_transaction_cost(quantity, limit_price, side)
        trade_value = quantity * limit_price
        
        if side.upper() == "BUY":
            total_cost = trade_value + fee
            if total_cost > self.cash:
                logger.warning(f"[{trade_date}] Mock BUY Rejected: Insufficient cash (Need ${total_cost:.2f}, Have ${self.cash:.2f})")
                return None
                
            self.cash -= total_cost
            if symbol in self.positions:
                # Average down / scale position
                old_qty = self.positions[symbol]['quantity']
                old_cost = self.positions[symbol]['avg_cost']
                new_qty = old_qty + quantity
                new_cost = ((old_cost * old_qty) + (limit_price * quantity)) / new_qty
                self.positions[symbol] = {'quantity': new_qty, 'avg_cost': new_cost}
            else:
                self.positions[symbol] = {'quantity': quantity, 'avg_cost': limit_price}
                
        elif side.upper() == "SELL":
            if symbol not in self.positions:
                logger.warning(f"[{trade_date}] Mock SELL Rejected: No open position for {symbol}")
                return None
                
            qty_held = self.positions[symbol]['quantity']
            qty_to_sell = min(quantity, qty_held)
            
            self.cash += (qty_to_sell * limit_price) - fee
            
            if qty_to_sell == qty_held:
                del self.positions[symbol]
            else:
                self.positions[symbol]['quantity'] -= qty_to_sell
                
        trade_record = {
            "date": trade_date,
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "price": limit_price,
            "fee": fee,
            "total_value": trade_value
        }
        self.trades.append(trade_record)
        return 100000 + len(self.trades)

    def refresh_account_data(self):
        pass

    def cancel_stale_orders(self):
        pass

    def has_pending_orders(self):
        return False

    def wait_for_pending_orders(self, timeout=60):
        return True

    def disconnect(self):
        self.connected = False


class MockDataFetcher(DataFetcher):
    """Mock DataFetcher that slices yfinance bars day-by-day to prevent look-ahead bias"""
    
    def __init__(self, historical_data):
        super().__init__()
        self.historical_data = historical_data
        self.current_sim_date = None

    def get_stock_data(self, symbol, period='3mo', interval='1d'):
        """Return historical stock data sliced up to the current simulated date T"""
        if symbol not in self.historical_data:
            return None
            
        full_df = self.historical_data[symbol]
        if self.current_sim_date is None:
            return full_df.iloc[:20]  # return small chunk if no sim date set
            
        # Slice data up to current simulated date T
        sliced_df = full_df[full_df.index <= self.current_sim_date]
        return sliced_df

    def get_current_price(self, symbol):
        if symbol not in self.historical_data or self.current_sim_date is None:
            return None
            
        full_df = self.historical_data[symbol]
        sliced_df = full_df[full_df.index <= self.current_sim_date]
        if sliced_df.empty:
            return None
        return float(sliced_df['Close'].iloc[-1])

    def get_fundamental_data(self, symbol):
        """Simulate basic fundamental data for risk calculations"""
        price = self.get_current_price(symbol)
        if price is None:
            return None
            
        return {
            'symbol': symbol,
            'price': price,
            'market_cap': 10_000_000_000,  # Mock large cap
            'pe_ratio': 15.0,
            'eps': 3.5,
            'dividend_yield': 0.02,
            'avg_volume': 2_000_000,
            'quote_type': 'EQUITY',
            'currency': 'USD',
            'exchange': 'NMS'
        }

    def get_calendar_risk(self, symbol):
        """Ignore blackout dates during backtests for simplified testing"""
        return {'blocked': False, 'reason': '', 'earnings_date': None, 'ex_dividend_date': None}


class BacktestEngine:
    """Historical trading simulator and performance calculator"""
    
    def __init__(self, tickers, start_date, end_date, starting_cash=10000.0):
        self.tickers = [t.upper() for t in tickers]
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.starting_cash = starting_cash
        self.historical_data = {}
        self.ib_mock = None
        self.data_fetcher_mock = None
        self.risk_manager = None
        self.strategy = None

    def load_data(self):
        """Pre-fetch all daily bar histories for the backtest window from Yahoo Finance"""
        logger.info(f"Downloading historical quotes for backtest: {self.tickers}...")
        
        # Download extra buffer bars (e.g. 6 months before start date) to compute moving averages / ML lookbacks
        buffer_start = self.start_date - timedelta(days=120)
        
        for symbol in self.tickers:
            try:
                # Fetch daily bars
                df = yf.download(symbol, start=buffer_start, end=self.end_date, progress=False)
                if df.empty:
                    logger.warning(f"No historical data returned for {symbol}")
                    continue
                    
                # Normalize column headers
                if isinstance(df.columns, pd.MultiIndex):
                    if symbol in df.columns.get_level_values(-1):
                        df = df.xs(symbol, axis=1, level=-1)
                    else:
                        df.columns = df.columns.get_level_values(0)
                        
                # Manually add technical indicators using base fetcher method
                base_fetcher = DataFetcher()
                df = base_fetcher._add_indicators(df)
                
                self.historical_data[symbol] = df
                logger.info(f"Loaded {len(df)} daily bars for {symbol}")
            except Exception as e:
                logger.error(f"Failed to load data for {symbol}: {e}")

    def run(self, strategy_class, model_type=None):
        """Execute the day-by-day historical backtest simulation"""
        if not self.historical_data:
            self.load_data()
            
        # Get intersection of dates where we have data
        all_dates = []
        for df in self.historical_data.values():
            all_dates.extend(df.index.tolist())
        all_dates = sorted(list(set(all_dates)))
        
        # Filter timeline to start_date <= date <= end_date
        sim_dates = [d for d in all_dates if self.start_date <= d <= self.end_date]
        if not sim_dates:
            logger.error("No overlap of simulated dates in historical dataset.")
            return None

        logger.info(f"Starting simulation from {sim_dates[0].strftime('%Y-%m-%d')} to {sim_dates[-1].strftime('%Y-%m-%d')} ({len(sim_dates)} trading days)")

        # Instantiate mocks
        self.ib_mock = MockIBConnection(self.starting_cash)
        self.data_fetcher_mock = MockDataFetcher(self.historical_data)
        self.risk_manager = RiskManager(self.ib_mock)
        
        # Instantiate strategy
        self.strategy = strategy_class(self.ib_mock, self.risk_manager)
        self.strategy.data_fetcher = self.data_fetcher_mock
        
        # Set overrides
        config.PAPER_TRADING = True  # use paper settings for safety
        config.TRADE_FREE_US_STOCKS_ONLY = False  # override lists for flexible test symbols
        config.REQUIRE_MARKET_REGIME_CONFIRMATION = False
        config.REQUIRE_NEWS_CHECK = False
        
        if model_type:
            config.ML_MODEL_TYPE = model_type.upper()
            if model_type.upper() in ('LSTM', 'RNN'):
                config.ML_NEURAL_EPOCHS = 10  # fast training in backtest

        portfolio_history = []

        # Step through timeline day-by-day
        for i, sim_date in enumerate(sim_dates):
            self.data_fetcher_mock.current_sim_date = sim_date
            
            # Update account value (cash + assets value at today's close)
            current_asset_value = 0.0
            positions = self.ib_mock.get_positions()
            
            for symbol, pos in list(positions.items()):
                close_price = self.data_fetcher_mock.get_current_price(symbol)
                if close_price:
                    current_asset_value += pos['quantity'] * close_price
                    
            self.ib_mock.account_value = self.ib_mock.cash + current_asset_value
            self.risk_manager.reset_daily_stats()
            
            # --- 1. Exit Checks (Stop-Loss and Take-Profit) ---
            for symbol, pos in list(positions.items()):
                close_price = self.data_fetcher_mock.get_current_price(symbol)
                if close_price is None:
                    continue
                    
                # Sync positions to risk manager
                self.risk_manager.add_position(symbol, pos['quantity'], pos['avg_cost'])
                if symbol not in self.risk_manager.stop_loss_prices:
                    self.risk_manager.set_stop_loss(symbol, pos['avg_cost'], config.STOP_LOSS_PERCENT)
                    self.risk_manager.set_take_profit(symbol, pos['avg_cost'], config.TAKE_PROFIT_PERCENT)

                # Check triggers
                if self.risk_manager.check_stop_loss(symbol, close_price) or self.risk_manager.check_take_profit(symbol, close_price):
                    self.ib_mock.place_order(
                        symbol, "SELL", pos['quantity'], order_type="LMT", limit_price=close_price, 
                        metadata={"date": sim_date.strftime("%Y-%m-%d")}
                    )
                    self.risk_manager.remove_position(symbol)

            # --- 2. Strategy Logic Generation ---
            # Simulate only on trading cycle
            if i % config.TRADING_LOOP_MINUTES == 0:
                try:
                    # Let the strategy generate signals
                    signals = self.strategy.generate_signals(self.tickers)
                    
                    # Intercept buy signals to attach current simulated date inside order metadata
                    for symbol, action in list(signals.items()):
                        if action == 'BUY':
                            # Let strategy place the BUY orders
                            pass
                            
                    # Clean out HOLD signals
                    active_signals = {sym: act for sym, act in signals.items() if act != 'HOLD'}
                    
                    if active_signals:
                        # Attach date metadata dynamically to simulated place_order calls
                        original_place_order = self.ib_mock.place_order
                        self.ib_mock.place_order = lambda symbol, side, qty, order_type="LMT", limit_price=0, metadata=None: \
                            original_place_order(symbol, side, qty, order_type, limit_price, {"date": sim_date.strftime("%Y-%m-%d")})
                            
                        # Execute strategy trades
                        self.strategy.execute_trades(active_signals)
                        
                        # Restore place_order method
                        self.ib_mock.place_order = original_place_order
                        
                except Exception as e:
                    logger.error(f"Error in simulated trading step on {sim_date.strftime('%Y-%m-%d')}: {e}")

            # Record portfolio metrics daily
            portfolio_history.append({
                "date": sim_date,
                "cash": self.ib_mock.cash,
                "asset_value": current_asset_value,
                "total_value": self.ib_mock.account_value
            })

        # Calculate backtest performance statistics
        history_df = pd.DataFrame(portfolio_history)
        return self._calculate_metrics(history_df)

    def _calculate_metrics(self, history_df):
        """Compute performance metrics (Net Return, Sharpe Ratio, Max Drawdown) from equity curve"""
        if history_df.empty:
            return {}
            
        final_value = history_df['total_value'].iloc[-1]
        cumulative_return_pct = ((final_value - self.starting_cash) / self.starting_cash) * 100
        
        # Calculate daily returns
        history_df['daily_return'] = history_df['total_value'].pct_change().dropna()
        avg_daily_return = history_df['daily_return'].mean()
        std_daily_return = history_df['daily_return'].std()
        
        # Annualized Sharpe Ratio (assuming risk-free rate of 0 for simplicity)
        if std_daily_return and std_daily_return > 0:
            sharpe_ratio = (avg_daily_return / std_daily_return) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # Calculate Max Drawdown
        history_df['peak'] = history_df['total_value'].cummax()
        history_df['drawdown'] = (history_df['total_value'] - history_df['peak']) / history_df['peak'] * 100
        max_drawdown = history_df['drawdown'].min()

        # Trade analytics
        total_trades = len(self.ib_mock.trades)
        buys = [t for t in self.ib_mock.trades if t['side'] == 'BUY']
        sells = [t for t in self.ib_mock.trades if t['side'] == 'SELL']
        
        # Simple win-rate calculation based on closed trades
        # Match Buy/Sell pairs
        profits = []
        buy_prices = {}
        
        for t in self.ib_mock.trades:
            sym = t['symbol']
            side = t['side']
            price = t['price']
            qty = t['quantity']
            
            if side == 'BUY':
                buy_prices[sym] = buy_prices.get(sym, []) + [price] * qty
            elif side == 'SELL':
                if sym in buy_prices and buy_prices[sym]:
                    matching_buys = buy_prices[sym][:qty]
                    buy_prices[sym] = buy_prices[sym][qty:]
                    avg_buy = np.mean(matching_buys)
                    profit = (price - avg_buy) * qty
                    profits.append(profit)
                    
        wins = [p for p in profits if p > 0]
        win_rate = (len(wins) / len(profits) * 100) if profits else 0.0
        total_fees = sum(t['fee'] for t in self.ib_mock.trades)

        return {
            "initial_capital": self.starting_cash,
            "final_capital": final_value,
            "net_return_pct": cumulative_return_pct,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown_pct": max_drawdown,
            "total_trades": total_trades,
            "win_rate_pct": win_rate,
            "total_fees": total_fees,
            "trade_history": self.ib_mock.trades,
            "equity_curve": history_df
        }
