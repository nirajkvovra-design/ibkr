from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from ibapi.client import EClient
from ibapi.wrapper import EWrapper

import config
from core.broker_interface import BrokerConnection
from core.models import (
    AccountSnapshot,
    OrderRequest,
    OrderStatusModel,
    BrokerResponse,
    OrderType,
    Position,
)
from utils import get_front_month_future, get_logger, send_alert

logger = get_logger(__name__)


class IBWrapper(EWrapper):
    """Interactive Brokers wrapper for event callbacks."""

    def __init__(self):
        super().__init__()
        self.next_order_id: Optional[int] = None
        self.positions: Dict[str, Dict[str, float]] = {}
        self.account_summary: Dict[str, float] = {}
        self.order_status: Dict[int, OrderStatusModel] = {}
        self.pending_orders: Dict[int, Dict[str, object]] = {}
        self.market_data: Dict[int, float] = {}
        self.connected: bool = False
        self.last_heartbeat: float = time.time()
        
        # Level 2 orderbook state
        self.depth_symbols: Dict[int, str] = {}
        self.order_books: Dict[str, Any] = {}
        self.event_engine: Optional[Any] = None

    def nextValidId(self, orderId: int) -> None:
        self.next_order_id = orderId
        self.connected = True
        logger.info("Next valid order ID received: %s", orderId)

    def error(self, reqId: int, errorCode: int, errorString: str) -> None:
        info_codes = {2104, 2106, 2158, 1102, 2119, 399}
        warning_codes = {2103, 2105, 2157, 2108, 1100, 1101}
        if errorCode in info_codes:
            logger.info("IB %s: %s (req=%s)", errorCode, errorString, reqId)
        elif errorCode in warning_codes:
            logger.warning("IB %s: %s (req=%s)", errorCode, errorString, reqId)
        else:
            logger.error("IB error %s: %s (req=%s)", errorCode, errorString, reqId)
            send_alert(
                f"IB error {errorCode}: {errorString}",
                level="ERROR",
                details={"reqId": reqId, "errorCode": errorCode, "message": errorString},
            )

    def managedAccounts(self, accountsList: str) -> None:
        accounts = accountsList.split(',')
        logger.info("Managed accounts: %s", accounts)
        if not config.IB_ACCOUNT and accounts:
            config.IB_ACCOUNT = accounts[0]

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str) -> None:
        if currency and currency not in {"USD", "BASE"}:
            return
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return

        self.account_summary[tag] = numeric_value
        if tag == "TotalCashValue":
            self.account_summary["cash"] = numeric_value
        elif tag == "NetLiquidation":
            self.account_summary["net_liquidation"] = numeric_value
        elif tag == "PortfolioValue":
            self.account_summary["portfolio_value"] = numeric_value
        elif tag == "AvailableFunds":
            self.account_summary["available_funds"] = numeric_value
        elif tag == "BuyingPower":
            self.account_summary["buying_power"] = numeric_value
        elif tag == "SettledCash":
            self.account_summary["settled_cash"] = numeric_value

    def position(self, account: str, contract: Contract, position: float, avgCost: float) -> None:
        symbol = contract.symbol
        self.positions[symbol] = {
            "quantity": position,
            "avg_cost": avgCost,
            "account": account,
        }
        logger.debug("Position updated: %s qty=%s avg_cost=%s", symbol, position, avgCost)

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:
        from core.chaos_engine import ChaosEngine
        chaos = ChaosEngine()
        if chaos.enabled and chaos.should_force_partial_fill() and status == "Filled":
            original_qty = filled + remaining
            filled = chaos.force_partial_quantity(original_qty)
            remaining = original_qty - filled
            status = "PartiallyFilled"
            logger.warning("[Chaos Sentry] Overriding status to PartiallyFilled: filled=%.2f remaining=%.2f", filled, remaining)
        status_model = OrderStatusModel(
            order_id=orderId,
            status=status,
            filled=filled,
            remaining=remaining,
            avg_fill_price=avgFillPrice,
            updated_at=datetime.now(timezone.utc),
            metadata=self.pending_orders.get(orderId, {}).copy(),
        )
        self.order_status[orderId] = status_model
        logger.info(
            "Order %s status=%s filled=%s remaining=%s avg_fill_price=%s",
            orderId,
            status,
            filled,
            remaining,
            avgFillPrice,
        )

    def execDetails(self, reqId: int, contract: Contract, execution) -> None:
        logger.info(
            "Execution details for %s qty=%s price=%s orderId=%s",
            contract.symbol,
            execution.shares,
            execution.price,
            execution.orderId,
        )

    def updateMktDepth(
        self,
        reqId: int,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: float,
    ) -> None:
        """EWrapper market depth callback for Level 2 rows."""
        self.last_heartbeat = time.time()  # Record heartbeat on L2 depth stream tick
        symbol = self.depth_symbols.get(reqId)
        if not symbol:
            return
        
        if symbol not in self.order_books:
            from core.order_book import LocalOrderBook
            self.order_books[symbol] = LocalOrderBook(symbol)
            
        book = self.order_books[symbol]
        book.update_level(position, operation, side, price, size)
        
        if self.event_engine:
            from core.event_engine import Event, EVENT_TICK
            self.event_engine.put(Event(EVENT_TICK, data=book.get_snapshot()))

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib) -> None:
        self.last_heartbeat = time.time()  # Record heartbeat on standard price tick callback
        from ibapi.ticktype import TickType
        if price > 0:
            self.market_data[reqId] = price

    def connectionClosed(self) -> None:
        super().connectionClosed()
        self.connected = False
        logger.warning("IB connection closed")


class IBClient(EClient):
    def __init__(self, wrapper: IBWrapper):
        super().__init__(wrapper)
        self.wrapper = wrapper


class IBBrokerConnection(BrokerConnection):
    """Interactive Brokers connection adapter implementing the broker interface."""

    def __init__(self):
        self.wrapper = IBWrapper()
        self.client = IBClient(self.wrapper)
        self.connected = False
        self.connection_thread: Optional[threading.Thread] = None
        self.order_history: Dict[int, Dict[str, Any]] = {}
        
        # Staged Rollout Safety Gate
        from core.safety_gate import SafetyGate
        self.safety_gate = SafetyGate()

    def connect(self, retry: bool = True, timeout: float = 10.0) -> bool:
        attempts = 0
        max_attempts = config.RECONNECT_ATTEMPTS if retry else 1

        while attempts < max_attempts:
            try:
                logger.info("Connecting to IB %s:%s client_id=%s", config.IB_HOST, config.IB_PORT, config.IB_CLIENTID)
                self.client.connect(config.IB_HOST, config.IB_PORT, config.IB_CLIENTID)
                self.connection_thread = threading.Thread(target=self.client.run, daemon=True)
                self.connection_thread.start()

                deadline = time.time() + timeout
                while time.time() < deadline:
                    if self.wrapper.next_order_id is not None:
                        self.connected = True
                        logger.info("Connected to Interactive Brokers")
                        self._request_account_data()
                        return True
                    time.sleep(0.1)

                logger.warning("IB connection attempt %s failed after %s seconds", attempts + 1, timeout)
                self.client.disconnect()
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(config.RECONNECT_DELAY)
            except Exception as exc:
                logger.error("IB connection exception: %s", exc)
                send_alert(
                    "IB connection exception during connect",
                    level="ERROR",
                    details={"error": str(exc), "attempt": attempts + 1},
                )
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(config.RECONNECT_DELAY)

        logger.error("Failed to connect to IB after %s attempts", max_attempts)
        return False

    def disconnect(self) -> None:
        if self.connected:
            try:
                self.client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting from IB: %s", exc)
            self.connected = False
            logger.info("Disconnected from Interactive Brokers")

    def _request_account_data(self) -> None:
        tags = ",".join(
            [
                "TotalCashValue",
                "NetLiquidation",
                "GrossPositionValue",
                "AvailableFunds",
                "BuyingPower",
                "SettledCash",
            ]
        )
        self.client.reqAccountSummary(1, "All", tags)
        self.client.reqPositions()

    def refresh_account_data(self) -> None:
        if not self.connected:
            return
        self.wrapper.positions = {}
        self._request_account_data()
        time.sleep(0.5)

    def _build_contract(self, symbol: str, request: Optional[OrderRequest] = None):
        from ib_connection import Contract

        symbol = symbol.upper()
        contract = Contract()
        contract.symbol = symbol

        # If combo legs are specified
        if request and getattr(request, 'combo_legs', None):
            contract.secType = "BAG"
            contract.exchange = "SMART"
            contract.currency = "USD"
            contract.comboLegs = []
            from ibapi.contract import ComboLeg
            for leg_model in request.combo_legs:
                leg = ComboLeg()
                leg.conId = leg_model.conId
                leg.ratio = leg_model.ratio
                leg.action = leg_model.action
                leg.exchange = leg_model.exchange
                contract.comboLegs.append(leg)
            return contract

        clean_sym = symbol.replace("-USD", "").replace("=F", "")
        crypto_list = getattr(config, "CRYPTO_SYMBOLS", ["BTC", "ETH", "LTC", "BCH"])
        futures_list = getattr(config, "FUTURE_SYMBOLS", ["ES", "NQ", "YM", "CL", "GC"])
        is_crypto = symbol in crypto_list or symbol.endswith("-USD") or os.getenv(f"CRYPTO_EXCHANGE_{clean_sym}")
        is_future = symbol in futures_list or symbol.endswith("=F") or os.getenv(f"FUTURE_EXCHANGE_{clean_sym}")

        if is_crypto:
            contract.secType = "CRYPTO"
            contract.exchange = os.getenv(f"CRYPTO_EXCHANGE_{clean_sym}", "PAXOS")
        elif is_future:
            contract.secType = "FUT"
            exchanges = getattr(config, "FUTURE_EXCHANGES", {})
            contract.exchange = os.getenv(f"FUTURE_EXCHANGE_{clean_sym}", exchanges.get(clean_sym, "CME"))
            contract.lastTradeDateOrContractMonth = get_front_month_future(clean_sym)
            multipliers = getattr(config, "FUTURE_MULTIPLIERS", {})
            contract.multiplier = str(os.getenv(f"FUTURE_MULTIPLIER_{clean_sym}", multipliers.get(clean_sym, "")))
        else:
            contract.secType = "STK"
            contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    def place_order(self, request: OrderRequest) -> Optional[int]:
        from core.chaos_engine import ChaosEngine
        chaos = ChaosEngine()
        if chaos.enabled:
            # Inject Latency Chaos
            chaos.inject_latency()
            # Inject Connection Drop Chaos
            if chaos.should_drop_socket():
                logger.error("[Chaos Sentry] Injecting connection drop on order placement!")
                self.disconnect()
                return None

        # --- SAFETY GATE INTERCEPTOR ---
        if hasattr(self, "safety_gate"):
            acc_summary = getattr(self.wrapper, "account_summary", {}) or {}
            account_val = acc_summary.get("net_liquidation", 0.0)
            if not isinstance(account_val, (int, float)):
                account_val = 10000.0
            elif account_val <= 0:
                account_val = 10000.0  # Safe fallback for sizing validation
            filtered_request, message = self.safety_gate.filter_order(request, account_val)
            if filtered_request is None:
                logger.info("[Safety Gate] Intercepted and blocked order: %s", message)
                return None
            request = filtered_request

        if not self.connected:
            logger.error("Order blocked: no IB connection")
            return None

        if not config.PAPER_TRADING and not config.ENABLE_LIVE_TRADING:
            logger.error("LIVE order blocked: ENABLE_LIVE_TRADING=False")
            return None

        if self.wrapper.next_order_id is None:
            logger.error("Order blocked: next valid order ID unavailable")
            return None

        if request.quantity <= 0:
            logger.error("Order blocked: invalid quantity %s", request.quantity)
            return None

        if config.USE_LIMIT_ORDERS_ONLY and request.order_type != OrderType.LMT:
            logger.error("Order blocked: market orders disabled by USE_LIMIT_ORDERS_ONLY")
            return None

        if request.order_type == OrderType.LMT and request.limit_price is None:
            logger.error("Order blocked: LMT order requires limit_price")
            return None

        contract = self._build_contract(request.symbol, request=request)
        from ib_connection import Order

        order = Order()
        order.action = request.action.value if hasattr(request.action, "value") else str(request.action)
        order.totalQuantity = request.quantity
        order.orderType = request.order_type.value if hasattr(request.order_type, "value") else str(request.order_type)
        order.tif = request.tif
        order.outsideRth = request.outside_rth
        order.firmQuoteOnly = request.firm_quote_only
        order.eTradeOnly = request.e_trade_only
        if request.order_type == OrderType.LMT and request.limit_price is not None:
            order.lmtPrice = float(request.limit_price)
        if request.order_type in (OrderType.STP, OrderType.STP_LMT) and request.aux_price is not None:
            try:
                order.auxPrice = float(request.aux_price)
            except Exception:
                pass

        order_id = self.wrapper.next_order_id
        self.wrapper.next_order_id += 1
        self.client.placeOrder(order_id, contract, order)

        self.wrapper.pending_orders[order_id] = {
            "symbol": request.symbol,
            "action": request.action.value if hasattr(request.action, "value") else str(request.action),
            "quantity": request.quantity,
            "order_type": request.order_type.value if hasattr(request.order_type, "value") else str(request.order_type),
            "created_at": time.time(),
            "metadata": request.metadata,
        }
        self.order_history[order_id] = {
            "request": request.model_dump(),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Order submitted %s %s %s %s @ %s (order_id=%s)",
            request.action,
            request.quantity,
            request.symbol,
            request.order_type,
            request.limit_price or "MARKET",
            order_id,
        )
        return order_id

    def place_order_with_confirmation(
        self,
        request: OrderRequest,
        timeout: Optional[float] = None,
        retry: Optional[int] = None,
        fallback_to_market: Optional[bool] = None,
    ) -> Optional[int]:
        timeout = timeout if timeout is not None else config.ORDER_CONFIRMATION_TIMEOUT
        retry = retry if retry is not None else config.ORDER_RETRY_LIMIT
        fallback_to_market = fallback_to_market if fallback_to_market is not None else config.ORDER_RETRY_FALLBACK_TO_MARKET

        order_id = self.place_order(request)
        if order_id is None:
            return None

        if self.wait_for_order_filled(order_id, timeout=timeout):
            return order_id

        logger.warning("Order %s did not fill within %ss; retrying", order_id, timeout)
        self.cancel_order(order_id)

        if retry <= 0:
            return None

        if fallback_to_market and request.order_type == OrderType.LMT and not config.USE_LIMIT_ORDERS_ONLY:
            request.order_type = OrderType.MKT
            request.limit_price = None
            logger.info("Retrying order %s as market order", order_id)
            return self.place_order_with_confirmation(request, timeout=timeout, retry=retry - 1, fallback_to_market=False)

        return self.place_order_with_confirmation(request, timeout=timeout, retry=retry - 1, fallback_to_market=fallback_to_market)

    def cancel_order(self, order_id: int) -> None:
        try:
            self.client.cancelOrder(order_id)
            logger.info("Cancelled order %s", order_id)
        except Exception as exc:
            logger.error("Error cancelling order %s: %s", order_id, exc)

    def get_order_status(self, order_id: int) -> Optional[OrderStatusModel]:
        return self.wrapper.order_status.get(order_id)

    def wait_for_order_status(self, order_id: int, target_statuses: Optional[set] = None, timeout: Optional[float] = None) -> Optional[str]:
        target_statuses = target_statuses or {"Filled", "Cancelled", "Inactive", "ApiCancelled"}
        deadline = time.time() + (timeout or config.ORDER_CONFIRMATION_TIMEOUT)
        while time.time() < deadline:
            status = self.get_order_status(order_id)
            if status and status.status in target_statuses:
                return status.status
            time.sleep(config.RESTART_POLL_INTERVAL)
        status = self.get_order_status(order_id)
        return status.status if status else None

    def wait_for_order_filled(self, order_id: int, timeout: Optional[float] = None) -> bool:
        status = self.wait_for_order_status(order_id, timeout=timeout)
        return status == "Filled"

    def cancel_stale_orders(self, timeout: Optional[float] = None) -> None:
        timeout = timeout if timeout is not None else config.STALE_ORDER_TIMEOUT
        now = time.time()
        for order_id, metadata in list(self.wrapper.pending_orders.items()):
            if metadata.get("created_at") is None:
                continue
            status = self.wrapper.order_status.get(order_id)
            if status and status.status in {"Filled", "Cancelled", "Inactive", "ApiCancelled"}:
                continue
            age = now - metadata["created_at"]
            if age > timeout:
                logger.warning("Cancelling stale order %s after %ss", order_id, int(age))
                self.cancel_order(order_id)

    def get_positions(self) -> Dict[str, Position]:
        return {
            symbol: Position(
                symbol=symbol,
                quantity=info.get("quantity", 0),
                avg_cost=info.get("avg_cost", 0.0),
                account=info.get("account"),
            )
            for symbol, info in self.wrapper.positions.items()
            if info.get("quantity", 0) != 0
        }

    def has_active_order(self, symbol: str, action: Optional[str] = None) -> bool:
        terminal = {"Filled", "Cancelled", "Inactive", "ApiCancelled", "PendingCancel"}
        symbol = symbol.upper()
        action_upper = action.upper() if action else None

        for order_id, pending_info in list(self.wrapper.pending_orders.items()):
            if pending_info.get("symbol", "").upper() != symbol:
                continue
            if action_upper and pending_info.get("action", "").upper() != action_upper:
                continue
            status_model = self.wrapper.order_status.get(order_id)
            if status_model and status_model.status in terminal:
                continue
            if status_model and status_model.remaining == 0:
                continue
            return True
        return False

    def has_pending_orders(self) -> bool:
        terminal = {"Filled", "Cancelled", "Inactive", "ApiCancelled", "PendingCancel"}
        for status in self.wrapper.order_status.values():
            if status.status not in terminal and status.remaining > 0:
                return True
            if status.status in {"Submitted", "PreSubmitted", "PendingSubmit"}:
                return True
        return False

    def wait_for_pending_orders(self, timeout: Optional[float] = None) -> bool:
        timeout = timeout if timeout is not None else config.RESTART_SHUTDOWN_TIMEOUT
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.has_pending_orders():
                return True
            time.sleep(config.RESTART_POLL_INTERVAL)
        return not self.has_pending_orders()

    def _account_summary_value(self, key: str, default: float = 0.0) -> float:
        if hasattr(self.wrapper, "account_summary") and isinstance(self.wrapper.account_summary, dict):
            value = self.wrapper.account_summary.get(key, None)
        else:
            value = None

        if value is None:
            value = getattr(self.wrapper, key, default)

        try:
            return float(value)
        except Exception:
            return default

    def get_cash(self) -> float:
        sim = getattr(config, "SIMULATE_PORTFOLIO_VALUE", 0.0)
        if sim > 0.0:
            return sim
        return self._account_summary_value("cash", 0.0)

    def get_available_funds_for_buys(self) -> float:
        sim = getattr(config, "SIMULATE_PORTFOLIO_VALUE", 0.0)
        if sim > 0.0:
            return sim
        source = getattr(config, "FUNDING_SOURCE", "CONSERVATIVE").upper()
        cash = self._account_summary_value("cash", 0.0)
        available_funds = self._account_summary_value("available_funds", 0.0)
        buying_power = self._account_summary_value("buying_power", 0.0)
        settled_cash = self._account_summary_value("settled_cash", 0.0)

        if source == "BUYING_POWER" and buying_power > 0:
            return buying_power
        if source == "MARGIN" and available_funds > 0:
            return available_funds

        if config.REQUIRE_SETTLED_CASH_FOR_BUYS and settled_cash > 0:
            candidates = [v for v in [cash, available_funds, buying_power, settled_cash] if v > 0]
            return min(candidates) if candidates else 0.0

        if cash > 0:
            return cash

        candidates = [v for v in [available_funds, buying_power] if v > 0]
        return min(candidates) if candidates else 0.0

    def get_account_value(self) -> float:
        sim = getattr(config, "SIMULATE_PORTFOLIO_VALUE", 0.0)
        if sim > 0.0:
            return sim
        return self._account_summary_value("net_liquidation", 0.0)

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            net_liquidation=self.get_account_value(),
            total_cash=self._account_summary_value("cash", 0.0),
            available_funds=self._account_summary_value("available_funds", 0.0),
            buying_power=self._account_summary_value("buying_power", 0.0),
            settled_cash=self._account_summary_value("settled_cash", 0.0),
            funds_for_new_buys=self.get_available_funds_for_buys(),
            metadata={"account_summary": getattr(self.wrapper, "account_summary", {}).copy() if hasattr(self.wrapper, "account_summary") and isinstance(self.wrapper.account_summary, dict) else {}},
        )

    def set_event_engine(self, event_engine: Any) -> None:
        """Register the global async EventEngine for dispatching callbacks."""
        self.wrapper.event_engine = event_engine

    def subscribe_market_depth(self, symbol: str, req_id: int) -> None:
        """Subscribe to Level 2 market depth updates via TWS."""
        if not self.connected:
            return
        
        contract = self._build_contract(symbol)
        self.wrapper.depth_symbols[req_id] = symbol.upper()
        # Request up to 10 rows of SMART market depth
        self.client.reqMktDepth(req_id, contract, 10, False, [])
        logger.info("[OMS L2] Requested market depth for %s (ReqID: %s)", symbol.upper(), req_id)

    def unsubscribe_market_depth(self, req_id: int) -> None:
        """Cancel Level 2 market depth subscription."""
        if not self.connected:
            return
            
        self.client.cancelMktDepth(req_id, False)
        symbol = self.wrapper.depth_symbols.pop(req_id, None)
        if symbol:
            self.wrapper.order_books.pop(symbol, None)
        logger.info("[OMS L2] Cancelled market depth subscription for ReqID: %s", req_id)
