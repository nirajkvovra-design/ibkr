#!/usr/bin/env python
"""
Unit tests for the Options Greeks and Probability of Profit Strategy Advisor.
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from options_strategy_advisor import recommend_options_strategy


class TestOptionsStrategyAdvisor(unittest.TestCase):

    def setUp(self):
        # Create mock call and put option chains
        # We need strike, bid, ask, lastPrice, impliedVolatility, openInterest, volume
        self.mock_calls = pd.DataFrame({
            "strike": [140.0, 145.0, 150.0, 155.0, 160.0],
            "bid": [11.20, 6.40, 3.10, 1.15, 0.35],
            "ask": [11.40, 6.60, 3.30, 1.25, 0.45],
            "lastPrice": [11.30, 6.50, 3.20, 1.20, 0.40],
            "impliedVolatility": [0.28, 0.26, 0.24, 0.23, 0.22],
            "openInterest": [100, 200, 500, 300, 150],
            "volume": [50, 120, 350, 180, 90]
        })

        self.mock_puts = pd.DataFrame({
            "strike": [140.0, 145.0, 150.0, 155.0, 160.0],
            "bid": [0.30, 1.10, 2.90, 6.10, 10.90],
            "ask": [0.40, 1.20, 3.10, 6.30, 11.10],
            "lastPrice": [0.35, 1.15, 3.00, 6.20, 11.00],
            "impliedVolatility": [0.27, 0.25, 0.24, 0.26, 0.29],
            "openInterest": [120, 250, 450, 200, 100],
            "volume": [60, 150, 400, 110, 40]
        })

    @patch('option_analyzer.fetch_option_data')
    @patch('option_analyzer.analyze_options')
    def test_strategy_advisor_output(self, mock_analyze, mock_fetch):
        # 1. Arrange Mocks
        mock_fetch.return_value = {
            'symbol': 'AAPL',
            'expiration_date': '2026-06-19',
            'all_expirations': ['2026-06-19'],
            'current_price': 150.0,
            'calls': self.mock_calls,
            'puts': self.mock_puts
        }

        mock_analyze.return_value = {
            'current_price': 150.0,
            'max_pain_strike': 150.0,
            'pcr_oi': 1.05,
            'call_wall': 160.0,
            'put_wall': 140.0,
            'expiration_date': '2026-06-19'
        }

        # 2. Act
        recs = recommend_options_strategy("AAPL", expiration_date="2026-06-19", max_collateral=500.0)

        # 3. Assert
        self.assertIsNotNone(recs)
        self.assertEqual(len(recs), 3)

        # Verify strategy 1 (Iron Butterfly) metrics
        butterfly = recs[0]
        self.assertEqual(butterfly["name"], "Short Iron Butterfly (Max Pain Neutral Pin)")
        self.assertIn("probability_of_profit", butterfly["metrics"])
        self.assertIn("net_short_theta", butterfly["metrics"])

        # Verify strategy 2 (Bull Put Spread) metrics
        bull_put = recs[1]
        self.assertEqual(bull_put["name"], "Bull Put Credit Spread (Bullish Income)")
        self.assertIn("short_leg_delta", bull_put["metrics"])
        self.assertIn("short_leg_theta", bull_put["metrics"])

        # Verify strategy 3 (Bear Call Spread) metrics
        bear_call = recs[2]
        self.assertEqual(bear_call["name"], "Bear Call Credit Spread (Bearish Income)")
        self.assertIn("short_leg_delta", bear_call["metrics"])
        self.assertIn("probability_of_profit", bear_call["metrics"])


if __name__ == "__main__":
    unittest.main()
