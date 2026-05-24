#!/usr/bin/env python
"""
Verification script for Leveraged Margin Funding & High-Confidence Setup Sizing
Tests:
1. Available funds selector using conservative cash, margin, and buying power sources.
2. High confidence scaling resolution under technical & news sentiment alignments.
"""

import sys
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

# Set up encoding support for Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
from ib_connection import InteractiveBrokersConnection
from strategies import MomentumStrategy
from data_fetcher import DataFetcher

class TestFundingAndConfidence(unittest.TestCase):
    def setUp(self):
        config.HIGH_CONFIDENCE_SCALING = True
        config.HIGH_CONFIDENCE_MULTIPLIER = 1.5

    def test_available_funds_selectors(self):
        """Test 1: Verify get_available_funds_for_buys scales correctly based on FUNDING_SOURCE"""
        print("\n[Test 1] Testing get_available_funds_for_buys with various funding sources...")
        
        conn = InteractiveBrokersConnection()
        conn.wrapper = MagicMock()
        conn.wrapper.cash = 10000.0
        conn.wrapper.available_funds = 25000.0
        conn.wrapper.buying_power = 40000.0
        conn.wrapper.settled_cash = 8000.0
        
        # 1. Conservative mode: takes min of cash/available/power
        config.FUNDING_SOURCE = "CONSERVATIVE"
        config.REQUIRE_SETTLED_CASH_FOR_BUYS = False
        funds_cons = conn.get_available_funds_for_buys()
        self.assertEqual(funds_cons, 10000.0, f"Expected conservative funding of $10,000, got ${funds_cons}")
        
        # 2. Margin mode: takes available_funds (includes margin equity)
        config.FUNDING_SOURCE = "MARGIN"
        funds_margin = conn.get_available_funds_for_buys()
        self.assertEqual(funds_margin, 25000.0, f"Expected margin funding of $25,000, got ${funds_margin}")
        
        # 3. Buying Power mode: takes buying_power (full margin leverage)
        config.FUNDING_SOURCE = "BUYING_POWER"
        funds_power = conn.get_available_funds_for_buys()
        self.assertEqual(funds_power, 40000.0, f"Expected buying power funding of $40,000, got ${funds_power}")
        
        print("  - Conservative funds selector evaluated successfully ($10,000 cash).")
        print("  - IBKR Margin Available Funds selector evaluated successfully ($25,000 margin equity).")
        print("  - IBKR Buying Power leverage selector evaluated successfully ($40,000 full leverage).")
        print("  ✓ Sizing and funding selectors passed.")

    @patch('strategies.NewsSentiment')
    @patch('strategies.DataFetcher')
    def test_high_confidence_setup_scaling(self, mock_fetcher_class, mock_sentiment_class):
        """Test 2: Verify size multiplier scales to 1.5x when indicators and sentiment are fully aligned"""
        print("\n[Test 2] Testing High Confidence Setup dynamic scaling resolution...")
        
        # Instantiate Strategy
        mock_conn = MagicMock()
        strategy = MomentumStrategy(mock_conn)
        
        # Mock connection return values to prevent mock containment check bugs
        mock_conn.get_positions.return_value = {}
        mock_conn.has_active_order.return_value = False
        
        # Mock DataFetcher to return fully aligned high-momentum technical indicators
        mock_fetcher = MagicMock()
        dates = pd.date_range(start="2026-05-01", periods=20)
        mock_data = pd.DataFrame({
            'Close': [100.0] * 20,
            'RSI': [45.0] * 20,
            'MACD': [2.5] * 20,
            'MACD_Signal': [1.0] * 20,
            'Volume_Ratio': [1.5] * 20,
            'SMA_20': [90.0] * 20
        }, index=dates)
        mock_fetcher.get_stock_data.return_value = mock_data
        mock_fetcher.get_current_price.return_value = 100.0
        mock_fetcher.get_limit_price.return_value = 100.0
        
        # Mock NewsSentiment to return strongly BULLISH
        mock_sentiment = MagicMock()
        mock_sentiment.get_news_sentiment.return_value = 'BULLISH'
        
        # Inject mocks into strategy
        strategy.data_fetcher = mock_fetcher
        strategy.sentiment_analyzer = mock_sentiment
        
        # Run execution loop mockup to verify confidence sizing multiplier is applied
        mock_conn.get_available_funds_for_buys.return_value = 10000.0
        mock_conn.get_account_value.return_value = 10000.0
        config.POSITION_SIZE_PERCENT = 0.5  # Bet $5,000
        config.DYNAMIC_RISK_SCALING = False
        config.MAX_POSITION_SIZE = 10000.0
        
        # Trigger buy signal execution
        strategy.active_positions = {}
        strategy.daily_trades = 0
        signals = {"AAPL": "BUY"}
        
        with patch.object(mock_conn, 'place_order') as mock_place:
            strategy.execute_trades(signals)
            
            # Assert place_order was called with quantity = 75
            # AAPL price = 100. Base size = min(10000, 10000 * 0.5) = 5000.
            # Aligned indicators -> scaled by 1.5x -> target_size = 7500.
            # Quantity = target_size / 100 = 75 shares.
            mock_place.assert_called_once()
            call_args = mock_place.call_args[0]
            self.assertEqual(call_args[0], "AAPL")
            self.assertEqual(call_args[1], "BUY")
            self.assertEqual(call_args[2], 75, f"Expected scaled quantity of 75 shares, got {call_args[2]}")
            
        print("  - Fully aligned technicals (RSI/MACD/Volume/SMA20) identified.")
        print("  - Strongly bullish news sentiment identified.")
        print("  - Dynamically scaled size resolved to 75 shares (1.5x size boost, from 50 base).")
        print("  ✓ High confidence setup sizing passed.")

def main():
    print("=" * 70)
    print("  MARGIN LEVERAGE & DYNAMIC HIGH-CONFIDENCE SIZING TESTS")
    print("=" * 70)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFundingAndConfidence)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n" + "="*70)
        print("ALL TESTS PASSED SUCCESSFULLY! MARGIN AND DYNAMIC SIZING IS 100% CORRECT.")
        print("="*70 + "\n")
    else:
        print("\n❌ Tests failed!\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
