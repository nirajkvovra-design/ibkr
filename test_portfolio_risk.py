#!/usr/bin/env python
"""
Unit tests for the Portfolio Risk Engine and Risk Manager Integration.
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from portfolio_risk_engine import PortfolioRiskEngine, StressTestResult, PortfolioRiskReport
from risk_manager import RiskManager


class DummyIBConnection:
    """Mock connection to bypass live TWS."""
    def __init__(self, account_value=100000.0, cash=80000.0):
        self.account_value = account_value
        self.cash = cash

    def get_account_value(self) -> float:
        return self.account_value

    def get_cash(self) -> float:
        return self.cash


class TestPortfolioRiskEngine(unittest.TestCase):

    def setUp(self):
        # Create a mock DataFetcher
        self.mock_fetcher = MagicMock()
        self.engine = PortfolioRiskEngine(data_fetcher=self.mock_fetcher)

        # Set up mock stock returns
        # AAPL with 20% annualized volatility, SPY as index
        dates = pd.date_range(start="2026-01-01", periods=60, freq="D")
        np.random.seed(42)
        
        # SPY daily returns
        spy_ret = np.random.normal(0.0002, 0.010, 60)
        # AAPL daily returns (correlated with SPY)
        aapl_ret = 1.2 * spy_ret + np.random.normal(0.0, 0.008, 60)
        # MSFT daily returns
        msft_ret = 0.9 * spy_ret + np.random.normal(0.0, 0.007, 60)

        self.spy_data = pd.DataFrame({"Close": np.cumprod(1.0 + spy_ret) * 400.0}, index=dates)
        self.aapl_data = pd.DataFrame({"Close": np.cumprod(1.0 + aapl_ret) * 150.0}, index=dates)
        self.msft_data = pd.DataFrame({"Close": np.cumprod(1.0 + msft_ret) * 250.0}, index=dates)

        # Mock the data fetcher get_stock_data calls
        def mock_get_stock_data(symbol, *args, **kwargs):
            if symbol == "SPY":
                return self.spy_data
            elif symbol == "AAPL":
                return self.aapl_data
            elif symbol == "MSFT":
                return self.msft_data
            return None

        self.mock_fetcher.get_stock_data.side_effect = mock_get_stock_data

    def test_parsed_positions_risk_computation(self):
        # 1. Arrange a mock portfolio
        # Total equity = $100,000, with $10,000 AAPL and $10,000 MSFT (rest CASH)
        open_positions = {
            "AAPL": {"quantity": 66.67, "avg_cost": 150.0, "current_value": 10000.0},
            "MSFT": {"quantity": 40.0, "avg_cost": 250.0, "current_value": 10000.0}
        }
        account_value = 100000.0

        # 2. Act
        report = self.engine.calculate_portfolio_risk_metrics(open_positions, account_value)

        # 3. Assertions
        self.assertIsNotNone(report)
        self.assertEqual(report.portfolio_value, account_value)
        self.assertEqual(report.cash, 80000.0) # $100k - $20k allocated

        # Check weights
        self.assertIn("AAPL", report.concentration)
        self.assertIn("MSFT", report.concentration)
        self.assertEqual(report.concentration["AAPL"], 10.0)
        self.assertEqual(report.concentration["MSFT"], 10.0)
        self.assertEqual(report.concentration["CASH"], 80.0)

        # Check VaR and Expected Shortfall are calculated and positive
        self.assertTrue(report.parametric_var_95 > 0.0)
        self.assertTrue(report.parametric_var_99 > 0.0)
        self.assertTrue(report.parametric_var_99 > report.parametric_var_95)
        self.assertTrue(report.expected_shortfall_95 > report.parametric_var_95)
        self.assertTrue(report.expected_shortfall_99 > report.expected_shortfall_95)

        # Check dynamic beta calculation (both assets around 1.0 -> portfolio beta around 0.21 since weights are 10% each)
        self.assertTrue(0.1 < report.portfolio_beta < 0.3)

        # Check stress test results are generated
        self.assertEqual(len(report.stress_test_results), 5)
        scenarios = [r.scenario_name for r in report.stress_test_results]
        self.assertIn("Black Monday", scenarios)
        self.assertIn("2008 Financial Crisis", scenarios)
        self.assertIn("Tech Sector Rout", scenarios)

    def test_concentration_limit_alerts(self):
        # AAPL concentration represents 40% of the portfolio (exceeds 20% limit)
        open_positions = {
            "AAPL": {"quantity": 266.67, "avg_cost": 150.0, "current_value": 40000.0}
        }
        account_value = 100000.0

        report = self.engine.calculate_portfolio_risk_metrics(open_positions, account_value)
        self.assertEqual(len(report.concentration_alerts), 1)
        self.assertIn("AAPL", report.concentration_alerts[0])

    def test_risk_manager_integration(self):
        # Test dynamic sizing multiplier and VaR block inside RiskManager
        conn = DummyIBConnection(account_value=100000.0, cash=90000.0)
        rm = RiskManager(conn)
        
        # Override the mocked portfolio risk engine in the risk manager
        rm.portfolio_risk_engine = self.engine

        # Let's mock evaluate_portfolio_risk to return high volatility (30% annualized)
        mock_report = PortfolioRiskReport(
            portfolio_value=100000.0,
            parametric_var_95=2000.0,  # 2% of equity (within 5% limit)
            portfolio_volatility=30.0  # Spikes above 25% limit
        )
        rm.evaluate_portfolio_risk = MagicMock(return_value=mock_report)

        # Force DYNAMIC_RISK_SCALING to True
        with patch('config.DYNAMIC_RISK_SCALING', True), \
             patch('config.MAX_PORTFOLIO_POSITION_PERCENT', 0.05):
            
            # 1. Sizing should be scaled down by 50% due to volatility trigger
            # Starter / dynamic max limit: $100,000 * 5% = $5,000 max size.
            # Volatility cuts this to $2,500.
            # Trade value = $3,000 should exceed limits!
            allowed = rm.is_within_limits("AAPL", 20, 150.0)  # Value = $3,000
            self.assertFalse(allowed)

            # Trade value = $1,500 should be allowed
            allowed_small = rm.is_within_limits("AAPL", 10, 150.0)
            self.assertTrue(allowed_small)

        # Let's mock evaluate_portfolio_risk to return extreme VaR
        mock_high_var_report = PortfolioRiskReport(
            portfolio_value=100000.0,
            parametric_var_95=6000.0,  # 6% of equity (exceeds 5% limit)
            portfolio_volatility=15.0
        )
        rm.evaluate_portfolio_risk = MagicMock(return_value=mock_high_var_report)

        # 2. Trade should be completely blocked due to VaR limit breach
        allowed_blocked = rm.is_within_limits("AAPL", 10, 150.0)
        self.assertFalse(allowed_blocked)


if __name__ == "__main__":
    unittest.main()
