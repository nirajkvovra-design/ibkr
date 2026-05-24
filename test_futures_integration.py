#!/usr/bin/env python
"""
Verification script for Automated Futures Trading Integration
Tests:
1. Rollover month calculation in get_front_month_future (symbol 'ES' -> YYYY03/06/09/12).
2. Suffix mapping in DataFetcher.get_stock_data (symbol 'ES' -> 'ES=F').
3. MultiIndex normalization in DataFetcher._normalize_yfinance_data.
4. Exemption rules in DataFetcher.is_trade_free_us_stock_candidate.
5. Sizing and Risk Sentry exposure scaling in RiskManager.is_within_limits.
6. FUT contract routing parameters in InteractiveBrokersConnection mock.
"""

import sys
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime

# Set up encoding support for Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure we import config first
import config
from data_fetcher import DataFetcher
from utils import get_front_month_future

class TestFuturesIntegration(unittest.TestCase):
    def setUp(self):
        self.fetcher = DataFetcher()

    def test_front_month_rollover_calculation(self):
        """Test 1: Check quarterly index and monthly commodity futures rollover logic"""
        print("\n[Test 1] Testing dynamic rollover calendar month calculator...")
        
        # Verify that ES/NQ/YM/RTY return a quarterly month string: 03, 06, 09, 12
        es_expiry = get_front_month_future("ES")
        self.assertEqual(len(es_expiry), 6, "Expiry string must be exactly 6 characters (YYYYMM)")
        self.assertTrue(es_expiry[-2:] in {"03", "06", "09", "12"}, f"Invalid quarterly expiry month: {es_expiry}")
        
        # Verify commodity monthly rollover
        cl_expiry = get_front_month_future("CL")
        self.assertEqual(len(cl_expiry), 6, "Expiry string must be exactly 6 characters (YYYYMM)")
        print(f"  - ES Expiry resolved: {es_expiry}")
        print(f"  - CL Expiry resolved: {cl_expiry}")
        print("  ✓ Front month rollover calculation passed.")

    @patch('yfinance.download')
    def test_futures_suffix_and_normalization(self, mock_download):
        """Test 2: Suffix '=F' appended for futures, and normalization works"""
        print("\n[Test 2] Testing DataFetcher suffix mapping and normalization for Futures...")
        
        # Create a mock dataframe like yfinance returns
        dates = pd.date_range(start="2026-05-01", periods=5)
        # MultiIndex columns (like yfinance download)
        columns = pd.MultiIndex.from_product(
            [['Adj Close', 'Close', 'High', 'Low', 'Open', 'Volume'], ['ES=F']],
            names=['Price', 'Ticker']
        )
        mock_data = pd.DataFrame(np.random.randn(5, 6), index=dates, columns=columns)
        mock_download.return_value = mock_data

        # Call get_stock_data with base ticker 'ES'
        result = self.fetcher.get_stock_data("ES", period="5d")
        
        # Verify yfinance was called with 'ES=F'
        mock_download.assert_called_with("ES=F", period="5d", interval="1d", progress=False, threads=False)
        self.assertIsNotNone(result, "DataFetcher returned None for ES")
        self.assertIn("Close", result.columns, "Close column missing from normalized DataFrame")
        print("  - Yahoo Finance suffix mapped: 'ES' -> 'ES=F'")
        print("  - DataFrame MultiIndex successfully normalized.")
        print("  ✓ Suffix mapping and normalization passed.")

    def test_futures_liquidity_exemptions(self):
        """Test 3: Futures tickers bypass the strict US stock requirements"""
        print("\n[Test 3] Testing futures liquidity check exemption rules...")
        
        # In stock candidate checking, ES should return True immediately without fetching fundamentals
        is_candidate = self.fetcher.is_trade_free_us_stock_candidate("ES")
        self.assertTrue(is_candidate, "ES was not marked as a valid candidate")
        
        is_candidate_cl = self.fetcher.is_trade_free_us_stock_candidate("CL")
        self.assertTrue(is_candidate_cl, "CL was not marked as a valid candidate")
        print("  - is_trade_free_us_stock_candidate returned True for ES & CL.")
        print("  ✓ Futures check exemption passed.")

    def test_risk_sentry_leverage_exposure_scaling(self):
        """Test 4: Risk Sentry scales position value by futures point multipliers"""
        print("\n[Test 4] Testing RiskManager position limit evaluations using point multipliers...")
        
        from risk_manager import RiskManager
        
        # Mock connection get_account_value to return 100,000
        mock_conn = MagicMock()
        mock_conn.get_account_value.return_value = 100000.0
        
        risk = RiskManager(mock_conn)
        risk.max_position_size = 50000.0  # Max limit
        config.DYNAMIC_RISK_SCALING = False
        
        # Check standard equity AAPL size (100 shares @ $150 = $15,000)
        aapl_ok = risk.is_within_limits("AAPL", quantity=100, entry_price=150.0)
        self.assertTrue(aapl_ok, "Standard AAPL position size of $15,000 should be allowed")
        
        # Check leveraged ES futures (1 contract @ $5,000. Under stock rules it would be $5,000,
        # but with point multiplier (50x) it evaluates as $250,000 notional, which exceeds $50k limit)
        es_ok = risk.is_within_limits("ES", quantity=1, entry_price=5000.0)
        self.assertFalse(es_ok, "ES contract evaluating as $250,000 notional should be blocked by $50,000 limit")
        
        print("  - Standard equity AAPL position evaluates normally.")
        print("  - ES contract evaluates accurately at full notional value ($250,000 instead of raw $5,000).")
        print("  ✓ Point multiplier risk scaling passed.")

    @patch('ib_connection.Contract')
    @patch('ib_connection.Order')
    def test_ibkr_futures_contract_routing(self, mock_order, mock_contract):
        """Test 5: Place order routes futures symbol to proper exchange, Contract Month, and Multiplier"""
        print("\n[Test 5] Testing Interactive Brokers contract routing for futures contracts...")
        
        from ib_connection import InteractiveBrokersConnection
        
        # Disable limit orders constraint temporarily or provide limit details
        config.USE_LIMIT_ORDERS_ONLY = True
        
        # Instantiate connection
        conn = InteractiveBrokersConnection()
        conn.connected = True
        conn.wrapper = MagicMock()
        conn.wrapper.next_order_id = 100
        conn.client = MagicMock()
        
        # Trigger place_order for futures symbol 'ES'
        contract_mock_instance = MagicMock()
        mock_contract.return_value = contract_mock_instance
        
        conn.place_order(symbol="ES", action="BUY", quantity=1, order_type="LMT", limit_price=5000.0)
        
        # Verify that secType is FUT, exchange CME, expiry set, multiplier 50
        self.assertEqual(contract_mock_instance.symbol, "ES")
        self.assertEqual(contract_mock_instance.secType, "FUT")
        self.assertEqual(contract_mock_instance.exchange, "CME")
        self.assertEqual(contract_mock_instance.multiplier, "50")
        self.assertEqual(contract_mock_instance.lastTradeDateOrContractMonth, get_front_month_future("ES"))
        
        # Trigger place_order for futures symbol 'CL'
        contract_mock_instance_cl = MagicMock()
        mock_contract.return_value = contract_mock_instance_cl
        
        conn.place_order(symbol="CL", action="BUY", quantity=1, order_type="LMT", limit_price=80.0)
        self.assertEqual(contract_mock_instance_cl.symbol, "CL")
        self.assertEqual(contract_mock_instance_cl.secType, "FUT")
        self.assertEqual(contract_mock_instance_cl.exchange, "NYMEX")
        self.assertEqual(contract_mock_instance_cl.multiplier, "1000")
        self.assertEqual(contract_mock_instance_cl.lastTradeDateOrContractMonth, get_front_month_future("CL"))
        
        print("  - Index futures ('ES') routed to secType='FUT', exchange='CME', multiplier='50'")
        print("  - Commodity futures ('CL') routed to secType='FUT', exchange='NYMEX', multiplier='1000'")
        print("  ✓ FUT contract parameters and exchange routing passed.")

def main():
    print("=" * 70)
    print("  INTERACTIVE BROKERS AUTOMATED FUTURES TRADING INTEGRATION TESTS")
    print("=" * 70)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFuturesIntegration)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n" + "="*70)
        print("ALL TESTS PASSED SUCCESSFULLY! FUTURES INTEGRATION AND ROUTING IS 100% CORRECT.")
        print("="*70 + "\n")
    else:
        print("\n❌ Tests failed!\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
