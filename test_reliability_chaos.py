"""
Institutional Verification & Chaos Testing Suite
Tests:
1. StateManager JSON serialization and rehydration.
2. SafetyGate progressive rollout filtering (Shadow, Micro, Limited, Full).
3. ChaosEngine round-trip latency and programmatic socket disconnects.
4. StressMockIBConnection slippage shocks and order rejections.
5. Monte Carlo bootstrap trade re-sampling and drawdown percentile calculations.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import MagicMock

from core.chaos_engine import ChaosEngine
from core.models import OrderRequest, OrderSide, OrderType
from core.safety_gate import SafetyGate, TradingStage
from core.state_manager import StateManager
from risk_manager import RiskManager
from backtest_stress import StressMockIBConnection, StressBacktestEngine


class TestReliabilityChaos(unittest.TestCase):

    def setUp(self):
        self.symbol = "AAPL"
        self.state_file = ".test_state_cache.json"
        self.state_manager = StateManager(self.state_file)

    def tearDown(self):
        # Cleanup temporary files
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        # Ensure chaos engine is reset
        ChaosEngine().configure(enabled=False)

    def test_state_manager_serialization_and_rehydration(self):
        """Verify StateManager correctly saves and rehydrates volatile risk limits across mock restarts."""
        mock_conn = MagicMock()
        mock_conn.get_account_value.return_value = 10000.0
        
        # Instantiate RiskManager and point to test state file
        rm1 = RiskManager(mock_conn)
        rm1.state_manager = self.state_manager
        
        # Hermetic test mock to bypass internet headline fetch
        rm1.macro_engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "LOW_VOL_TREND",
            "stress_score": 0.10,
            "geopolitical_multiplier": 1.0,
            "event_blackout": {"is_blocked": False}
        })
        
        # Modify active RAM state
        rm1.add_position(self.symbol, quantity=50, entry_price=150.00)
        rm1.set_stop_loss(self.symbol, entry_price=150.00, stop_loss_percent=2.0)
        rm1.set_take_profit(self.symbol, entry_price=150.00, take_profit_percent=5.0)
        rm1.update_daily_pnl(-250.00)
        
        # Ensure state file was written
        self.assertTrue(os.path.exists(self.state_file), "State cache file was not created on disk.")
        
        # Create a second RiskManager (simulating a system crash and restart)
        rm2 = MagicMock() # Create second RiskManager using standard class
        from risk_manager import RiskManager as ActualRiskManager
        rm2 = ActualRiskManager(mock_conn)
        rm2.state_manager = self.state_manager
        
        # Hermetic test mock to bypass internet headline fetch
        rm2.macro_engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "LOW_VOL_TREND",
            "stress_score": 0.10,
            "geopolitical_multiplier": 1.0,
            "event_blackout": {"is_blocked": False}
        })
        
        rm2.rehydrate_state()
        
        # Assert rehydrated fields match original values
        self.assertEqual(rm2.daily_loss, -250.00)
        self.assertIn(self.symbol, rm2.open_positions)
        self.assertEqual(rm2.open_positions[self.symbol]["quantity"], 50)
        self.assertEqual(rm2.stop_loss_prices[self.symbol], 147.00)  # 150 * 0.98
        self.assertEqual(rm2.take_profit_prices[self.symbol], 157.50)  # 150 * 1.05

    def test_safety_gate_staged_rollout_filtering(self):
        """Verify SafetyGate intercepts and scales orders correctly per staged rollout rules."""
        gate = SafetyGate(TradingStage.SHADOW)
        account_value = 10000.0
        
        req = OrderRequest(
            symbol=self.symbol,
            action=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LMT,
            limit_price=150.00
        )
        
        # 1. SHADOW Mode: should block order entirely (return None)
        filtered_shadow, msg_shadow = gate.filter_order(req, account_value)
        self.assertIsNone(filtered_shadow, "Shadow mode failed to block active order.")
        
        # 2. MICRO Mode: should truncate order to exactly 1 share
        gate.set_stage(TradingStage.MICRO)
        req_micro = OrderRequest(
            symbol=self.symbol,
            action=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LMT,
            limit_price=150.00
        )
        filtered_micro, msg_micro = gate.filter_order(req_micro, account_value)
        self.assertIsNotNone(filtered_micro)
        self.assertEqual(filtered_micro.quantity, 1, "Micro mode failed to truncate order to 1 share.")
        
        # 3. LIMITED Mode: should cap exposure to 5% of account value ($500.00 max)
        # $150 price * 100 qty = $15,000 exposure -> should truncate to 3 shares ($450 exposure)
        gate.set_stage(TradingStage.LIMITED)
        req_limited = OrderRequest(
            symbol=self.symbol,
            action=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LMT,
            limit_price=150.00
        )
        filtered_limited, msg_limited = gate.filter_order(req_limited, account_value)
        self.assertIsNotNone(filtered_limited)
        self.assertEqual(filtered_limited.quantity, 3, "Limited mode failed to enforce 5% portfolio exposure cap.")
        
        # 4. FULL Mode: should pass order through unchanged
        gate.set_stage(TradingStage.FULL)
        req_full = OrderRequest(
            symbol=self.symbol,
            action=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LMT,
            limit_price=150.00
        )
        filtered_full, msg_full = gate.filter_order(req_full, account_value)
        self.assertEqual(filtered_full.quantity, 100, "Full mode altered order quantity unexpectedly.")

    def test_chaos_engine_latency_and_disconnections(self):
        """Verify ChaosEngine hooks inject blocking delays and socket drops correctly."""
        chaos = ChaosEngine()
        chaos.configure(
            enabled=True,
            latency_injection=True,
            min_latency_ms=10,
            max_latency_ms=20,
            socket_drop_rate=1.0  # Force disconnect on place_order
        )
        
        from core.ib_broker import IBBrokerConnection
        
        # Mock IBBrokerConnection base methods
        conn = IBBrokerConnection()
        conn.connected = True
        conn.disconnect = MagicMock()
        
        req = OrderRequest(
            symbol=self.symbol,
            action=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LMT,
            limit_price=150.00
        )
        
        # Attempting place_order under 100% disconnect chaos should trigger disconnect and return None
        res = conn.place_order(req)
        self.assertIsNone(res)
        conn.disconnect.assert_called_once()

    def test_stress_mock_slippage_shocks_and_rejections(self):
        """Verify StressMockIBConnection triggers order rejections and volatility-slipped fills."""
        # Setup StressMock with 100% rejection rate
        mock_reject = StressMockIBConnection(starting_cash=10000.0, slippage_shock_pct=0.0, order_reject_rate=1.0)
        res_reject = mock_reject.place_order(self.symbol, "BUY", 10, "LMT", 150.00)
        self.assertIsNone(res_reject, "Stress mock failed to reject order at 100% reject rate.")
        
        # Setup StressMock with 100% slippage rate (average 5% slippage shock)
        mock_slip = StressMockIBConnection(starting_cash=10000.0, slippage_shock_pct=5.0, order_reject_rate=0.0)
        mock_slip.place_order(self.symbol, "BUY", 10, "LMT", 100.00)
        
        trades = mock_slip.trades
        self.assertEqual(len(trades), 1)
        # BUY price must be strictly greater than 100.00 due to positive slippage injection
        self.assertTrue(trades[0]["price"] > 100.00, "Stress mock failed to apply positive slippage shock on BUY.")

    def test_monte_carlo_resampling_tail_risk(self):
        """Verify Monte Carlo resampling correctly solves ruin probability and worst-case drawdowns."""
        engine = StressBacktestEngine(["AAPL"], "2020_COVID", starting_cash=10000.0)
        
        # Feed mock round-trip trades: some wins, some major losses
        mock_trades = [
            {"symbol": "AAPL", "side": "BUY", "quantity": 10, "price": 100.00, "fee": 1.00},
            {"symbol": "AAPL", "side": "SELL", "quantity": 10, "price": 150.00, "fee": 1.00}, # Win +$498
            {"symbol": "AAPL", "side": "BUY", "quantity": 20, "price": 200.00, "fee": 1.00},
            {"symbol": "AAPL", "side": "SELL", "quantity": 20, "price": 100.00, "fee": 1.00}, # Major Loss -$2002
        ]
        
        mc_results = engine.run_monte_carlo(mock_trades, iterations=100)
        self.assertIn("ruin_probability_pct", mc_results)
        self.assertIn("worst_case_drawdown_pct", mc_results)
        self.assertIn("drawdown_percentiles", mc_results)
        self.assertTrue(mc_results["worst_case_drawdown_pct"] < 0.0, "Monte Carlo failed to record negative drawdowns.")
        self.assertIn("95th", mc_results["drawdown_percentiles"])


if __name__ == "__main__":
    unittest.main()
