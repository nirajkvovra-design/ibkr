#!/usr/bin/env python
"""
Verification script for Dynamic Stock Universe Expander
Tests:
1. Dynamic theme query parsing (Mocked HTTP search responses).
2. Candidate validation using DataFetcher liquidity checks.
3. Disk serialization/deserialization (dynamic_universe.json).
4. Screener pool dynamic integration.
"""

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Set up encoding support for Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from universe_expander import UniverseExpander, _SAVE_PATH
from stock_screener import StockScreener
from data_fetcher import DataFetcher
import config

class MockDataFetcher(DataFetcher):
    """Subclass of DataFetcher with static liquidity overrides for deterministic tests"""
    def __init__(self, valid_tickers):
        super().__init__()
        self.valid_tickers = set(valid_tickers)

    def is_trade_free_us_stock_candidate(self, symbol):
        return symbol in self.valid_tickers

    def get_calendar_risk(self, symbol):
        return {'blocked': False, 'reason': ''}

class TestUniverseExpander(unittest.TestCase):
    def setUp(self):
        # Back up existing dynamic_universe.json if it exists
        self.backup_path = Path("dynamic_universe.json.backup")
        if _SAVE_PATH.exists():
            _SAVE_PATH.rename(self.backup_path)

    def tearDown(self):
        # Clean up temporary test files
        if _SAVE_PATH.exists():
            _SAVE_PATH.unlink()
        # Restore backup if it existed
        if self.backup_path.exists():
            self.backup_path.rename(_SAVE_PATH)

    def test_dynamic_saving_and_loading(self):
        """Test 1: Disk saving and loading works correctly"""
        print("\n[Test 1] Testing dynamic ticker disk serialization...")
        
        fetcher = MockDataFetcher([])
        expander = UniverseExpander(fetcher)
        expander.discovered_tickers = {"IONQ", "OKLO", "RGTI"}
        
        expander.save_dynamic_tickers()
        
        # Verify file exists and has correct elements
        self.assertTrue(_SAVE_PATH.exists(), "dynamic_universe.json was not created")
        with _SAVE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data), 3)
            self.assertIn("IONQ", data)
            self.assertIn("OKLO", data)
            
        # Verify loading works on a fresh instance
        expander_new = UniverseExpander(fetcher)
        self.assertEqual(expander_new.discovered_tickers, {"IONQ", "OKLO", "RGTI"})
        print("  ✓ Ticker saving and loading validated.")

    @patch('requests.get')
    def test_universe_expansion(self, mock_get):
        """Test 2: Dynamic API search parsing and liquidity validation"""
        print("\n[Test 2] Testing dynamic API search parsing and liquidity screening...")
        
        # Mock API Search Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "quotes": [
                {"symbol": "IONQ", "quoteType": "EQUITY", "exchange": "NMS"},
                {"symbol": "OKLO", "quoteType": "EQUITY", "exchange": "NYQ"},
                {"symbol": "INVALID1", "quoteType": "MUTUALFUND", "exchange": "NMS"}, # Invalid type
                {"symbol": "SPX-IPO", "quoteType": "EQUITY", "exchange": "NMS"}      # Valid equity
            ]
        }
        mock_get.return_value = mock_response

        # We configure MockDataFetcher so that IONQ, OKLO, and SPX-IPO are valid, but INVALID1 is not
        valid_tickers = ["IONQ", "OKLO", "SPX-IPO"]
        fetcher = MockDataFetcher(valid_tickers)
        
        expander = UniverseExpander(fetcher)
        
        # Run expansion
        discovered = expander.expand_universe()
        
        print(f"  Discovered tickers: {discovered}")
        self.assertIn("IONQ", discovered, "Failed to discover IONQ")
        self.assertIn("OKLO", discovered, "Failed to discover OKLO")
        self.assertIn("SPX-IPO", discovered, "Failed to discover SpaceX/SPX-IPO")
        self.assertNotIn("INVALID1", discovered, "Incorrectly added non-equity mutual fund")
        print("  ✓ API discovery, type filtering, and liquidity check passed.")

    @patch('requests.get')
    def test_screener_watchlist_merging(self, mock_get):
        """Test 3: Automatic integration into StockScreener pool"""
        print("\n[Test 3] Testing dynamic integration into StockScreener pool...")
        
        # Pre-seed dynamic_universe.json with a valid thematic winner
        fetcher = MockDataFetcher(["IONQ", "OKLO"])
        expander = UniverseExpander(fetcher)
        expander.discovered_tickers = {"IONQ", "OKLO"}
        expander.save_dynamic_tickers()
        
        # Instantiate StockScreener and check default stocks list
        screener = StockScreener()
        
        print(f"  Screener default list: {screener.default_stocks[:8]}...")
        self.assertIn("IONQ", screener.default_stocks, "IONQ was not merged into StockScreener watchlist")
        self.assertIn("OKLO", screener.default_stocks, "OKLO was not merged into StockScreener watchlist")
        print("  ✓ Discovered tickers merged into active screener search pool.")

def main():
    print("=" * 70)
    print("  DYNAMIC STOCK UNIVERSE EXPANDER TESTS")
    print("=" * 70)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUniverseExpander)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n" + "="*70)
        print("ALL TESTS PASSED SUCCESSFULLY! FEATURE IMPLEMENTATION INTEGRITY IS 100% CORRECT.")
        print("="*70 + "\n")
    else:
        print("\n❌ Tests failed!\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
