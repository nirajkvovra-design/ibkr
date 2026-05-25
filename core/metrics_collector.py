"""
Performance Metrics Collector and Observability Engine.
Tracks order latency, trade slippage, and portfolio performance metrics.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """
    Thread-safe performance metrics collector.
    Records latency, slippage, trade results, and exports system telemetry.
    """

    def __init__(self, metrics_file: str = "metrics.json"):
        self.metrics_filepath = Path(metrics_file)
        self.lock = threading.Lock()
        
        # Performance Stores
        self.order_timestamps: Dict[int, float] = {}  # order_id -> submission_timestamp
        self.latencies: List[float] = []               # latency values in ms
        self.slippages: List[float] = []               # absolute slippage values
        self.slippages_pct: List[float] = []           # percentage slippages
        self.trade_results: List[Dict[str, Any]] = []  # completed trades realized stats
        
        # Load existing metrics if present
        self._load_metrics()

    def _load_metrics(self) -> None:
        """Load historical metrics from disk."""
        with self.lock:
            if not self.metrics_filepath.exists():
                return
            try:
                content = self.metrics_filepath.read_text(encoding="utf-8")
                if not content.strip():
                    return
                data = json.loads(content)
                self.latencies = data.get("latencies", [])
                self.slippages = data.get("slippages", [])
                self.slippages_pct = data.get("slippages_pct", [])
                self.trade_results = data.get("trade_results", [])
                logger.info(
                    "Loaded metrics from %s. Latency entries: %d. Completed trades: %d",
                    self.metrics_filepath.name,
                    len(self.latencies),
                    len(self.trade_results),
                )
            except Exception as e:
                logger.error("Failed to load metrics from %s: %s", self.metrics_filepath, e)

    def _save_metrics(self) -> None:
        """Persist current metrics database to structured JSON."""
        try:
            self.metrics_filepath.parent.mkdir(parents=True, exist_ok=True)
            stats = self.get_summary_statistics()
            data = {
                "summary": stats,
                "latencies": self.latencies[-1000:],     # Cap raw lists to prevent file bloat
                "slippages": self.slippages[-1000:],
                "slippages_pct": self.slippages_pct[-1000:],
                "trade_results": self.trade_results[-100:],
            }
            self.metrics_filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save metrics to %s: %s", self.metrics_filepath, e)

    def record_order_submitted(self, order_id: int) -> None:
        """Record the precise submission time of an order to calculate execution latency."""
        with self.lock:
            self.order_timestamps[order_id] = time.time()
            logger.debug("[Telemetry] Order %s submission timestamp recorded.", order_id)

    def record_order_filled(
        self,
        order_id: int,
        symbol: str,
        action: str,
        quantity: float,
        fill_price: float,
        target_price: float,
    ) -> None:
        """
        Record order fill details.
        Calculates execution latency and execution slippage relative to target price.
        """
        with self.lock:
            # 1. Latency Calculation
            submit_time = self.order_timestamps.pop(order_id, None)
            latency_ms = None
            if submit_time:
                latency_ms = (time.time() - submit_time) * 1000.0
                self.latencies.append(latency_ms)
                logger.info(
                    "[OMS Telemetry] Exec Latency: %.1fms for %s fill of %s shares (OrderID: %s)",
                    latency_ms,
                    symbol,
                    quantity,
                    order_id,
                )

            # 2. Slippage Calculation
            # BUY: Actual price - Target price (positive = worse price)
            # SELL: Target price - Actual price (positive = worse price)
            slippage = 0.0
            if action.upper() in ("BUY", "BOT"):
                slippage = fill_price - target_price
            else:
                slippage = target_price - fill_price

            slippage_pct = (slippage / target_price) * 100.0 if target_price > 0 else 0.0
            self.slippages.append(slippage)
            self.slippages_pct.append(slippage_pct)

            logger.info(
                "[OMS Telemetry] Exec Slippage: $%.4f (%.4f%%) on %s %s @ $%.2f (Target: $%.2f)",
                slippage,
                slippage_pct,
                action,
                symbol,
                fill_price,
                target_price,
            )

            # 3. Save realized trade records
            self.trade_results.append({
                "timestamp": time.time(),
                "order_id": order_id,
                "symbol": symbol.upper(),
                "action": action.upper(),
                "quantity": quantity,
                "fill_price": fill_price,
                "target_price": target_price,
                "latency_ms": latency_ms,
                "slippage": slippage,
                "slippage_pct": slippage_pct,
            })
            self._save_metrics()

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Compute structured rolling performance summary metrics."""
        import numpy as np

        avg_latency = float(np.mean(self.latencies)) if self.latencies else 0.0
        p95_latency = float(np.percentile(self.latencies, 95)) if self.latencies else 0.0
        p99_latency = float(np.percentile(self.latencies, 99)) if self.latencies else 0.0

        avg_slippage = float(np.mean(self.slippages)) if self.slippages else 0.0
        avg_slippage_pct = float(np.mean(self.slippages_pct)) if self.slippages_pct else 0.0

        # PnL / win rate calculations from completed trades
        total_trades = len(self.trade_results)
        realized_pnls = [
            t.get("realized_pnl")
            for t in self.trade_results
            if t.get("realized_pnl") is not None
        ]
        
        total_pnl = float(sum(realized_pnls)) if realized_pnls else 0.0
        winners = [p for p in realized_pnls if p > 0]
        losers = [p for p in realized_pnls if p < 0]
        
        win_rate = (len(winners) / len(realized_pnls)) * 100.0 if realized_pnls else 0.0
        profit_factor = (
            sum(winners) / abs(sum(losers))
            if losers and sum(winners) > 0
            else (1.0 if not losers and winners else 0.0)
        )

        return {
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "p99_latency_ms": round(p99_latency, 2),
            "avg_slippage_usd": round(avg_slippage, 4),
            "avg_slippage_pct": round(avg_slippage_pct, 4),
            "total_trades_counted": total_trades,
            "realized_win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "net_realized_pnl_usd": round(total_pnl, 2),
        }

    def reset_metrics(self) -> None:
        """Clear all metrics in memory and on disk."""
        with self.lock:
            self.order_timestamps = {}
            self.latencies = []
            self.slippages = []
            self.slippages_pct = []
            self.trade_results = []
            self._save_metrics()
        logger.info("Cleared all metrics statistics.")
