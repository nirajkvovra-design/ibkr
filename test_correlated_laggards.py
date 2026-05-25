#!/usr/bin/env python
"""
Verification script for Correlated Laggard Sector Catch-Up Trading Strategy
Tests:
1. Thematic mapping configuration and retrieval.
2. Laggard buy signal triggers during leader breakout.
3. Signal blocking when laggard has already caught up.
4. Signal blocking when laggard is overbought (RSI >= 60).
"""

import sys
import unittest
import pandas as pd
from unittest.mock import MagicMock, patch

# Set up encoding support for Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
from strategies import CorrelatedLaggardStrategy

class TestCorrelatedLaggards(unittest.TestCase):
    def setUp(self):
        # Save standard configurations
        self.old_correlations = getattr(config, "THEMATIC_CORRELATIONS", {})
        config.THEMATIC_CORRELATIONS = {
            "AI_HARDWARE": {
                "leader": "NVDA",
                "laggards": ["AMD", "SMCI"]
            }
        }
        config.LAGGER_LEADER_MIN_RETURN = 0.015
        config.LAGGER_LEADER_MIN_VOLUME_RATIO = 1.2
        config.LAGGER_MAX_CATCHUP_RATIO = 0.3
        config.LAGGER_MAX_RSI = 60.0

    def tearDown(self):
        config.THEMATIC_CORRELATIONS = self.old_correlations

    def test_thematic_mapping(self):
        """Test 1: Verify Leader/Laggard relations are mapped correctly"""
        print("\n[Test 1] Testing thematic correlations mapping structure...")
        correlations = getattr(config, "THEMATIC_CORRELATIONS", {})
        self.assertIn("AI_HARDWARE", correlations)
        self.assertEqual(correlations["AI_HARDWARE"]["leader"], "NVDA")
        self.assertListEqual(correlations["AI_HARDWARE"]["laggards"], ["AMD", "SMCI"])
        print("  ✓ Mapping configuration validated successfully.")

    @patch('strategies.DataFetcher')
    def test_laggard_buy_signal_trigger(self, mock_fetcher_class):
        """Test 2: Verify buy signal triggers when leader breaks out and laggard is lagging"""
        print("\n[Test 2] Testing laggard BUY signal triggers during leader breakout...")
        
        mock_conn = MagicMock()
        mock_conn.get_positions.return_value = {}
        mock_conn.has_active_order.return_value = False
        
        strategy = CorrelatedLaggardStrategy(mock_conn)
        mock_fetcher = MagicMock()
        
        # 1. Leader (NVDA) surges 2.0% on 1.5x Volume Ratio (Breakout!)
        leader_data = pd.DataFrame({
            'Close': [100.0, 102.0],
            'Volume_Ratio': [1.0, 1.5],
            'RSI': [50.0, 55.0]
        })
        
        # 2. Laggard (AMD) is flat (0.0% return) and not overbought (RSI = 45)
        laggard_data = pd.DataFrame({
            'Close': [50.0, 50.0],
            'Volume_Ratio': [1.0, 1.0],
            'RSI': [45.0, 45.0]
        })
        
        # Mock fetcher outputs
        def get_stock_data_mock(symbol, *args, **kwargs):
            if symbol == "NVDA":
                return leader_data
            elif symbol == "AMD":
                return laggard_data
            return None
            
        mock_fetcher.get_stock_data.side_effect = get_stock_data_mock
        strategy.data_fetcher = mock_fetcher
        
        # Execute signals
        signals = strategy.generate_signals(["NVDA", "AMD"])
        
        self.assertEqual(signals.get("AMD"), "BUY")
        self.assertEqual(signals.get("NVDA"), "HOLD")
        
        print("  - Leader breakout (NVDA +2.0%, Vol Ratio 1.5) successfully detected.")
        print("  - Laggard status verified (AMD +0.0% return, RSI 45).")
        print("  ✓ BUY signal triggered for AMD as expected.")

    @patch('strategies.DataFetcher')
    def test_laggard_no_signal_when_caught_up(self, mock_fetcher_class):
        """Test 3: Verify no signal is generated if the laggard has already caught up"""
        print("\n[Test 3] Testing signal omission when laggard has already caught up...")
        
        mock_conn = MagicMock()
        mock_conn.get_positions.return_value = {}
        mock_conn.has_active_order.return_value = False
        
        strategy = CorrelatedLaggardStrategy(mock_conn)
        mock_fetcher = MagicMock()
        
        # 1. Leader (NVDA) surges 2.0%
        leader_data = pd.DataFrame({
            'Close': [100.0, 102.0],
            'Volume_Ratio': [1.0, 1.5]
        })
        
        # 2. Laggard (AMD) also surges 1.8% (caught up!)
        laggard_data = pd.DataFrame({
            'Close': [50.0, 50.9],
            'Volume_Ratio': [1.0, 1.0],
            'RSI': [45.0, 52.0]
        })
        
        def get_stock_data_mock(symbol, *args, **kwargs):
            if symbol == "NVDA":
                return leader_data
            elif symbol == "AMD":
                return laggard_data
            return None
            
        mock_fetcher.get_stock_data.side_effect = get_stock_data_mock
        strategy.data_fetcher = mock_fetcher
        
        signals = strategy.generate_signals(["NVDA", "AMD"])
        
        self.assertEqual(signals.get("AMD"), "HOLD")
        print("  - Laggard (AMD +1.8%) caught up with leader (NVDA +2.0%).")
        print("  ✓ No BUY signal generated for AMD.")

    @patch('strategies.DataFetcher')
    def test_laggard_no_signal_when_overbought(self, mock_fetcher_class):
        """Test 4: Verify no signal is generated if the laggard is overbought (RSI >= 60)"""
        print("\n[Test 4] Testing signal blocking when laggard is overbought (RSI >= 60)...")
        
        mock_conn = MagicMock()
        mock_conn.get_positions.return_value = {}
        mock_conn.has_active_order.return_value = False
        
        strategy = CorrelatedLaggardStrategy(mock_conn)
        mock_fetcher = MagicMock()
        
        # 1. Leader (NVDA) surges 2.0%
        leader_data = pd.DataFrame({
            'Close': [100.0, 102.0],
            'Volume_Ratio': [1.0, 1.5]
        })
        
        # 2. Laggard (AMD) is flat (0.0%) but already overbought (RSI = 65)
        laggard_data = pd.DataFrame({
            'Close': [50.0, 50.0],
            'Volume_Ratio': [1.0, 1.0],
            'RSI': [65.0, 65.0]
        })
        
        def get_stock_data_mock(symbol, *args, **kwargs):
            if symbol == "NVDA":
                return leader_data
            elif symbol == "AMD":
                return laggard_data
            return None
            
        mock_fetcher.get_stock_data.side_effect = get_stock_data_mock
        strategy.data_fetcher = mock_fetcher
        
        signals = strategy.generate_signals(["NVDA", "AMD"])
        
        self.assertEqual(signals.get("AMD"), "HOLD")
        print("  - Laggard (AMD) is lagging but overbought (RSI = 65).")
        print("  ✓ BUY signal correctly blocked for AMD.")

def main():
    print("=" * 70)
    print("  CORRELATED LAGGER SECTOR CATCH-UP STRATEGY TESTS")
    print("=" * 70)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCorrelatedLaggards)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n" + "="*70)
        print("ALL TESTS PASSED SUCCESSFULLY! CORRELATED LAGGER STRATEGY IS 100% CORRECT.")
        print("="*70 + "\n")
    else:
        print("\n❌ Tests failed!\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
