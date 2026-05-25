from __future__ import annotations

from typing import Optional, List
import asyncio

from core.broker_interface import BrokerConnection
from core.models import OrderRequest, BrokerResponse
from utils import get_logger

logger = get_logger(__name__)


class OrderManager:
    """High-level order management layer for execution quality and recovery."""

    def __init__(self, broker: BrokerConnection):
        self.broker = broker
        self.submitted_orders = {}

    def submit_order(self, request: OrderRequest) -> Optional[int]:
        order_id = self.broker.place_order(request)
        if order_id is None:
            logger.warning("OrderManager rejected order request for %s", request.symbol)
            return None

        self.submitted_orders[order_id] = {
            "request": request,
            "submitted_at": request.metadata.get("submitted_at"),
        }
        logger.debug("OrderManager submitted order %s for %s", order_id, request.symbol)
        return order_id

    def submit_order_with_confirmation(
        self,
        request: OrderRequest,
        timeout: Optional[float] = None,
        retry: Optional[int] = None,
        fallback_to_market: Optional[bool] = None,
    ) -> Optional[int]:
        order_id = self.broker.place_order_with_confirmation(request, timeout=timeout, retry=retry, fallback_to_market=fallback_to_market)
        if order_id is None:
            logger.warning("OrderManager failed to confirm order for %s", request.symbol)
            return None
        return order_id

    def cancel_stale_orders(self, timeout: Optional[float] = None) -> None:
        self.broker.cancel_stale_orders(timeout)

    def get_order_status(self, order_id: int) -> Optional[BrokerResponse]:
        status = self.broker.get_order_status(order_id)
        if status is None:
            return None
        return BrokerResponse(success=True, order_id=order_id, status=status.status, metadata=status.metadata)

    def get_active_orders(self) -> dict:
        return {oid: info for oid, info in self.submitted_orders.items() if self.broker.has_active_order(info["request"].symbol)}

    async def execute_twap(
        self,
        request: OrderRequest,
        duration_seconds: float,
        interval_seconds: float
    ) -> List[int]:
        """
        Execute an order request using a Time-Weighted Average Price (TWAP) algorithm.
        Slices the total quantity equally across intervals.
        """
        logger.info(
            "[TWAP] Beginning TWAP execution for %s. Total Qty: %s, Duration: %ss, Interval: %ss",
            request.symbol, request.quantity, duration_seconds, interval_seconds
        )
        num_slices = max(1, round(duration_seconds / interval_seconds))
        slice_qty = round(request.quantity / num_slices, 4)
        if slice_qty <= 0:
            slice_qty = request.quantity
            num_slices = 1

        filled_order_ids = []
        for i in range(num_slices):
            # Calculate remaining quantity for final slice to avoid rounding errors
            if i == num_slices - 1:
                current_qty = round(request.quantity - sum([slice_qty for _ in range(num_slices - 1)]), 4)
                if current_qty <= 0:
                    break
            else:
                current_qty = slice_qty

            logger.info("[TWAP] Submitting slice %s/%s for %s shares of %s", i + 1, num_slices, current_qty, request.symbol)
            child_request = request.model_copy(update={"quantity": current_qty})
            
            # Place order asynchronously with confirmation
            order_id = await asyncio.to_thread(
                self.submit_order_with_confirmation,
                child_request,
                timeout=interval_seconds,
                retry=0,
                fallback_to_market=False
            )
            
            if order_id is not None:
                filled_order_ids.append(order_id)
                status = self.get_order_status(order_id)
                logger.info(
                    "[TWAP] Slice %s/%s submitted. Order ID: %s. Status: %s",
                    i + 1, num_slices, order_id, status.status if status else "Unknown"
                )
            else:
                logger.warning("[TWAP] Slice %s/%s failed to submit", i + 1, num_slices)

            if i < num_slices - 1:
                await asyncio.sleep(interval_seconds)

        logger.info("[TWAP] Finished TWAP execution for %s. Submitted order IDs: %s", request.symbol, filled_order_ids)
        return filled_order_ids

    async def execute_vwap(
        self,
        request: OrderRequest,
        duration_seconds: float,
        interval_seconds: float
    ) -> List[int]:
        """
        Execute an order request using a Volume-Weighted Average Price (VWAP) algorithm.
        Slices the total quantity according to a standard U-shaped institutional intraday volume curve.
        """
        logger.info(
            "[VWAP] Beginning VWAP execution for %s. Total Qty: %s, Duration: %ss, Interval: %ss",
            request.symbol, request.quantity, duration_seconds, interval_seconds
        )
        num_slices = max(1, round(duration_seconds / interval_seconds))
        if num_slices == 1:
            return await self.execute_twap(request, duration_seconds, interval_seconds)

        # Generate U-shaped weights: f(t) = (t-0.5)^2 + 0.1 normalized
        t_coords = [float(i) / (num_slices - 1) for i in range(num_slices)]
        unnormalized_weights = [(t - 0.5) ** 2 + 0.1 for t in t_coords]
        total_sum = sum(unnormalized_weights)
        weights = [w / total_sum for w in unnormalized_weights]

        filled_order_ids = []
        for i in range(num_slices):
            # Quantity for this slice
            if i == num_slices - 1:
                # Avoid rounding residuals
                current_qty = round(request.quantity - sum([round(w * request.quantity, 4) for w in weights[:-1]]), 4)
                if current_qty <= 0:
                    break
            else:
                current_qty = round(weights[i] * request.quantity, 4)
                if current_qty <= 0:
                    current_qty = 1e-4  # Minimum float quantity

            logger.info(
                "[VWAP] Submitting U-shaped slice %s/%s for %s shares of %s (weight: %.1f%%)",
                i + 1, num_slices, current_qty, request.symbol, weights[i] * 100.0
            )
            child_request = request.model_copy(update={"quantity": current_qty})
            
            order_id = await asyncio.to_thread(
                self.submit_order_with_confirmation,
                child_request,
                timeout=interval_seconds,
                retry=0,
                fallback_to_market=False
            )
            
            if order_id is not None:
                filled_order_ids.append(order_id)
                status = self.get_order_status(order_id)
                logger.info(
                    "[VWAP] Slice %s/%s submitted. Order ID: %s. Status: %s",
                    i + 1, num_slices, order_id, status.status if status else "Unknown"
                )
            else:
                logger.warning("[VWAP] Slice %s/%s failed to submit", i + 1, num_slices)

            if i < num_slices - 1:
                await asyncio.sleep(interval_seconds)

        logger.info("[VWAP] Finished VWAP execution for %s. Submitted order IDs: %s", request.symbol, filled_order_ids)
        return filled_order_ids

