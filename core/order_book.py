"""
LocalOrderBook Core Engine for Market Microstructure Analytics.
Tracks Level 2 order book depth and calculates high-fidelity microstructure signals.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from utils import get_logger

logger = get_logger(__name__)


class LocalOrderBook:
    """
    High-performance Level 2 Local Order Book.
    Maintains sorted lists of bids and asks, and computes microstructure metrics.
    """

    def __init__(self, symbol: str):
        self.symbol: str = symbol.upper()
        self.lock = threading.Lock()
        
        # Order Book queues: list of [price, size]
        # Bids sorted descending by price, asks sorted ascending by price
        self.bids: List[List[float]] = []
        self.asks: List[List[float]] = []
        
        # State tracking for Order Flow Imbalance (OFI)
        self.prev_best_bid_price: Optional[float] = None
        self.prev_best_bid_size: Optional[float] = None
        self.prev_best_ask_price: Optional[float] = None
        self.prev_best_ask_size: Optional[float] = None

    def update_level(self, position: int, operation: int, side: int, price: float, size: float) -> None:
        """
        Update the order book depth rows.
        
        Args:
            position: Row index (0-indexed).
            operation: 0 = INSERT, 1 = UPDATE, 2 = DELETE.
            side: 0 = ASK, 1 = BID.
            price: Order book price level.
            size: Volume size at this level.
        """
        with self.lock:
            target_list = self.bids if side == 1 else self.asks

            if operation == 0:  # INSERT
                if position <= len(target_list):
                    target_list.insert(position, [price, float(size)])
                else:
                    target_list.append([price, float(size)])
            elif operation == 1:  # UPDATE
                if position < len(target_list):
                    target_list[position] = [price, float(size)]
                else:
                    # Fallback to appending if update index is out of bounds
                    target_list.append([price, float(size)])
            elif operation == 2:  # DELETE
                if position < len(target_list):
                    target_list.pop(position)
            
            # Post-update validation: Ensure correct price sorting in depth
            if side == 1:
                # Bids must be sorted descending by price
                self.bids.sort(key=lambda x: x[0], reverse=True)
            else:
                # Asks must be sorted ascending by price
                self.asks.sort(key=lambda x: x[0])

    def get_spread(self) -> Tuple[float, float, float]:
        """Return best bid, best ask, and absolute spread."""
        with self.lock:
            best_bid = self.bids[0][0] if self.bids else 0.0
            best_ask = self.asks[0][0] if self.asks else 0.0
            spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0.0
            return best_bid, best_ask, spread

    def get_depth(self, levels: int = 5) -> Tuple[List[List[float]], List[List[float]]]:
        """Return top N bids and asks levels."""
        with self.lock:
            return self.bids[:levels].copy(), self.asks[:levels].copy()

    def calculate_wap(self) -> float:
        """
        Calculate Weighted Average Price (WAP) of the top level.
        WAP = (BidPrice * AskSize + AskPrice * BidSize) / (BidSize + AskSize)
        """
        with self.lock:
            if not self.bids or not self.asks:
                return 0.0
            
            bid_price, bid_size = self.bids[0]
            ask_price, ask_size = self.asks[0]
            
            total_size = bid_size + ask_size
            if total_size <= 0:
                return 0.0
            
            wap = (bid_price * ask_size + ask_price * bid_size) / total_size
            return float(wap)

    def calculate_book_imbalance(self, depth: int = 5) -> float:
        """
        Calculate Book Volume Imbalance of top N levels.
        Imbalance = (BidVol - AskVol) / (BidVol + AskVol)
        """
        with self.lock:
            bid_vol = sum(level[1] for level in self.bids[:depth])
            ask_vol = sum(level[1] for level in self.asks[:depth])
            
            total_vol = bid_vol + ask_vol
            if total_vol <= 0:
                return 0.0
            
            imbalance = (bid_vol - ask_vol) / total_vol
            return float(imbalance)

    def calculate_ofi(self) -> float:
        """
        Calculate Order Flow Imbalance (OFI) since the last update.
        Solves changes in top bid/ask price levels and accumulated depth volumes.
        """
        with self.lock:
            if not self.bids or not self.asks:
                return 0.0

            current_bid_price, current_bid_size = self.bids[0]
            current_ask_price, current_ask_size = self.asks[0]

            # 1. Solve Bid changes
            delta_v_bid = 0.0
            if self.prev_best_bid_price is not None:
                if current_bid_price > self.prev_best_bid_price:
                    delta_v_bid = current_bid_size
                elif current_bid_price == self.prev_best_bid_price:
                    delta_v_bid = current_bid_size - self.prev_best_bid_size
                else:
                    delta_v_bid = -self.prev_best_bid_size
            
            # 2. Solve Ask changes
            delta_v_ask = 0.0
            if self.prev_best_ask_price is not None:
                if current_ask_price < self.prev_best_ask_price:
                    delta_v_ask = current_ask_size
                elif current_ask_price == self.prev_best_ask_price:
                    delta_v_ask = current_ask_size - self.prev_best_ask_size
                else:
                    delta_v_ask = -self.prev_best_ask_size

            # Store current best levels for the next period computation
            self.prev_best_bid_price = current_bid_price
            self.prev_best_bid_size = current_bid_size
            self.prev_best_ask_price = current_ask_price
            self.prev_best_ask_size = current_ask_size

            # OFI = Delta_Bid - Delta_Ask
            return delta_v_bid - delta_v_ask

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a structured dictionary snapshot of the order book and its metrics."""
        best_bid, best_ask, spread = self.get_spread()
        bids_depth, asks_depth = self.get_depth(levels=5)
        
        return {
            "symbol": self.symbol,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "wap": self.calculate_wap(),
            "book_imbalance": self.calculate_book_imbalance(),
            "bids_depth": bids_depth,
            "asks_depth": asks_depth,
        }
