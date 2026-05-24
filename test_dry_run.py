import unittest
from unittest.mock import patch

import daily_positions
import trading_engine
from trading_engine import TradingEngine
from trade_research import TradeResearch


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
        return True

    def refresh_account_data(self):
        pass

    def get_positions(self):
        return {symbol: data for symbol, data in self.positions.items() if data['quantity'] != 0}

    def get_account_snapshot(self):
        return {
            'net_liquidation': 100000.0,
            'total_cash': 100000.0,
            'available_funds': 100000.0,
            'buying_power': 100000.0,
            'settled_cash': 100000.0,
            'funds_for_new_buys': 100000.0,
        }

    def cancel_stale_orders(self):
        pass

    def cancel_order(self, order_id):
        pass

    def get_order_status(self, order_id):
        return {'status': 'Cancelled', 'remaining': 0}

    def wait_for_order_filled(self, order_id, timeout=None):
        return False

    def has_pending_orders(self):
        return False

    def has_active_order(self, symbol, action=None):
        return False

    def place_order(self, symbol, action, quantity, order_type='LMT', limit_price=None, metadata=None):
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


class MockDataFetcher:
    def get_current_price(self, symbol):
        prices = {'AAPL': 145.0, 'MSFT': 305.0}
        return prices.get(symbol, 100.0)

    def get_limit_price(self, symbol, side):
        current = self.get_current_price(symbol)
        return round(current * (0.995 if side == 'SELL' else 1.005), 2)

    def is_trade_free_us_stock_candidate(self, symbol):
        return True

    def get_calendar_risk(self, symbol):
        return {'blocked': False, 'reason': ''}


class MockRiskManager:
    def __init__(self):
        self.open_positions = {}
        self.stop_loss_prices = {}
        self.take_profit_prices = {}

    def update_daily_pnl(self, pnl):
        self.daily_loss = pnl

    def reset_daily_stats(self):
        self.daily_loss = 0

    def check_stop_loss(self, symbol, price):
        return False

    def check_take_profit(self, symbol, price):
        return False

    def remove_position(self, symbol):
        self.open_positions.pop(symbol, None)

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

    def get_position_info(self):
        return {'num_positions': len(self.open_positions), 'drawdown_percent': 0.0}

    def is_trading_allowed(self):
        return True


class MockStrategy:
    def __init__(self, ib_connection, risk_manager=None):
        self.ib_connection = ib_connection
        self.risk_manager = risk_manager
        self.daily_trades = 0
        self.daily_profit_loss = 0

    def reset_daily_stats(self):
        self.daily_trades = 0
        self.daily_profit_loss = 0

    def get_trading_blockers(self):
        return []

    def generate_signals(self, symbols):
        return {'AAPL': 'SELL', 'MSFT': 'BUY'}

    def execute_trades(self, signals):
        for symbol, action in signals.items():
            if action == 'SELL':
                qty = self.ib_connection.get_positions().get(symbol, {}).get('quantity', 0)
                if qty > 0:
                    self.ib_connection.place_order(symbol, 'SELL', qty, order_type='LMT', limit_price=145.0)
                    self.daily_trades += 1
            elif action == 'BUY':
                self.ib_connection.place_order(symbol, 'BUY', 1, order_type='LMT', limit_price=305.0)
                self.daily_trades += 1


class MockStockScreener:
    def get_watchlist(self, method):
        return ['AAPL', 'MSFT']


class TradingEngineDryRunTest(unittest.TestCase):
    def setUp(self):
        if hasattr(daily_positions, 'clear_all'):
            daily_positions.clear_all()

        trading_engine.MomentumStrategy = MockStrategy
        trading_engine.PairsTradingStrategy = MockStrategy
        trading_engine.VolatilityBreakoutStrategy = MockStrategy
        trading_engine.IPOBreakoutStrategy = MockStrategy
        trading_engine.MachineLearningStrategy = MockStrategy
        trading_engine.GridTradingStrategy = MockStrategy

        self.engine = TradingEngine()
        self.engine.ib_connection = MockIBConnection()
        self.engine.data_fetcher = MockDataFetcher()
        self.engine.risk_manager = MockRiskManager()
        self.engine.stock_screener = MockStockScreener()
        self.engine.research = TradeResearch(self.engine.data_fetcher)
        self.engine._eod_close_done = False

    @patch('trading_engine.is_market_open', lambda: True)
    @patch('trade_research.is_market_open', lambda: True)
    def test_dry_run_flow(self):
        self.assertTrue(self.engine.initialize(), 'Engine failed to initialize')

        report = self.engine._run_market_research()
        self.assertTrue(report['can_execute_trades'])
        self.assertIn('AAPL', report['watchlist'])
        self.assertEqual(report['recommended_opens'], ['MSFT'])
        self.assertEqual(report['recommended_closes'], ['AAPL'])

        self.engine.running = True
        self.engine._trading_loop()
        self.assertGreaterEqual(len(self.engine.ib_connection.order_log), 1)
        self.assertEqual(self.engine.ib_connection.order_log[0][1], 'SELL')

        daily_positions.record_open('MSFT', 1, 305.0, order_id=1001)
        self.engine._eod_close_done = False
        self.engine._close_todays_positions()
        self.assertTrue(any(order[0] == 'MSFT' and order[1] == 'SELL' for order in self.engine.ib_connection.order_log))

        self.engine._end_of_day()
        self.engine.stop()
        status = self.engine.get_status()
        self.assertFalse(status['running'])
        self.assertEqual(status['positions'], 0)


if __name__ == '__main__':
    unittest.main()
