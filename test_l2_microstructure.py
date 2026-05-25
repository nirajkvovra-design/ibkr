"""
Verification and Integration Suite for Level 2 Order Book & Microstructure Analytics.
Tests:
1. LocalOrderBook level insertions, updates, and deletions maintaining price sorting.
2. Microstructure metrics: WAP and Book Imbalance calculations.
3. Microstructure metrics: Order Flow Imbalance (OFI) calculations on sequential updates.
4. MarketDataEngine async simulated depth streaming dispatching ticks correctly.
"""

import asyncio
import unittest
from unittest.mock import MagicMock

from core.event_engine import EventEngine, Event, EVENT_TICK
from core.market_data import MarketDataEngine
from core.order_book import LocalOrderBook


class TestL2Microstructure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.symbol = "AAPL"
        self.book = LocalOrderBook(self.symbol)

    def test_l2_price_sorting_and_depth(self):
        """Test bid/ask row changes are sorted correctly (Bids descending, Asks ascending)."""
        # Bids: insert out of order
        self.book.update_level(position=0, operation=0, side=1, price=150.00, size=500)
        self.book.update_level(position=1, operation=0, side=1, price=149.00, size=300)
        self.book.update_level(position=2, operation=0, side=1, price=151.00, size=100) # Should sort to index 0

        bids, _ = self.book.get_depth(levels=3)
        self.assertEqual(len(bids), 3)
        self.assertEqual(bids[0][0], 151.00) # Best Bid (highest price)
        self.assertEqual(bids[1][0], 150.00)
        self.assertEqual(bids[2][0], 149.00)

        # Asks: insert out of order
        self.book.update_level(position=0, operation=0, side=0, price=152.00, size=400)
        self.book.update_level(position=1, operation=0, side=0, price=153.00, size=600)
        self.book.update_level(position=2, operation=0, side=0, price=151.50, size=200) # Should sort to index 0

        _, asks = self.book.get_depth(levels=3)
        self.assertEqual(len(asks), 3)
        self.assertEqual(asks[0][0], 151.50) # Best Ask (lowest price)
        self.assertEqual(asks[1][0], 152.00)
        self.assertEqual(asks[2][0], 153.00)

        # Test absolute spread
        best_bid, best_ask, spread = self.book.get_spread()
        self.assertEqual(best_bid, 151.00)
        self.assertEqual(best_ask, 151.50)
        self.assertAlmostEqual(spread, 0.50, places=2)

    def test_wap_and_book_imbalance_metrics(self):
        """Test Weighted Average Price (WAP) and Book Imbalance calculations."""
        # Setup top level: Bid 150.00 x 400 size, Ask 152.00 x 100 size
        self.book.update_level(position=0, operation=0, side=1, price=150.00, size=400)
        self.book.update_level(position=0, operation=0, side=0, price=152.00, size=100)

        # WAP = (150 * 100 + 152 * 400) / 500 = (15000 + 60800) / 500 = 75800 / 500 = 151.60
        wap = self.book.calculate_wap()
        self.assertAlmostEqual(wap, 151.60, places=2)

        # Book Imbalance = (BidVol - AskVol) / (BidVol + AskVol) = (400 - 100) / 500 = 300 / 500 = 0.60
        imbalance = self.book.calculate_book_imbalance(depth=1)
        self.assertAlmostEqual(imbalance, 0.60, places=2)

    def test_order_flow_imbalance_calculations(self):
        """Test Order Flow Imbalance (OFI) calculations on sequential updates."""
        # 1. Initial State: Bid 100.00 x 50 shares, Ask 102.00 x 40 shares
        self.book.update_level(position=0, operation=0, side=1, price=100.00, size=50)
        self.book.update_level(position=0, operation=0, side=0, price=102.00, size=40)
        
        # Seed initial OFI state
        self.book.calculate_ofi()

        # 2. Update 1: Bid price rises to 101.00 x 60 shares, Ask price stays at 102.00 but size rises to 70 shares
        # Bid price rose -> Delta Bid = 60
        # Ask price stayed -> Delta Ask = 70 - 40 = 30
        # OFI = 60 - 30 = +30
        self.book.update_level(position=0, operation=0, side=1, price=101.00, size=60)
        self.book.update_level(position=0, operation=1, side=0, price=102.00, size=70)
        
        ofi = self.book.calculate_ofi()
        self.assertEqual(ofi, 30.0, "OFI calculation failed on Price Rise / Size Change.")

        # 3. Update 2: Bid price falls back to 100.00 x 50 shares, Ask price falls to 101.50 x 30 shares
        # Bid price fell -> Delta Bid = -60 (previous bid size)
        # Ask price fell -> Delta Ask = 30 (new ask size)
        # OFI = -60 - 30 = -90
        self.book.update_level(position=0, operation=2, side=1, price=101.00, size=60)
        self.book.update_level(position=0, operation=0, side=0, price=101.50, size=30)
        
        ofi2 = self.book.calculate_ofi()
        self.assertEqual(ofi2, -90.0, "OFI calculation failed on Price Falls / Ask Shifts.")

    async def test_simulated_depth_streaming(self):
        """Test MarketDataEngine deep-liquidity simulation stream updates are dispatched correctly."""
        engine = EventEngine()
        engine.start()

        mde = MarketDataEngine()
        async def mock_get_price(sym):
            return 100.0
        mde.get_current_price = mock_get_price

        callback_called = False
        received_snapshot = None

        def callback(snapshot):
            nonlocal callback_called, received_snapshot
            callback_called = True
            received_snapshot = snapshot

        # Subscribe to simulated L2 updates with high frequency (100ms)
        mde.subscribe_l2_depth(
            self.symbol,
            callback=callback,
            event_engine=engine,
            sim_interval_seconds=0.1
        )

        # Wait briefly for multiple ticks to stream
        await asyncio.sleep(0.4)

        # Unsubscribe to halt task loop
        mde.unsubscribe_l2_depth(self.symbol)
        await engine.stop()

        self.assertTrue(callback_called, "Simulated market depth callback was never triggered.")
        self.assertIsNotNone(received_snapshot, "Simulated snapshot payload is empty.")
        self.assertEqual(received_snapshot["symbol"], self.symbol)
        self.assertEqual(len(received_snapshot["bids_depth"]), 5, "Simulated bid depth is incomplete.")
        self.assertEqual(len(received_snapshot["asks_depth"]), 5, "Simulated ask depth is incomplete.")
        self.assertTrue(received_snapshot["wap"] > 0, "Weighted Average Price is zero or invalid.")


if __name__ == "__main__":
    unittest.main()
