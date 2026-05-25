"""
Unit and integration tests for the FIFO tax lot manager and RiskManager tax safety gates.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from risk_manager import RiskManager
from tax_manager import TaxLot, TaxManager


class DummyIBConnection:
    """Mock connection to bypass TWS API calls."""

    def __init__(self, account_value=10000.0, cash=9000.0):
        self.account_value = account_value
        self.cash = cash

    def get_account_value(self) -> float:
        return self.account_value

    def get_cash(self) -> float:
        return self.cash


class TestTaxIntegration(unittest.TestCase):

    def setUp(self):
        # Use a temporary file for testing tax lots
        self.test_lots_file = Path("test_tax_lots.json")
        if self.test_lots_file.exists():
            self.test_lots_file.unlink()

        # Patch config.TAX_LOTS_FILE
        self.config_patcher = patch("config.TAX_LOTS_FILE", str(self.test_lots_file))
        self.config_patcher.start()

        self.tax_manager = TaxManager()

    def tearDown(self):
        self.config_patcher.stop()
        if self.test_lots_file.exists():
            self.test_lots_file.unlink()

    def test_add_buy_lots(self):
        """Test adding buy lots is recorded and persisted correctly."""
        self.tax_manager.add_buy_lot("AAPL", 10.0, 150.0, order_id=101)
        self.tax_manager.add_buy_lot("AAPL", 5.0, 155.0, order_id=102)

        lots = self.tax_manager.active_lots["AAPL"]
        self.assertEqual(len(lots), 2)
        self.assertEqual(lots[0].quantity, 10.0)
        self.assertEqual(lots[0].price, 150.0)
        self.assertEqual(lots[0].order_id, 101)

        self.assertEqual(lots[1].quantity, 5.0)
        self.assertEqual(lots[1].price, 155.0)
        self.assertEqual(lots[1].order_id, 102)

        # Verify persistence by instantiating a new TaxManager
        new_manager = TaxManager()
        self.assertIn("AAPL", new_manager.active_lots)
        self.assertEqual(len(new_manager.active_lots["AAPL"]), 2)

    def test_holding_period_determination(self):
        """Test that holding periods are correctly evaluated as short-term vs long-term."""
        now = datetime.now(timezone.utc)
        one_year_ago = (now - timedelta(days=366)).isoformat()
        six_months_ago = (now - timedelta(days=180)).isoformat()
        now_str = now.isoformat()

        # Long term evaluation (> 365 days)
        lt_period = self.tax_manager._determine_holding_period(one_year_ago, now_str)
        self.assertEqual(lt_period, "LONG_TERM")

        # Short term evaluation (<= 365 days)
        st_period = self.tax_manager._determine_holding_period(six_months_ago, now_str)
        self.assertEqual(st_period, "SHORT_TERM")

    def test_fifo_tax_implication_estimation(self):
        """Test FIFO matching logic and capital gains tax estimation."""
        now = datetime.now(timezone.utc)
        one_year_ago = (now - timedelta(days=370)).isoformat()
        six_months_ago = (now - timedelta(days=180)).isoformat()

        # Add two entries: 10 shares of AAPL long-term at $100, 20 shares short-term at $150
        self.tax_manager.add_buy_lot("AAPL", 10.0, 100.0, timestamp=one_year_ago, order_id=1)
        self.tax_manager.add_buy_lot("AAPL", 20.0, 150.0, timestamp=six_months_ago, order_id=2)

        # Estimate selling 15 shares at $200
        # FIFO expects: 
        # - 10 shares matched from Lot 1 (LTCG: 10 * ($200 - $100) = $1,000)
        # - 5 shares matched from Lot 2 (STCG: 5 * ($200 - $150) = $250)
        # P&L = $1,250
        # Estimated tax = ($1,000 * 15%) + ($250 * 30%) = $150 + $75 = $225
        implication = self.tax_manager.estimate_tax_implication("AAPL", 15.0, 200.0)

        self.assertEqual(implication["symbol"], "AAPL")
        self.assertEqual(implication["quantity_matched"], 15.0)
        self.assertEqual(implication["unmatched_quantity"], 0.0)
        self.assertEqual(implication["realized_pnl"], 1250.0)
        self.assertEqual(implication["long_term_gain_loss"], 1000.0)
        self.assertEqual(implication["short_term_gain_loss"], 250.0)
        self.assertEqual(implication["estimated_tax"], 225.0)
        self.assertEqual(len(implication["tax_lots_matched"]), 2)

        # Verify active lots were NOT modified during estimation
        self.assertEqual(len(self.tax_manager.active_lots["AAPL"]), 2)
        self.assertEqual(self.tax_manager.active_lots["AAPL"][0].quantity, 10.0)
        self.assertEqual(self.tax_manager.active_lots["AAPL"][1].quantity, 20.0)

    def test_fifo_sell_matching(self):
        """Test physical FIFO sell processing updating lot queues."""
        now = datetime.now(timezone.utc)
        one_year_ago = (now - timedelta(days=370)).isoformat()
        six_months_ago = (now - timedelta(days=180)).isoformat()

        self.tax_manager.add_buy_lot("AAPL", 10.0, 100.0, timestamp=one_year_ago, order_id=1)
        self.tax_manager.add_buy_lot("AAPL", 20.0, 150.0, timestamp=six_months_ago, order_id=2)

        # Process an actual sell execution of 15 shares at $200
        result = self.tax_manager.process_sell("AAPL", 15.0, 200.0, order_id=999)

        self.assertEqual(result["quantity_matched"], 15.0)
        self.assertEqual(result["realized_pnl"], 1250.0)

        # Verify active lots WERE updated:
        # Lot 1 (10 shares) should be fully matched and removed.
        # Lot 2 should have 15 shares remaining (20 - 5).
        active_lots = self.tax_manager.active_lots["AAPL"]
        self.assertEqual(len(active_lots), 1)
        self.assertEqual(active_lots[0].quantity, 15.0)
        self.assertEqual(active_lots[0].price, 150.0)

        # Check realized trade record in history
        self.assertEqual(len(self.tax_manager.realized_trades), 1)
        self.assertEqual(self.tax_manager.realized_trades[0]["symbol"], "AAPL")
        self.assertEqual(self.tax_manager.realized_trades[0]["realized_pnl"], 1250.0)
        self.assertEqual(self.tax_manager.realized_trades[0]["order_id"], 999)

    def test_risk_manager_pre_sell_tax_assessment(self):
        """Test RiskManager integrates and triggers warning alerts for high tax events."""
        conn = DummyIBConnection()
        rm = RiskManager(conn)
        rm.tax_manager = self.tax_manager

        # Add a lot: 100 shares of NVDA at $10
        self.tax_manager.add_buy_lot("NVDA", 100.0, 10.0)

        # Estimate selling at $100 (gain = 100 * ($100 - $10) = $9,000 short-term)
        # Tax = $9,000 * 30% = $2,700
        # Triggering a warning if threshold is $100
        with patch("config.TAX_IMPLICATION_WARNING_THRESHOLD", 100.0), \
             patch("config.ENABLE_TAX_SAFETY_GATES", False):
            
            implication = rm.evaluate_tax_implication("NVDA", 100.0, 100.0)
            self.assertEqual(implication["estimated_tax"], 2700.0)
            
            # Since safety gates is False, check_tax_safety_gate should warn but allow
            allowed = rm.check_tax_safety_gate("NVDA", 100.0, 100.0)
            self.assertTrue(allowed)

        # Test safety gates when enabled
        with patch("config.TAX_IMPLICATION_WARNING_THRESHOLD", 100.0), \
             patch("config.ENABLE_TAX_SAFETY_GATES", True):
            
            # Should be blocked
            allowed = rm.check_tax_safety_gate("NVDA", 100.0, 100.0)
            self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
