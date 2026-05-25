"""
Verification and Integration Suite for Institutional Engine Core.
Tests:
1. EventEngine async queue dispatching and listener callbacks.
2. MetricsCollector execution latency, slippage, and PnL metrics.
3. RiskManager Kill Switch locks.
4. RiskManager symbol Cooldown blocks.
5. RiskManager emergency Flatten-All liquidation order routing.
"""

import asyncio
import json
import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from core.event_engine import EventEngine, Event, EVENT_TICK, EVENT_SIGNAL
from core.metrics_collector import MetricsCollector
from risk_manager import RiskManager


class DummyIBConnection:
    """Mock connection to bypass live TWS."""

    def __init__(self, account_value=100000.0, cash=90000.0):
        self.account_value = account_value
        self.cash = cash
        self.positions = {}

    def get_account_value(self) -> float:
        return self.account_value

    def get_cash(self) -> float:
        return self.cash

    def get_positions(self):
        return self.positions

    def refresh_account_data(self) -> None:
        pass

    def cancel_order(self, oid) -> None:
        pass

    def place_order(self, req) -> None:
        pass


class TestInstitutionalCore(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_metrics_file = Path("test_metrics.json")
        if self.test_metrics_file.exists():
            self.test_metrics_file.unlink()

        self.conn = DummyIBConnection()
        self.risk = RiskManager(self.conn)
        self.metrics = MetricsCollector(metrics_file=str(self.test_metrics_file))
        self.risk.metrics_collector = self.metrics

    def tearDown(self):
        if self.test_metrics_file.exists():
            self.test_metrics_file.unlink()

    async def test_event_engine_async_dispatch(self):
        """Test EventEngine asynchronous queue processing and listener callbacks."""
        engine = EventEngine()
        engine.start()

        event_received_sync = False
        event_received_async = False
        received_data = None

        def sync_handler(event: Event):
            nonlocal event_received_sync, received_data
            event_received_sync = True
            received_data = event.data

        async def async_handler(event: Event):
            nonlocal event_received_async
            await asyncio.sleep(0.01)  # Simulate short async task
            event_received_async = True

        # Register callbacks
        engine.register_listener(EVENT_TICK, sync_handler)
        engine.register_listener(EVENT_TICK, async_handler)

        # Dispatch TICK event
        engine.put(Event(EVENT_TICK, data={"price": 150.0}))

        # Wait briefly for async loop processing
        await asyncio.sleep(0.05)

        self.assertTrue(event_received_sync, "Synchronous event handler failed to trigger.")
        self.assertTrue(event_received_async, "Asynchronous event handler failed to trigger.")
        self.assertEqual(received_data, {"price": 150.0}, "Event data payload is corrupted.")

        # Stop engine
        await engine.stop()

    def test_metrics_telemetry_and_persistence(self):
        """Test MetricsCollector calculates exact execution latency and price slippage."""
        # 1. Record order submission
        self.metrics.record_order_submitted(order_id=5001)

        # Simulate brief latency delay (e.g. 10ms)
        time.sleep(0.01)

        # 2. Record order fill (BUY 100 shares @ $150.50, Target: $150.00 -> $0.50 positive slippage)
        self.metrics.record_order_filled(
            order_id=5001,
            symbol="AAPL",
            action="BUY",
            quantity=100.0,
            fill_price=150.50,
            target_price=150.00,
        )

        # Assert metrics calculated
        self.assertEqual(len(self.metrics.latencies), 1)
        self.assertTrue(self.metrics.latencies[0] >= 10.0, "Execution latency calculation is too low.")

        self.assertEqual(len(self.metrics.slippages), 1)
        self.assertAlmostEqual(self.metrics.slippages[0], 0.50, places=2, msg="Execution slippage calculation is incorrect.")
        self.assertAlmostEqual(self.metrics.slippages_pct[0], (0.50 / 150.00) * 100, places=2)

        # Verify JSON file persistence
        self.assertTrue(self.test_metrics_file.exists(), "Metrics file was not created on disk.")
        content = self.test_metrics_file.read_text(encoding="utf-8")
        data = json.loads(content)
        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total_trades_counted"], 1)
        self.assertAlmostEqual(data["summary"]["avg_slippage_usd"], 0.50, places=2)

    def test_global_kill_switch(self):
        """Test global Kill Switch immediately blocks new signal executions in RiskManager."""
        self.assertFalse(self.risk.kill_switch_active)

        # Verify normal trade checks are allowed initially
        allowed = self.risk.is_within_limits("MSFT", 10.0, 200.0)
        self.assertTrue(allowed)

        # Activate Kill Switch
        self.risk.activate_kill_switch()
        self.assertTrue(self.risk.kill_switch_active)

        # Verify all subsequent trades are blocked
        blocked = self.risk.is_within_limits("MSFT", 10.0, 200.0)
        self.assertFalse(blocked, "Kill Switch failed to block trade execution.")

        # Deactivate and restore
        self.risk.deactivate_kill_switch()
        self.assertFalse(self.risk.kill_switch_active)
        allowed_again = self.risk.is_within_limits("MSFT", 10.0, 200.0)
        self.assertTrue(allowed_again)

    def test_symbol_cooldown_lockout(self):
        """Test symbol trade cooldown locks restrict tickers for specified lockout durations."""
        symbol = "NVDA"
        self.assertFalse(self.risk.is_in_cooldown(symbol))

        # Trigger a 1-second cooldown lock
        self.risk.trigger_cooldown(symbol, duration_seconds=1.0)
        self.assertTrue(self.risk.is_in_cooldown(symbol))

        # Verify trades are blocked
        blocked = self.risk.is_within_limits(symbol, 5.0, 100.0)
        self.assertFalse(blocked, "Cooldown lockout failed to block symbol trade.")

        # Wait for cooldown to expire (1.1s)
        time.sleep(1.1)

        # Verify locked symbol is unlocked
        self.assertFalse(self.risk.is_in_cooldown(symbol))
        allowed = self.risk.is_within_limits(symbol, 5.0, 100.0)
        self.assertTrue(allowed)

    def test_emergency_flatten_all(self):
        """Test Emergency Flatten-All cancels orders, liquidates positions, and engages the Kill Switch."""
        from core.models import Position

        # Seed active positions into mock connection
        self.conn.positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_cost=150.0),
            "TSLA": Position(symbol="TSLA", quantity=-10, avg_cost=200.0),  # short position
        }

        # Mock order manager with submitted orders list
        mock_oms = MagicMock()
        mock_oms.submitted_orders = {
            1001: {"request": MagicMock(symbol="AAPL")},
            1002: {"request": MagicMock(symbol="TSLA")},
        }

        # Patch place_order and cancel_order calls inside connections to verify behavior
        mock_place = MagicMock()
        self.conn.place_order = mock_place
        self.conn.cancel_order = MagicMock()

        # Trigger emergency flatten
        self.risk.flatten_all_positions(order_manager=mock_oms)

        # 1. Kill Switch must be engaged immediately
        self.assertTrue(self.risk.kill_switch_active)

        # 2. Cancel order calls should be made on all active orders
        self.assertTrue(self.conn.cancel_order.called)
        
        # 3. Two liquidation orders should be submitted (sell AAPL, buy TSLA) via OMS
        self.assertEqual(mock_oms.submit_order.call_count, 2)
        
        calls = [call[0][0] for call in mock_oms.submit_order.call_args_list]
        symbols = {c.symbol for c in calls}
        actions = {c.action for c in calls}
        quantities = {c.quantity for c in calls}

        self.assertIn("AAPL", symbols)
        self.assertIn("TSLA", symbols)
        
        # AAPL (long 50) -> should SELL 50
        # TSLA (short 10) -> should BUY 10
        self.assertIn("SELL", actions)
        self.assertIn("BUY", actions)
        self.assertIn(50, quantities)
        self.assertIn(10, quantities)


if __name__ == "__main__":
    import sys
    import json
    unittest.main()
