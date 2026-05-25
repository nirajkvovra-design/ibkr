"""Reusable dry-run script for the IBKR trading engine using mocked inputs.

This script exercises the engine flow without a live Interactive Brokers connection.
It initializes the engine, runs market research, executes a mock trading loop,
simulates end-of-day position closing, and stops cleanly.

Usage:
    python dry_run_mock.py
"""

from trading_engine import TradingEngine
from trade_research import TradeResearch
import daily_positions
import trading_engine as te
import utils
from core.models import OrderRequest, OrderSide, OrderType


class MockIBConnection:
    def __init__(self):
        self.connected = False
        self.positions = {
            'AAPL': {'quantity': 5, 'avg_cost': 150.0},
            'MSFT': {'quantity': 0, 'avg_cost': 0.0},
        }
        self.order_log = []

    def connect(self, retry=True):
        self.connected = True
        print('MockIBConnection: connect()')
        return True

    def refresh_account_data(self):
        print('MockIBConnection: refresh_account_data()')

    def get_positions(self):
        print('MockIBConnection: get_positions()')
        return {symbol: data for symbol, data in self.positions.items() if data['quantity'] != 0}

    def get_account_snapshot(self):
        print('MockIBConnection: get_account_snapshot()')
        return {
            'net_liquidation': 100000.0,
            'total_cash': 100000.0,
            'available_funds': 100000.0,
            'buying_power': 100000.0,
            'settled_cash': 100000.0,
            'funds_for_new_buys': 100000.0,
        }

    def cancel_stale_orders(self):
        print('MockIBConnection: cancel_stale_orders()')

    def cancel_order(self, order_id):
        print(f'MockIBConnection: cancel_order({order_id})')

    def get_order_status(self, order_id):
        return {'status': 'Cancelled', 'remaining': 0}

    def wait_for_order_filled(self, order_id, timeout=None):
        print(f'MockIBConnection: wait_for_order_filled({order_id})')
        return False

    def has_pending_orders(self):
        return False

    def has_active_order(self, symbol, action=None):
        return False

    def place_order(self, symbol, action, quantity, order_type='LMT', limit_price=None, metadata=None):
        print(f"MockIBConnection: place_order({action}, {quantity}, {symbol}, {order_type}, {limit_price})")
        self.order_log.append((symbol, action, quantity, order_type, limit_price, metadata))
        if action == 'SELL' and symbol in self.positions:
            self.positions[symbol]['quantity'] = 0
        if action == 'BUY':
            self.positions[symbol] = {'quantity': quantity, 'avg_cost': limit_price or 0.0}
        return 1001

    def get_cash(self):
        return 100000.0

    def get_available_funds_for_buys(self):
        return 100000.0

    def get_account_value(self):
        return 100000.0

    def disconnect(self):
        self.connected = False
        print('MockIBConnection: disconnect()')


class MockOrderManager:
    """Simple adapter to emulate OrderManager behavior for dry-run tests."""
    def __init__(self, ib_connection):
        self.ib = ib_connection

    def submit_order_with_confirmation(self, request: OrderRequest):
        # Convert OrderRequest into legacy ib_connection call for the mock
        action = request.action.value if hasattr(request.action, 'value') else str(request.action)
        order_type = request.order_type.value if hasattr(request.order_type, 'value') else str(request.order_type)
        limit_price = float(request.limit_price) if request.limit_price is not None else None
        return self.ib.place_order(request.symbol, action, int(request.quantity), order_type=order_type, limit_price=limit_price, metadata=request.metadata)

    def submit_order(self, request: OrderRequest):
        return self.submit_order_with_confirmation(request)


class MockDataFetcher:
    def get_current_price(self, symbol):
        prices = {'AAPL': 145.0, 'MSFT': 305.0}
        price = prices.get(symbol, 100.0)
        print(f'MockDataFetcher: get_current_price({symbol}) -> {price}')
        return price

    def get_limit_price(self, symbol, side):
        current = self.get_current_price(symbol)
        limit = current * (0.995 if side == 'SELL' else 1.005)
        limit = round(limit, 2)
        print(f'MockDataFetcher: get_limit_price({symbol}, {side}) -> {limit}')
        return limit

    def is_trade_free_us_stock_candidate(self, symbol):
        return True

    def get_calendar_risk(self, symbol):
        return {'blocked': False, 'reason': ''}


class MockStrategy:
    def __init__(self, ib_connection, risk_manager=None, order_manager=None):
        self.ib_connection = ib_connection
        self.risk_manager = risk_manager
        self.order_manager = order_manager
        self.daily_trades = 0
        self.daily_profit_loss = 0

    def reset_daily_stats(self):
        self.daily_trades = 0
        self.daily_profit_loss = 0

    def get_trading_blockers(self):
        return []

    def generate_signals(self, symbols):
        print('MockStrategy: generate_signals', symbols)
        return {'AAPL': 'SELL', 'MSFT': 'BUY'}

    def execute_trades(self, signals):
        print('MockStrategy: execute_trades', signals)
        for symbol, action in signals.items():
            if action == 'SELL':
                qty = self.ib_connection.get_positions().get(symbol, {}).get('quantity', 0)
                if qty > 0:
                    if getattr(self, 'order_manager', None):
                        req = OrderRequest(symbol=symbol, action=OrderSide.SELL, quantity=int(qty), order_type=OrderType.LMT, limit_price=145.0)
                        self.order_manager.submit_order_with_confirmation(req)
                    else:
                        self.ib_connection.place_order(symbol, 'SELL', qty, order_type='LMT', limit_price=145.0)
                    self.daily_trades += 1
            elif action == 'BUY':
                if getattr(self, 'order_manager', None):
                    req = OrderRequest(symbol=symbol, action=OrderSide.BUY, quantity=1, order_type=OrderType.LMT, limit_price=305.0)
                    self.order_manager.submit_order_with_confirmation(req)
                else:
                    self.ib_connection.place_order(symbol, 'BUY', 1, order_type='LMT', limit_price=305.0)
                self.daily_trades += 1


class MockStockScreener:
    def get_watchlist(self, method):
        print(f'MockStockScreener: get_watchlist({method})')
        return ['AAPL', 'MSFT']


class MockRiskManager:
    def __init__(self):
        self.open_positions = {}
        self.stop_loss_prices = {}
        self.take_profit_prices = {}

    def update_daily_pnl(self, pnl):
        print(f'MockRiskManager: update_daily_pnl({pnl})')

    def reset_daily_stats(self):
        print('MockRiskManager: reset_daily_stats()')

    def check_stop_loss(self, symbol, price):
        return False

    def check_take_profit(self, symbol, price):
        return False

    def remove_position(self, symbol):
        self.open_positions.pop(symbol, None)
        print(f'MockRiskManager: remove_position({symbol})')

    def set_stop_loss(self, symbol, entry_price, stop_loss_percent):
        self.stop_loss_prices[symbol] = entry_price * (1 - stop_loss_percent / 100)

    def set_take_profit(self, symbol, entry_price, take_profit_percent):
        self.take_profit_prices[symbol] = entry_price * (1 + take_profit_percent / 100)

    def add_position(self, symbol, quantity, entry_price):
        self.open_positions[symbol] = {
            'quantity': quantity,
            'entry_price': entry_price,
            'current_value': quantity * entry_price,
        }
        print(f'MockRiskManager: add_position({symbol}, {quantity}, {entry_price})')

    def get_position_info(self):
        return {'num_positions': len(self.open_positions), 'drawdown_percent': 0.0}

    def is_trading_allowed(self):
        return True


def run_dry_run():
    print('\n=== BEGIN IBKR MOCK DRY RUN ===\n')

    if hasattr(daily_positions, 'clear_all'):
        daily_positions.clear_all()

    # Build engine and substitute mocked components.
    te.MomentumStrategy = MockStrategy
    te.PairsTradingStrategy = MockStrategy
    te.VolatilityBreakoutStrategy = MockStrategy
    te.IPOBreakoutStrategy = MockStrategy
    te.MachineLearningStrategy = MockStrategy
    te.GridTradingStrategy = MockStrategy

    engine = TradingEngine()
    engine.ib_connection = MockIBConnection()
    engine.order_manager = MockOrderManager(engine.ib_connection)
    engine.data_fetcher = MockDataFetcher()
    engine.risk_manager = MockRiskManager()
    engine.strategy = MockStrategy(engine.ib_connection, engine.risk_manager)
    engine.strategy.order_manager = engine.order_manager
    engine.stock_screener = MockStockScreener()
    engine.research = TradeResearch(engine.data_fetcher)

    # Allow the engine and research modules to pretend the market is open during dry run.
    te.is_market_open = lambda: True
    import trade_research as tr
    tr.is_market_open = lambda: True

    print('Initializing engine...')
    initialized = engine.initialize()
    print('initialize() ->', initialized)

    print('\nRunning market research...')
    report = engine._run_market_research()
    print('Market research report keys:', list(report.keys()))

    print('\nRunning trading loop...')
    engine.running = True
    engine._trading_loop()
    print('Order log after trading loop:', engine.ib_connection.order_log)

    print('\nRecording a mock today-open position for EOD close...')
    daily_positions.record_open('MSFT', 1, 305.0, order_id=1001)
    engine._eod_close_done = False

    print('\nExecuting end-of-day close...')
    engine._close_todays_positions()
    print('Order log after EOD close:', engine.ib_connection.order_log)

    print('\nExecuting end-of-day summary...')
    engine._end_of_day()
    print('Final engine status:', engine.get_status())

    print('\nStopping engine...')
    engine.stop()
    print('\n=== END IBKR MOCK DRY RUN ===\n')


if __name__ == '__main__':
    run_dry_run()
