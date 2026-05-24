import time
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.common import BarData
import config
from utils import get_logger, send_alert

logger = get_logger(__name__)

class IBWrapper(EWrapper):
    """Wrapper for Interactive Brokers API"""
    
    def __init__(self):
        super().__init__()
        self.next_order_id = None
        self.positions = {}
        self.account_value = 0
        self.portfolio_value = 0
        self.cash = 0
        self.available_funds = 0
        self.buying_power = 0
        self.settled_cash = 0
        self.account_summary = {}
        self.market_data = {}
        self.order_status = {}
        self.pending_orders = {}
        
    def nextValidId(self, orderId):
        """Called when next valid order ID is received"""
        self.next_order_id = orderId
        logger.info(f"Next Valid Order ID: {orderId}")
        
    def error(self, reqId, errorCode, errorString):
        """Handle API errors"""
        # IB sends many informational codes through error(); avoid treating them as failures.
        info_codes = {2104, 2106, 2158, 1102, 2119, 399}
        warning_codes = {2103, 2105, 2157, 2108, 1100, 1101}
        if errorCode in info_codes:
            logger.info(f"IB {errorCode}: {errorString} (Request: {reqId})")
        elif errorCode in warning_codes:
            logger.warning(f"IB {errorCode}: {errorString} (Request: {reqId})")
        else:
            logger.error(f"Error {errorCode}: {errorString} (Request: {reqId})")
            send_alert(
                f"IB error {errorCode}: {errorString}",
                level="ERROR",
                details={"reqId": reqId, "errorCode": errorCode, "errorString": errorString},
            )
        
    def managedAccounts(self, accountsList):
        """Called with list of managed accounts"""
        accounts = accountsList.split(',')
        logger.info(f"Managed Accounts: {accounts}")
        if config.IB_ACCOUNT == "":
            config.IB_ACCOUNT = accounts[0]
            
    def accountSummary(self, reqId, account, tag, value, currency):
        """Called with account summary data"""
        if currency and currency not in {"USD", "BASE"}:
            return
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return

        self.account_summary[tag] = numeric_value
        if tag == "TotalCashValue":
            self.cash = numeric_value
        elif tag == "NetLiquidation":
            self.account_value = numeric_value
        elif tag == "PortfolioValue":
            self.portfolio_value = numeric_value
        elif tag == "GrossPositionValue":
            self.portfolio_value = numeric_value
        elif tag == "AvailableFunds":
            self.available_funds = numeric_value
        elif tag == "BuyingPower":
            self.buying_power = numeric_value
        elif tag == "SettledCash":
            self.settled_cash = numeric_value
            
    def position(self, account, contract, position, avgCost):
        """Called with position data"""
        symbol = contract.symbol
        self.positions[symbol] = {
            'quantity': position,
            'avg_cost': avgCost,
            'account': account
        }
        logger.debug(f"Position: {symbol} - Qty: {position}, Avg Cost: ${avgCost}")
        
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Called with order status updates"""
        self.order_status[orderId] = {
            'status': status,
            'filled': filled,
            'remaining': remaining,
            'avg_fill_price': avgFillPrice
        }
        logger.info(f"Order {orderId}: {status} - Filled: {filled}, Remaining: {remaining}, Avg Price: ${avgFillPrice}")
        if config.PAPER_TRADING:
            pending = self.pending_orders.get(orderId, {})
            try:
                from paper_journal import record_order_status
                record_order_status(
                    orderId,
                    status,
                    filled,
                    avgFillPrice,
                    symbol=pending.get("symbol"),
                )
            except Exception as exc:
                logger.debug(f"Paper journal order_status skipped: {exc}")
        
    def execDetails(self, reqId, contract, execution):
        """Called when trade execution details are received"""
        logger.info(f"Trade Executed: {contract.symbol} - Qty: {execution.shares}, Price: ${execution.price}")
        if config.PAPER_TRADING:
            pending = self.pending_orders.get(execution.orderId, {})
            try:
                from paper_journal import record_execution
                record_execution(
                    contract.symbol,
                    float(execution.shares),
                    float(execution.price),
                    side=pending.get("action"),
                    order_id=execution.orderId,
                    entry_price=pending.get("entry_price"),
                    note=pending.get("note"),
                )
            except Exception as exc:
                logger.debug(f"Paper journal execution skipped: {exc}")
        
    def tickPrice(self, reqId, tickType, price, attrib):
        """Called with tick price data"""
        from ibapi.ticktype import TickType
        if tickType == TickType.LAST:
            self.market_data[reqId] = price
            
    def contractDetails(self, reqId, contractDetails):
        """Called with contract details"""
        logger.debug(f"Contract Details: {contractDetails.contract.symbol}")


class IBClient(EClient):
    """Client for Interactive Brokers API"""
    
    def __init__(self, wrapper):
        super().__init__(wrapper)
        self.wrapper = wrapper
        

class InteractiveBrokersConnection:
    """Main connection manager for Interactive Brokers"""
    
    def __init__(self):
        self.wrapper = IBWrapper()
        self.client = IBClient(self.wrapper)
        self.connected = False
        self.connection_thread = None
        
    def connect(self, retry=True):
        """Connect to Interactive Brokers TWS"""
        attempts = 0
        max_attempts = config.RECONNECT_ATTEMPTS if retry else 1
        
        while attempts < max_attempts:
            try:
                logger.info(f"Connecting to IB on {config.IB_HOST}:{config.IB_PORT}...")
                self.client.connect(config.IB_HOST, config.IB_PORT, config.IB_CLIENTID)
                
                # Start API thread
                self.connection_thread = threading.Thread(target=self._run_loop, daemon=True)
                self.connection_thread.start()
                
                # Wait for connection confirmation
                for _ in range(50):  # Wait up to 5 seconds
                    if self.wrapper.next_order_id is not None:
                        self.connected = True
                        logger.info("Successfully connected to Interactive Brokers")
                        self._request_account_data()
                        return True
                    time.sleep(0.1)
                    
                logger.warning(f"Connection attempt {attempts + 1} failed")
                send_alert(
                    "Automated alert: initial IB connection attempt failed, retrying.",
                    level="WARNING",
                    details={"host": config.IB_HOST, "port": config.IB_PORT, "client_id": config.IB_CLIENTID, "attempt": attempts + 1},
                )
                self.client.disconnect()
                attempts += 1
                
                if attempts < max_attempts:
                    time.sleep(config.RECONNECT_DELAY)
                    
            except Exception as e:
                logger.error(f"Connection error: {e}")
                send_alert(
                    "Automated alert: IB connection exception encountered during connect().",
                    level="ERROR",
                    details={"host": config.IB_HOST, "port": config.IB_PORT, "client_id": config.IB_CLIENTID, "error": str(e), "attempt": attempts + 1},
                )
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(config.RECONNECT_DELAY)
                    
        logger.error("Failed to connect to Interactive Brokers after all attempts")
        send_alert(
            "Automated alert: failed to connect to Interactive Brokers after retries.",
            level="ERROR",
            details={"host": config.IB_HOST, "port": config.IB_PORT, "client_id": config.IB_CLIENTID},
        )
        return False
        
    def _run_loop(self):
        """Run the message processing loop"""
        self.client.run()
        
    def disconnect(self):
        """Disconnect from Interactive Brokers"""
        if self.connected:
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from Interactive Brokers")
            
    def _request_account_data(self):
        """Request account data"""
        tags = ",".join([
            "TotalCashValue",
            "NetLiquidation",
            "GrossPositionValue",
            "AvailableFunds",
            "BuyingPower",
            "SettledCash",
        ])
        self.client.reqAccountSummary(1, "All", tags)
        self.client.reqPositions()

    def refresh_account_data(self):
        """Refresh account value, cash, and positions from IB."""
        if not self.connected:
            return
        self.wrapper.positions = {}
        self._request_account_data()
        time.sleep(0.5)
        
    def place_order(self, symbol, action, quantity, order_type="LMT", limit_price=None, metadata=None):
        """Place an order"""
        try:
            if not self.connected:
                logger.error("Order blocked: not connected to Interactive Brokers")
                return None
            if not config.PAPER_TRADING and not config.ENABLE_LIVE_TRADING:
                logger.error("LIVE order blocked: set ENABLE_LIVE_TRADING=True only after account setup and review")
                return None
            if self.wrapper.next_order_id is None:
                logger.error("Order blocked: next valid IB order ID has not been received")
                return None
            if quantity <= 0:
                logger.error(f"Order blocked: invalid quantity {quantity}")
                return None
            if config.USE_LIMIT_ORDERS_ONLY and order_type != "LMT":
                logger.error("Order blocked: market orders are disabled by USE_LIMIT_ORDERS_ONLY")
                return None
            if order_type == "LMT" and not limit_price:
                logger.error("Order blocked: limit order requires limit_price")
                return None

            contract = Contract()
            contract.symbol = symbol.upper()
            
            # Route cryptocurrency and futures tickers dynamically with future-proof overrides
            import os
            crypto_list = getattr(config, "CRYPTO_SYMBOLS", ["BTC", "ETH", "LTC", "BCH"])
            futures_list = getattr(config, "FUTURE_SYMBOLS", ["ES", "NQ", "YM", "CL", "GC"])
            
            clean_sym = symbol.upper().replace("-USD", "").replace("=F", "")
            is_crypto = symbol.upper() in crypto_list or symbol.upper().endswith("-USD") or os.getenv(f"CRYPTO_EXCHANGE_{clean_sym}") is not None
            is_future = symbol.upper() in futures_list or symbol.upper().endswith("=F") or os.getenv(f"FUTURE_EXCHANGE_{clean_sym}") is not None
            
            # Update contract symbol to clean symbol (without suffixes) for TWS API compatibility
            contract.symbol = clean_sym
            
            if is_crypto:
                contract.secType = "CRYPTO"
                contract.exchange = os.getenv(f"CRYPTO_EXCHANGE_{clean_sym}", "PAXOS")
            elif is_future:
                contract.secType = "FUT"
                exchanges = getattr(config, "FUTURE_EXCHANGES", {})
                contract.exchange = os.getenv(f"FUTURE_EXCHANGE_{clean_sym}", exchanges.get(clean_sym, "CME"))
                
                from utils import get_front_month_future
                contract.lastTradeDateOrContractMonth = get_front_month_future(clean_sym)
                
                multipliers = getattr(config, "FUTURE_MULTIPLIERS", {})
                contract.multiplier = str(os.getenv(f"FUTURE_MULTIPLIER_{clean_sym}", multipliers.get(clean_sym, "")))
            else:
                contract.secType = "STK"
                contract.exchange = "SMART"
                
            contract.currency = "USD"
            
            order = Order()
            order.action = action  # "BUY" or "SELL"
            order.totalQuantity = quantity
            order.orderType = order_type
            order.transmit = True
            order.outsideRth = False
            order.tif = "DAY"
            order.eTradeOnly = False
            order.firmQuoteOnly = False
            if order_type == "LMT" and limit_price:
                order.lmtPrice = limit_price
            # Support stop orders: use auxPrice for the stop trigger
            if order_type in ("STP", "STP LMT") and limit_price:
                try:
                    order.auxPrice = limit_price
                except Exception:
                    # auxPrice may not exist on some ibapi versions; ignore if unavailable
                    pass
                
            order_id = self.wrapper.next_order_id
            self.wrapper.next_order_id += 1

            self.client.placeOrder(order_id, contract, order)
            pending = {
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "order_type": order_type,
                "created_at": time.time(),
            }
            if limit_price is not None:
                pending["limit_price"] = limit_price
            if metadata is not None:
                pending.update(metadata)
            self.wrapper.pending_orders[order_id] = pending
            logger.info(f"Order placed: {action} {quantity} {symbol} at {limit_price if limit_price else 'market'}")
            if config.PAPER_TRADING:
                try:
                    from paper_journal import record_order_submitted
                    record_order_submitted(symbol, action, quantity, limit_price, order_id)
                except Exception as exc:
                    logger.debug(f"Paper journal order_submitted skipped: {exc}")
            return order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
            
    def cancel_order(self, order_id):
        """Cancel an order"""
        try:
            self.client.cancelOrder(order_id)
            logger.info(f"Order {order_id} cancelled")
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            
    def get_order_status(self, order_id):
        """Return the latest known IB status for an order."""
        return self.wrapper.order_status.get(order_id, {})

    def wait_for_order_status(self, order_id, target_statuses, timeout=None):
        """Wait until an order reaches one of the provided statuses."""
        timeout = timeout if timeout is not None else config.ORDER_CONFIRMATION_TIMEOUT
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_order_status(order_id).get("status")
            if status in target_statuses:
                return status
            time.sleep(config.RESTART_POLL_INTERVAL)
        return self.get_order_status(order_id).get("status")

    def wait_for_order_filled(self, order_id, timeout=None):
        """Wait for an order to be filled or terminalized."""
        status = self.wait_for_order_status(
            order_id,
            {"Filled", "Cancelled", "Inactive", "ApiCancelled"},
            timeout=timeout,
        )
        return status == "Filled"

    def cancel_stale_orders(self, timeout=None):
        """Cancel any tracked working orders older than the provided timeout."""
        timeout = timeout if timeout is not None else config.STALE_ORDER_TIMEOUT
        now = time.time()
        for order_id, metadata in list(self.wrapper.pending_orders.items()):
            if metadata.get("created_at") is None:
                continue
            status = self.get_order_status(order_id).get("status", "")
            if status in {"Filled", "Cancelled", "Inactive", "ApiCancelled"}:
                continue
            age = now - metadata["created_at"]
            if age > timeout:
                logger.warning(f"Cancelling stale order {order_id} after {int(age)}s")
                self.cancel_order(order_id)
                if config.PAPER_TRADING:
                    try:
                        from paper_journal import record_order_status
                        record_order_status(order_id, "Cancelled", 0.0, 0.0, symbol=metadata.get("symbol"))
                    except Exception as exc:
                        logger.debug(f"Paper journal stale cancel skipped: {exc}")

    def place_order_with_confirmation(
        self,
        symbol,
        action,
        quantity,
        order_type="LMT",
        limit_price=None,
        metadata=None,
        timeout=None,
        retry=None,
        fallback_to_market=None,
    ):
        """Place an order and confirm it fills, optionally retrying stale or unfilled orders."""
        timeout = timeout if timeout is not None else config.ORDER_CONFIRMATION_TIMEOUT
        retry = retry if retry is not None else config.ORDER_RETRY_LIMIT
        fallback_to_market = fallback_to_market if fallback_to_market is not None else config.ORDER_RETRY_FALLBACK_TO_MARKET

        order_id = self.place_order(symbol, action, quantity, order_type, limit_price, metadata)
        if not order_id:
            return None

        if self.wait_for_order_filled(order_id, timeout=timeout):
            return order_id

        logger.warning(f"Order {order_id} did not fill within {timeout}s; retrying...")
        self.cancel_order(order_id)

        if retry <= 0:
            return None

        if fallback_to_market and order_type == "LMT" and not config.USE_LIMIT_ORDERS_ONLY:
            logger.info(f"Retrying order {order_id} as market order after limit timeout")
            return self.place_order_with_confirmation(
                symbol,
                action,
                quantity,
                order_type="MKT",
                limit_price=None,
                metadata=metadata,
                timeout=timeout,
                retry=retry - 1,
                fallback_to_market=False,
            )

        return self.place_order_with_confirmation(
            symbol,
            action,
            quantity,
            order_type=order_type,
            limit_price=limit_price,
            metadata=metadata,
            timeout=timeout,
            retry=retry - 1,
            fallback_to_market=fallback_to_market,
        )
    
    def get_account_value(self):
        """Get current account value"""
        return self.wrapper.account_value
        
    def get_positions(self):
        """Get current positions with non-zero quantity (IB may report closed lots at qty 0)."""
        return {
            symbol: info
            for symbol, info in self.wrapper.positions.items()
            if info.get("quantity", 0) != 0
        }

    def has_pending_orders(self):
        """True if any tracked orders are still working (not terminal)."""
        terminal = {
            "Filled",
            "Cancelled",
            "Inactive",
            "ApiCancelled",
            "PendingCancel",
        }
        for info in self.wrapper.order_status.values():
            status = info.get("status", "")
            remaining = info.get("remaining", 0)
            if status not in terminal and remaining and float(remaining) > 0:
                return True
            if status in {"Submitted", "PreSubmitted", "PendingSubmit"}:
                return True
        return False

    def has_active_order(self, symbol, action=None):
        """Check if there is an active (non-terminal) order for a specific symbol."""
        terminal = {
            "Filled",
            "Cancelled",
            "Inactive",
            "ApiCancelled",
            "PendingCancel",
        }
        symbol = symbol.upper()
        if action:
            action = action.upper()

        for order_id, pending_info in list(self.wrapper.pending_orders.items()):
            if pending_info.get("symbol", "").upper() != symbol:
                continue
            if action and pending_info.get("action", "").upper() != action:
                continue
            
            # Check the latest status from order_status
            status_info = self.wrapper.order_status.get(order_id, {})
            status = status_info.get("status")
            
            # If status is in terminal set, we skip
            if status in terminal:
                continue
                
            # If the status lists remaining quantity and it is 0, we can also consider it terminal
            remaining = status_info.get("remaining")
            if remaining is not None and float(remaining) == 0:
                continue
                
            # Otherwise, since it is in pending_orders and not terminal in order_status, it is active
            return True
        return False


    def wait_for_pending_orders(self, timeout=None):
        """Block until working orders complete or timeout (seconds)."""
        timeout = timeout if timeout is not None else config.RESTART_SHUTDOWN_TIMEOUT
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.has_pending_orders():
                return True
            time.sleep(config.RESTART_POLL_INTERVAL)
        return not self.has_pending_orders()
        
    def get_cash(self):
        """Get available cash"""
        return self.wrapper.cash

    def get_available_funds_for_buys(self):
        """Return funds available for opening new stock positions based on configured funding source."""
        source = getattr(config, "FUNDING_SOURCE", "CONSERVATIVE").upper()
        
        cash = self.wrapper.cash if self.wrapper.cash > 0 else 0
        avail = self.wrapper.available_funds if self.wrapper.available_funds > 0 else 0
        power = self.wrapper.buying_power if self.wrapper.buying_power > 0 else 0
        settled = self.wrapper.settled_cash if self.wrapper.settled_cash > 0 else 0

        if source == "BUYING_POWER" and power > 0:
            return power
        elif source == "MARGIN" and avail > 0:
            return avail
        else:
            # CONSERVATIVE
            candidates = [v for v in [cash, avail, power] if v > 0]
            if config.REQUIRE_SETTLED_CASH_FOR_BUYS and settled > 0:
                candidates.append(settled)
            return max(0, min(candidates)) if candidates else 0

    def get_account_snapshot(self):
        """Get account values used by risk and sizing checks."""
        return {
            'net_liquidation': self.wrapper.account_value,
            'total_cash': self.wrapper.cash,
            'available_funds': self.wrapper.available_funds,
            'buying_power': self.wrapper.buying_power,
            'settled_cash': self.wrapper.settled_cash,
            'funds_for_new_buys': self.get_available_funds_for_buys(),
        }
