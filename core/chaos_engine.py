"""
Programmatic Chaos Engine
Intentionally injects broker connection failures, latency spikes, packet corruption,
and partial fills to stress test system resilience, recovery mechanisms, and safety locks.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable, Dict, Optional

from utils import get_logger

logger = get_logger(__name__)


class ChaosEngine:
    """
    Hedge-fund scale Chaos Injection Engine.
    Allows automated stress testing of trading OS components under failure conditions.
    """

    _instance: Optional[ChaosEngine] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ChaosEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize configuration if not already set
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.enabled = False
            
            # Chaos injection scenarios
            self.latency_injection = False
            self.min_latency_ms = 100
            self.max_latency_ms = 1000
            
            self.socket_drop_rate = 0.0  # Probability of dropping socket on request
            self.partial_fill_rate = 0.0  # Probability of forcing a partial fill
            self.partial_fill_fraction = 0.5  # Fraction of order quantity to fill
            
            self.packet_corruption_rate = 0.0  # Probability of corrupting incoming book price values

    def configure(
        self,
        enabled: bool = False,
        latency_injection: bool = False,
        min_latency_ms: int = 100,
        max_latency_ms: int = 1000,
        socket_drop_rate: float = 0.0,
        partial_fill_rate: float = 0.0,
        partial_fill_fraction: float = 0.5,
        packet_corruption_rate: float = 0.0,
    ) -> None:
        """
        Configure the active chaos parameters.
        """
        self.enabled = enabled
        self.latency_injection = latency_injection
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.socket_drop_rate = socket_drop_rate
        self.partial_fill_rate = partial_fill_rate
        self.partial_fill_fraction = partial_fill_fraction
        self.packet_corruption_rate = packet_corruption_rate
        
        if enabled:
            logger.warning("[Chaos Sentry] Programmatic chaos injection is active!")
        else:
            logger.info("[Chaos Sentry] Programmatic chaos injection disabled.")

    def inject_latency(self) -> None:
        """
        Inject a synchronous blocking delay to simulate execution round-trip spikes.
        """
        if not self.enabled or not self.latency_injection:
            return
        
        delay_ms = random.randint(self.min_latency_ms, self.max_latency_ms)
        logger.warning("[Chaos Sentry] Injecting latency delay of %d ms...", delay_ms)
        time.sleep(delay_ms / 1000.0)

    async def inject_async_latency(self) -> None:
        """
        Inject an asynchronous delay to simulate async network routing overhead.
        """
        if not self.enabled or not self.latency_injection:
            return
        
        delay_ms = random.randint(self.min_latency_ms, self.max_latency_ms)
        logger.warning("[Chaos Sentry] Injecting async latency delay of %d ms...", delay_ms)
        await asyncio.sleep(delay_ms / 1000.0)

    def should_drop_socket(self) -> bool:
        """
        Evaluate if a socket connection drop should be triggered.
        """
        if not self.enabled or self.socket_drop_rate <= 0.0:
            return False
        return random.random() < self.socket_drop_rate

    def should_force_partial_fill(self) -> bool:
        """
        Evaluate if a partial fill should be forced.
        """
        if not self.enabled or self.partial_fill_rate <= 0.0:
            return False
        return random.random() < self.partial_fill_rate

    def force_partial_quantity(self, original_qty: float) -> float:
        """
        Calculate a truncated quantity for simulating partial fills.
        """
        return max(1.0, round(original_qty * self.partial_fill_fraction, 2))

    def corrupt_packet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject random data corruption or anomalies into real-time metric streams.
        """
        if not self.enabled or self.packet_corruption_rate <= 0.0:
            return data
        
        if random.random() < self.packet_corruption_rate:
            corrupted = data.copy()
            logger.warning("[Chaos Sentry] Injecting data corruption into packet!")
            # Mutate prices or set negative values
            for key in ["best_bid", "best_ask", "price", "wap"]:
                if key in corrupted and isinstance(corrupted[key], (int, float)):
                    corrupted[key] = -999.0
            return corrupted
        return data
