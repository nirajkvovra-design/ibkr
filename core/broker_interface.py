from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Sequence

from .models import AccountSnapshot, OrderRequest, OrderStatusModel, Position, BrokerResponse


class BrokerConnection(ABC):
    """Abstract broker connection interface."""

    @abstractmethod
    def connect(self, retry: bool = True, timeout: float = 10.0) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def refresh_account_data(self) -> None:
        pass

    @abstractmethod
    def place_order(self, request: OrderRequest) -> Optional[int]:
        """Submit a new order request to the broker.

        Returns the broker-assigned order ID on success, or None when the order
        could not be accepted.
        """
        pass

    @abstractmethod
    def place_order_with_confirmation(
        self,
        request: OrderRequest,
        timeout: Optional[float] = None,
        retry: Optional[int] = None,
        fallback_to_market: Optional[bool] = None,
    ) -> Optional[int]:
        """Submit an order and wait until it is confirmed/filled.

        Implementations should retry the order if confirmation fails, and may
        optionally fallback to a market order when a limit order does not fill.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: int) -> None:
        pass

    @abstractmethod
    def cancel_stale_orders(self, timeout: Optional[float] = None) -> None:
        pass

    @abstractmethod
    def get_order_status(self, order_id: int) -> Optional[OrderStatusModel]:
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        pass

    @abstractmethod
    def get_account_value(self) -> float:
        pass

    @abstractmethod
    def get_cash(self) -> float:
        pass

    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        pass

    @abstractmethod
    def get_available_funds_for_buys(self) -> float:
        pass

    @abstractmethod
    def has_active_order(self, symbol: str, action: Optional[str] = None) -> bool:
        pass

    @abstractmethod
    def has_pending_orders(self) -> bool:
        pass

    @abstractmethod
    def wait_for_pending_orders(self, timeout: Optional[float] = None) -> bool:
        pass
