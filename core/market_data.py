from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

import random
from data_fetcher import DataFetcher
from utils import get_logger
from core.order_book import LocalOrderBook

logger = get_logger(__name__)


class MarketDataEngine:
    """Async market data abstraction for price polling, historical fetch, and Level 2 depth streaming."""

    def __init__(self, fetcher: Optional[DataFetcher] = None, ib_connection: Optional[Any] = None):
        self.fetcher = fetcher or DataFetcher()
        self.ib_connection = ib_connection
        self.subscriptions: Dict[str, asyncio.Task] = {}
        
        # Level 2 Depth Subscriptions
        self.order_books: Dict[str, LocalOrderBook] = {}
        self.depth_tasks: Dict[str, asyncio.Task] = {}

    async def get_historical_data(self, symbol: str, period: str = "3mo", interval: str = "1d"):
        return await asyncio.to_thread(self.fetcher.get_stock_data, symbol, period, interval)

    async def get_current_price(self, symbol: str) -> Optional[float]:
        return await asyncio.to_thread(self.fetcher.get_current_price, symbol)

    async def get_limit_price(self, symbol: str, action: str) -> Optional[float]:
        return await asyncio.to_thread(self.fetcher.get_limit_price, symbol, action)

    def clear_cache(self) -> None:
        self.fetcher.clear_cache()

    def subscribe_price(
        self,
        symbol: str,
        callback: Callable[[str, Optional[float]], Any],
        interval_seconds: int = 15,
    ) -> None:
        if symbol in self.subscriptions:
            logger.warning("Already subscribed to %s", symbol)
            return

        async def poll():
            while True:
                price = await self.get_current_price(symbol)
                try:
                    callback(symbol, price)
                except Exception as exc:
                    logger.error("MarketDataEngine callback failed for %s: %s", symbol, exc)
                await asyncio.sleep(interval_seconds)

        self.subscriptions[symbol] = asyncio.create_task(poll())

    def unsubscribe_price(self, symbol: str) -> None:
        task = self.subscriptions.pop(symbol, None)
        if task and not task.done():
            task.cancel()

    def subscribe_l2_depth(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], Any],
        req_id: int = 2000,
        event_engine: Optional[Any] = None,
        sim_interval_seconds: float = 0.5,
    ) -> None:
        """
        Subscribe to real-time Level 2 market depth streaming.
        Routes to TWS reqMktDepth if live, or fallback to deep-liquidity simulation.
        """
        symbol_upper = symbol.upper()
        if symbol_upper in self.depth_tasks:
            logger.warning("Already subscribed to market depth for %s", symbol_upper)
            return

        # Initialize LocalOrderBook
        book = LocalOrderBook(symbol_upper)
        self.order_books[symbol_upper] = book

        # 1. Live TWS integration
        if self.ib_connection and self.ib_connection.connected:
            self.ib_connection.set_event_engine(event_engine)
            # Route to EWrapper L2 updates
            self.ib_connection.wrapper.order_books[symbol_upper] = book
            self.ib_connection.subscribe_market_depth(symbol_upper, req_id)
            
            # Simple async listener that dispatches EVENT_TICK to callback
            async def event_listener():
                if event_engine:
                    # Let event engine handle dispatches. We can also register callback.
                    pass
                while True:
                    await asyncio.sleep(1.0)

            self.depth_tasks[symbol_upper] = asyncio.create_task(event_listener())
            logger.info("[MarketDataEngine] Live TWS market depth subscribed for %s", symbol_upper)
            return

        # 2. Asynchronous Fallback Deep-Liquidity Simulation
        async def simulate_depth():
            logger.info("[MarketDataEngine] Starting Level 2 deep-liquidity simulation for %s", symbol_upper)
            
            # Seed starting price
            curr_price = await self.get_current_price(symbol_upper)
            if not curr_price or curr_price <= 0:
                curr_price = 100.0

            # Seed initial 5 price levels for Bids and Asks
            for i in range(5):
                bid_price = round(curr_price - 0.10 * (i + 1), 2)
                ask_price = round(curr_price + 0.10 * (i + 1), 2)
                book.update_level(position=i, operation=0, side=1, price=bid_price, size=random.randint(100, 1000))
                book.update_level(position=i, operation=0, side=0, price=ask_price, size=random.randint(100, 1000))

            while True:
                try:
                    # 1. Fluctuate base price slightly (Random walk)
                    price_shift = round(random.choice([-0.02, -0.01, 0.0, 0.01, 0.02]), 2)
                    curr_price = round(curr_price + price_shift, 2)

                    # 2. Modify one of the Bid levels randomly (UPDATE or DELETE/INSERT)
                    idx = random.randint(0, 4)
                    bid_price = round(curr_price - 0.10 * (idx + 1), 2)
                    ask_price = round(curr_price + 0.10 * (idx + 1), 2)

                    book.update_level(position=idx, operation=1, side=1, price=bid_price, size=random.randint(100, 1500))
                    book.update_level(position=idx, operation=1, side=0, price=ask_price, size=random.randint(100, 1500))

                    # 3. Compile snapshot and trigger dispatches
                    snapshot = book.get_snapshot()
                    
                    try:
                        callback(snapshot)
                    except Exception as e:
                        logger.error("L2 callback failed for %s: %s", symbol_upper, e)

                    if event_engine:
                        from core.event_engine import Event, EVENT_TICK
                        event_engine.put(Event(EVENT_TICK, data=snapshot))

                except Exception as ex:
                    logger.error("Error in L2 simulator for %s: %s", symbol_upper, ex)

                await asyncio.sleep(sim_interval_seconds)

        self.depth_tasks[symbol_upper] = asyncio.create_task(simulate_depth())

    def unsubscribe_l2_depth(self, symbol: str, req_id: int = 2000) -> None:
        """Cancel Level 2 market depth subscription."""
        symbol_upper = symbol.upper()
        task = self.depth_tasks.pop(symbol_upper, None)
        if task and not task.done():
            task.cancel()

        self.order_books.pop(symbol_upper, None)

        if self.ib_connection and self.ib_connection.connected:
            self.ib_connection.unsubscribe_market_depth(req_id)
            self.ib_connection.wrapper.order_books.pop(symbol_upper, None)
            
        logger.info("[MarketDataEngine] Unsubscribed market depth for %s", symbol_upper)
