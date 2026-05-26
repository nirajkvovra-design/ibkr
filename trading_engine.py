import os
import schedule
import time
import threading
from datetime import datetime
import pytz
import config
from utils import get_logger, is_market_open, format_trade_log, setup_logging, send_alert, update_health_status
from ib_connection import InteractiveBrokersConnection
from strategies import MomentumStrategy, GridTradingStrategy, MachineLearningStrategy, PairsTradingStrategy, VolatilityBreakoutStrategy, IPOBreakoutStrategy, CorrelatedLaggardStrategy
from risk_manager import RiskManager
from data_fetcher import DataFetcher
from stock_screener import StockScreener
from trade_research import TradeResearch
from core.order_manager import OrderManager
from core.models import OrderRequest, OrderSide, OrderType
from core.market_data import MarketDataEngine
import daily_positions
import asyncio
from core.event_engine import EventEngine, Event, EVENT_HEALTH, EVENT_RISK, EVENT_FILL, EVENT_SIGNAL, EVENT_ORDER, EVENT_TICK
from core.metrics_collector import MetricsCollector
from engine_control import (
    clear_pid,
    clear_restart_request,
    is_restart_requested,
    is_shutting_down,
    set_shutting_down,
    write_pid,
)

logger = get_logger(__name__)

class TradingEngine:
    """Main automated trading engine"""
    
    def __init__(self):
        setup_logging()
        self.ib_connection = InteractiveBrokersConnection()
        self.order_manager = OrderManager(self.ib_connection)
        self.risk_manager = RiskManager(self.ib_connection)
        self.data_fetcher = DataFetcher()
        self.market_data = MarketDataEngine(self.data_fetcher)
        self.stock_screener = StockScreener()
        self.research = TradeResearch(self.data_fetcher)
        
        # Institutional Observability Core
        self.event_engine = EventEngine()
        self.metrics_collector = MetricsCollector()
        self.risk_manager.metrics_collector = self.metrics_collector  # Wire up reference
        
        self.strategy = None
        self.running = False
        self._eod_close_done = False
        self.scheduler_thread = None
        self.opening_account_value = None
        self._last_connection_status = None
        self.tz = pytz.timezone('America/New_York')
        
    def initialize(self):
        """Initialize the trading engine"""
        logger.info("=" * 60)
        logger.info("Initializing Automated Trading Engine")
        logger.info("=" * 60)

        if not config.PAPER_TRADING and not config.ENABLE_LIVE_TRADING:
            logger.warning("Configured for live IB port, but live order placement is not armed.")
            logger.warning("Set ENABLE_LIVE_TRADING=True only after account setup, funding, and manual review.")
        
        # Connect to Interactive Brokers
        if not self.ib_connection.connect():
            logger.error("Failed to connect to Interactive Brokers. Exiting.")
            return False

        if config.PAPER_TRADING:
            try:
                from paper_journal import record_session_start
                record_session_start()
            except Exception as exc:
                logger.debug(f"Paper journal session_start skipped: {exc}")
            
        # Capture starting positions for today's session
        self.ib_connection.refresh_account_data()
        positions = self.ib_connection.get_positions()
        starting = {}
        for sym, info in positions.items():
            if hasattr(info, "quantity"):
                starting[sym.upper()] = getattr(info, "quantity", 0)
            elif isinstance(info, dict):
                starting[sym.upper()] = info.get("quantity", 0)
            else:
                starting[sym.upper()] = 0
        daily_positions.reset_if_new_day(starting)

        # Initialize strategy based on configuration
        strategy_choice = getattr(config, "SELECTED_STRATEGY", "MOMENTUM").upper()
        if strategy_choice == "ML":
            self.strategy = MachineLearningStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info(f"Instantiated MachineLearningStrategy using {config.ML_MODEL_TYPE} model.")
        elif strategy_choice == "PAIRS":
            self.strategy = PairsTradingStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info("Instantiated PairsTradingStrategy (Statistical Arbitrage).")
        elif strategy_choice == "BREAKOUT":
            self.strategy = VolatilityBreakoutStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info("Instantiated VolatilityBreakoutStrategy.")
        elif strategy_choice == "IPO":
            self.strategy = IPOBreakoutStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info("Instantiated IPOBreakoutStrategy (Stock Chart Base Breakout).")
        elif strategy_choice == "LAGGER":
            self.strategy = CorrelatedLaggardStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info("Instantiated CorrelatedLaggardStrategy (Thematic Lead-Lag Sector Arbitrage).")
        else:
            self.strategy = MomentumStrategy(self.ib_connection, self.risk_manager, self.order_manager)
            logger.info("Instantiated default MomentumStrategy.")

        
        logger.info(f"Connected to account: {config.IB_ACCOUNT}")
        logger.info(f"Trading mode: {'PAPER' if config.PAPER_TRADING else 'LIVE'}")
        logger.info(f"Live orders armed: {config.ENABLE_LIVE_TRADING}")
        if not self._validate_startup_configuration():
            return False
        if config.PAPER_TRADING:
            logger.info(
                "Paper overrides: settled_cash=%s starter_mode=%s market_regime=%s learning=%s",
                config.REQUIRE_SETTLED_CASH_FOR_BUYS,
                config.STARTER_ACCOUNT_MODE,
                config.REQUIRE_MARKET_REGIME_CONFIRMATION,
                config.PAPER_LEARNING_MODE,
            )
            if config.PAPER_LEARNING_MODE:
                logger.info(
                    "Paper learning: max_pos=$%s max_trades/day=%s loop=%sm buy_signals>=%s news_required=%s",
                    config.MAX_POSITION_SIZE,
                    config.MAX_DAILY_TRADES,
                    config.TRADING_LOOP_MINUTES,
                    config.MIN_BUY_SIGNALS_FOR_ENTRY,
                    config.REQUIRE_BULLISH_NEWS_FOR_BUY,
                )
        logger.info(f"Max position size: ${config.MAX_POSITION_SIZE}")
        logger.info(f"Max daily loss: ${config.MAX_DAILY_LOSS}")
        
        return True
        
    def _validate_startup_configuration(self):
        """Validate paper/live startup configuration before connecting."""
        issues = []
        warnings = []

        if config.PAPER_TRADING:
            if config.IB_PORT != 7497:
                warnings.append(
                    f"PAPER_TRADING=True but IB_PORT={config.IB_PORT}. Confirm this is the intended paper port."
                )
        else:
            if not config.ENABLE_LIVE_TRADING:
                issues.append(
                    "LIVE trading mode is configured but ENABLE_LIVE_TRADING=False. "
                    "Set ENABLE_LIVE_TRADING=True only after manual review and account readiness."
                )
            if config.IB_PORT == 7497:
                issues.append(
                    "LIVE trading mode should not use paper port 7497. "
                    "Set IB_PORT=7496 for live trading or keep PAPER_TRADING=True for paper mode."
                )
            elif config.IB_PORT != 7496:
                warnings.append(
                    f"LIVE trading mode is configured on non-standard port {config.IB_PORT}. "
                    "Confirm your live TWS/IB Gateway port is correct."
                )

        for warning in warnings:
            logger.warning("Startup config warning: %s", warning)
        for issue in issues:
            logger.error("Startup config error: %s", issue)

        return len(issues) == 0
        
    def start(self):
        """Start the automated trading engine"""
        set_shutting_down(False)
        if not self.initialize():
            return False
            
        self.running = True
        logger.info("Trading engine started successfully")
        
        # Start the Asynchronous Event Engine in a dedicated background thread
        self._async_loop = asyncio.new_event_loop()
        
        def run_async_loop(loop):
            asyncio.set_event_loop(loop)
            self.event_engine.start()
            loop.run_forever()

        self._async_thread = threading.Thread(target=run_async_loop, args=(self._async_loop,), daemon=True)
        self._async_thread.start()
        logger.info("Asynchronous EventEngine thread started successfully.")
        
        # Submit the connection watchdog coroutine to the async loop thread-safely
        asyncio.run_coroutine_threadsafe(self.monitor_broker_connection(), self._async_loop)
        logger.info("Asynchronous Connection Watchdog submitted to EventEngine loop.")
        
        # Schedule tasks
        self._setup_schedule()
        
        # Start scheduler in separate thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        return True
        
    def _setup_schedule(self):
        """Set up trading schedule"""
        # Pre-market setup (every weekday at 9:00 AM)
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            getattr(schedule.every(), day).at("09:00").do(self._pre_market_setup)
        
        # Main trading loop (every 5 minutes during market hours)
        schedule.every(config.TRADING_LOOP_MINUTES).minutes.do(self._trading_loop)
        
        # Flatten today's positions shortly before the close
        if config.CLOSE_TODAYS_POSITIONS_AT_EOD:
            end_mins = config.TRADING_HOURS_END * 60 + config.TRADING_MINUTES_END
            close_mins = max(0, end_mins - config.EOD_CLOSE_MINUTES_BEFORE_END)
            close_at = f"{close_mins // 60:02d}:{close_mins % 60:02d}"
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
                getattr(schedule.every(), day).at(close_at).do(self._close_todays_positions)

        # End of day routine (every weekday at 4:15 PM)
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            getattr(schedule.every(), day).at("16:15").do(self._end_of_day)
        
        # Health check and connection monitoring every 2 minutes
        schedule.every(2).minutes.do(self._health_check)
        
        # Weekend reset (Sunday 6 PM)
        schedule.every().sunday.at("18:00").do(self._weekend_reset)
        
        logger.info("Trading schedule configured")
        
    def _run_scheduler(self):
        """Run the schedule loop"""
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def audit_positions(self) -> tuple[bool, str]:
        """
        Cross-reference local RiskManager positions with actual TWS positions.
        Returns (is_in_sync, message).
        """
        try:
            live_positions = self.ib_connection.get_positions()
            local_positions = self.risk_manager.open_positions
            
            # Compare sets of keys (case-insensitive keys)
            live_keys = {k.upper() for k, v in live_positions.items() if getattr(v, "quantity", 0) != 0}
            local_keys = {k.upper() for k, v in local_positions.items() if v.get("quantity", 0) != 0}
            
            untracked = live_keys - local_keys
            if untracked:
                return False, f"Untracked live positions detected in TWS: {untracked}"
                
            missing = local_keys - live_keys
            if missing:
                return False, f"Missing expected positions in TWS: {missing}"
                
            for sym in live_keys:
                live_info = live_positions.get(sym)
                local_info = local_positions.get(sym)
                
                live_qty = getattr(live_info, "quantity", 0) if not isinstance(live_info, dict) else live_info.get("quantity", 0)
                local_qty = local_info.get("quantity", 0)
                
                if live_qty != local_qty:
                    return False, f"Position quantity mismatch for {sym}: Expected {local_qty}, found {live_qty} in TWS."
                    
            return True, "Positions in perfect synchronization."
        except Exception as e:
            return False, f"Position audit failed: {e}"

    async def monitor_broker_connection(self):
        """Asynchronous Watchdog loop that polls connection status, stale data, and external position drift."""
        logger.info("[Watchdog Sentry] Connection Sentry started.")
        while self.running:
            try:
                await asyncio.sleep(10)
                
                connected = self.ib_connection.connected
                
                # Check Blocker 1: Market Data Freshness Sentry
                stale_data = False
                if connected and hasattr(self.ib_connection, "wrapper") and self.ib_connection.wrapper:
                    last_hb = getattr(self.ib_connection.wrapper, "last_heartbeat", None)
                    if last_hb is not None and isinstance(last_hb, (int, float)) and not isinstance(last_hb, bool):
                        elapsed = time.time() - last_hb
                        from utils import is_market_open
                        freshness_limit = getattr(config, "MARKET_DATA_FRESHNESS_LIMIT", 60)
                        if elapsed > freshness_limit and is_market_open():
                            logger.critical(f"[Watchdog Sentry] Market data STALE detected! Time since last tick: {elapsed:.1f}s (Limit: {freshness_limit}s). Engaging emergency safeties...")
                            stale_data = True
                
                if not connected or stale_data:
                    logger.critical("[Watchdog Sentry] Broker disconnection or stale data detected! Engaging emergency safeties...")
                    
                    # 1. Trigger the emergency Kill Switch in RiskManager
                    self.risk_manager.engage_kill_switch()
                    
                    # 2. Cancel all stale/pending orders
                    try:
                        self.order_manager.cancel_stale_orders()
                        logger.warning("[Watchdog Sentry] Stale orders cancelled during recovery sequence.")
                    except Exception as err:
                        logger.error(f"[Watchdog Sentry] Error cancelling stale orders: {err}")
                        
                    # If socket disconnected, attempt reconnection loop
                    if not connected:
                        logger.info("[Watchdog Sentry] Starting reconnection attempt...")
                        reconnect_success = False
                        
                        # Try to reconnect a few times
                        for attempt in range(1, 4):
                            logger.info(f"[Watchdog Sentry] Reconnection attempt {attempt}/3...")
                            try:
                                # Run in executor to prevent blocking the async event loop if socket creation blocks
                                loop = asyncio.get_running_loop()
                                reconnect_success = await loop.run_in_executor(None, self.ib_connection.connect)
                                if reconnect_success:
                                    logger.info("[Watchdog Sentry] Reconnection successful!")
                                    break
                            except Exception as conn_err:
                                logger.error(f"[Watchdog Sentry] Connection attempt {attempt} raised exception: {conn_err}")
                            await asyncio.sleep(5)
                            
                        if reconnect_success:
                            # 4. Synchronize positions and safely deactivate Kill Switch
                            try:
                                self.ib_connection.refresh_account_data()
                                positions = self.ib_connection.get_positions()
                                daily_positions.sync_from_ib_positions(positions)
                                logger.info("[Watchdog Sentry] Local positions and state successfully synchronized.")
                            except Exception as sync_err:
                                logger.error(f"[Watchdog Sentry] Error synchronizing state after reconnect: {sync_err}")
                                
                            # Safely deactivate the Kill Switch
                            self.risk_manager.disengage_kill_switch()
                        else:
                            logger.critical("[Watchdog Sentry] Reconnection attempts exhausted. System remains in LOCKDOWN mode.")
                    else:
                        logger.warning("[Watchdog Sentry] Socket remains open but data flow stalled. Webhook alert issued.")
                        send_alert("Market data feed freeze detected while socket connected. Core execution paused.", level="WARNING")
                
                # Check Blocker 2: Manual Trade Interference Sentry (Only check if connection is normal)
                elif connected and not stale_data and not self.risk_manager.kill_switch_active:
                    is_in_sync, audit_msg = self.audit_positions()
                    if not is_in_sync:
                        logger.critical(f"[Watchdog Sentry] MISMATCH CRITICAL WARNING: {audit_msg} Engaging programmatic Kill Switch.")
                        send_alert(f"MISMATCH CRITICAL WARNING: {audit_msg} Engaging programmatic Kill Switch.", level="ERROR")
                        self.risk_manager.engage_kill_switch()
                        
            except Exception as e:
                logger.error(f"[Watchdog Sentry] Error in watchdog monitoring loop: {e}")
            
    def _health_check(self):
        """Check IB connection health, update status, and alert on connection loss."""
        connected = self.ib_connection.connected
        if self._last_connection_status is None:
            self._last_connection_status = connected

        health_status = {
            "connected": connected,
            "account": config.IB_ACCOUNT,
            "running": self.running,
            "timestamp": datetime.now(self.tz).isoformat(timespec="seconds"),
        }
        update_health_status(health_status)

        if connected != self._last_connection_status:
            if not connected:
                send_alert(
                    "Automated alert: IB connection lost",
                    level="ERROR",
                    details={"account": config.IB_ACCOUNT},
                )
            else:
                send_alert(
                    "IB connection restored",
                    level="INFO",
                    details={"account": config.IB_ACCOUNT},
                )
            self._last_connection_status = connected

        if self.running:
            self.order_manager.cancel_stale_orders()

        if self.running and not connected:
            send_alert(
                "Attempting to reconnect to Interactive Brokers after connection loss.",
                level="WARNING",
                details={"account": config.IB_ACCOUNT},
            )
            if not self.ib_connection.connect(retry=False):
                send_alert(
                    "Reconnection attempt failed.",
                    level="ERROR",
                    details={"account": config.IB_ACCOUNT},
                )
            else:
                self._last_connection_status = self.ib_connection.connected

    def _update_daily_pnl(self):
        """Update the running daily profit and loss from account value changes."""
        account_snapshot = self.ib_connection.get_account_snapshot()
        if isinstance(account_snapshot, dict):
            from core.models import AccountSnapshot
            account_snapshot = AccountSnapshot(**account_snapshot)
        current_value = account_snapshot.net_liquidation
        if current_value is None:
            return 0.0

        if self.opening_account_value is None:
            self.opening_account_value = current_value

        daily_pnl = current_value - self.opening_account_value
        self.strategy.daily_profit_loss = daily_pnl
        self.risk_manager.update_daily_pnl(daily_pnl)
        return daily_pnl

    def _pre_market_setup(self):
        """Pre-market tasks"""
        if self.running:
            logger.info("=" * 60)
            logger.info("Pre-Market Setup")
            logger.info("=" * 60)
            
            try:
                # Request fresh account data
                self.ib_connection.refresh_account_data()
                positions = self.ib_connection.get_positions()
                account_snapshot = self.ib_connection.get_account_snapshot()
                if isinstance(account_snapshot, dict):
                    from core.models import AccountSnapshot
                    account_snapshot = AccountSnapshot(**account_snapshot)
                
                logger.info(f"Account Value: ${account_snapshot.net_liquidation:,.2f}")
                logger.info(f"Total Cash: ${account_snapshot.total_cash:,.2f}")
                logger.info(f"Available Funds: ${account_snapshot.available_funds:,.2f}")
                logger.info(f"Settled Cash: ${account_snapshot.settled_cash:,.2f}")
                logger.info(f"Funds for New Buys: ${account_snapshot.funds_for_new_buys:,.2f}")
                logger.info(f"Open Positions: {len(positions)}")
                
                # Reset daily stats and seed opening account value for P&L tracking
                self.strategy.reset_daily_stats()
                self.risk_manager.reset_daily_stats()
                self.opening_account_value = account_snapshot.net_liquidation
                self.strategy.daily_profit_loss = 0
                self.risk_manager.update_daily_pnl(0)
                
                # Capture starting positions for today's session
                starting = {sym.upper(): info.get("quantity", 0) for sym, info in positions.items()}
                daily_positions.reset_if_new_day(starting)
                self._eod_close_done = False
                
                logger.info(f"Opening Account Value: ${self.opening_account_value:,.2f}")
                
                # Fetch and log the daily market direction/regime
                regime = self.data_fetcher.get_market_regime()
                logger.info(f"Daily Market Direction (Regime): {regime}")
                
                # Trigger dynamic stock universe expander to discover new thematic winners & IPOs
                try:
                    if hasattr(self.stock_screener, "universe_expander"):
                        logger.info("[Pre-Market] Triggering Dynamic Stock Universe Expander...")
                        self.stock_screener.universe_expander.expand_universe()
                        # Re-sync StockScreener's search universe with new discoveries
                        dynamic_tickers = list(self.stock_screener.universe_expander.discovered_tickers)
                        if dynamic_tickers:
                            base_universe = config.STARTER_STOCKS if config.STARTER_ACCOUNT_MODE else (config.AI_INFRA_STOCKS if config.USE_AI_INFRA_UNIVERSE else config.ALLOWED_US_STOCKS)
                            self.stock_screener.default_stocks = list(set(base_universe + dynamic_tickers))
                except Exception as ex:
                    logger.error(f"Error in pre-market stock universe expansion: {ex}")
                
                logger.info("Pre-market setup completed")
                
            except Exception as e:
                logger.error(f"Error in pre-market setup: {e}")
                
    def _trading_loop(self):
        """Main trading loop - runs every N minutes during market hours"""
        if not self.running or not is_market_open():
            return
            
        try:
            self.ib_connection.refresh_account_data()
            self._update_daily_pnl()
            now = datetime.now(self.tz)
            logger.debug(f"Trading loop executing at {now.strftime('%H:%M:%S')}")

            self._check_position_exits()

            report = self._run_market_research()

            if is_shutting_down():
                logger.info("Shutdown in progress — skipping new entries")
                return

            if not report["can_execute_trades"]:
                return

            if report["signals"]:
                self.strategy.execute_trades(report["signals"])
            
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")

    def _run_market_research(self):
        """Analyze watchlist and positions; log open/close ideas even when not trading."""
        try:
            positions = self.ib_connection.get_positions()
            daily_positions.sync_from_ib_positions(positions)
            report = self.research.build_report(
                self.strategy,
                self.stock_screener,
                self.ib_connection,
                self.risk_manager,
            )
            self.research.log_report(report)
            return report
        except Exception as exc:
            logger.error(f"Market research failed: {exc}")
            return {
                "can_execute_trades": False,
                "blockers": ["research_error"],
                "signals": {},
            }
            
    def _check_position_exits(self):
        """Check if any positions should exit"""
        try:
            positions = self.ib_connection.get_positions()
            
            # Sync RiskManager with actual IB positions: remove any that are no longer held in IB
            for rm_symbol in list(self.risk_manager.open_positions.keys()):
                if rm_symbol not in positions:
                    logger.info(f"Syncing: position {rm_symbol} closed externally or filled; removing from RiskManager.")
                    self.risk_manager.remove_position(rm_symbol)

            for symbol in positions:
                # Skip exit checking if a SELL order is already active/pending
                if self.ib_connection.has_active_order(symbol, "SELL"):
                    logger.info(f"Skipping exit check for {symbol}: SELL order is already pending.")
                    continue

                current_price = self.data_fetcher.get_current_price(symbol)
                if current_price is None or current_price <= 0:
                    logger.warning(f"Skipping exit check for {symbol}: current price unavailable")
                    continue

                pos_info = positions[symbol]
                if hasattr(pos_info, "avg_cost"):
                    avg_cost = getattr(pos_info, "avg_cost", 0.0)
                    quantity = getattr(pos_info, "quantity", 0)
                elif isinstance(pos_info, dict):
                    avg_cost = pos_info.get('avg_cost')
                    quantity = pos_info.get('quantity', 0)
                else:
                    avg_cost = 0.0
                    quantity = 0
                
                # Sync quantity/cost to RiskManager on each cycle
                if avg_cost and quantity > 0:
                    self.risk_manager.add_position(symbol, quantity, avg_cost)

                if avg_cost and symbol not in self.risk_manager.stop_loss_prices:
                    self.risk_manager.set_stop_loss(symbol, avg_cost, config.STOP_LOSS_PERCENT)
                    self.risk_manager.set_take_profit(symbol, avg_cost, config.TAKE_PROFIT_PERCENT)
                
                if self.risk_manager.check_stop_loss(symbol, current_price):
                    limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                    if limit_price is None:
                        logger.warning(f"Skipping stop-loss sell for {symbol}: limit price unavailable")
                        continue

                    # Tax Safety Gate check before selling
                    if not self.risk_manager.check_tax_safety_gate(symbol, quantity, limit_price):
                        logger.warning(f"Stop-loss sell for {symbol} blocked by tax safety gates")
                        continue

                    req = OrderRequest(symbol=symbol, action=OrderSide.SELL, quantity=int(quantity), order_type=OrderType.LMT, limit_price=limit_price, metadata={"entry_price": avg_cost})
                    if getattr(self, "order_manager", None):
                        order_id = self.order_manager.submit_order_with_confirmation(req)
                    else:
                        order_id = self.ib_connection.place_order(symbol, "SELL", quantity, order_type="LMT", limit_price=limit_price, metadata={"entry_price": avg_cost})
                    if order_id:
                        self.risk_manager.tax_manager.process_sell(symbol, quantity, limit_price, order_id=order_id)
                        self.risk_manager.remove_position(symbol)
                        daily_positions.record_close(symbol)
                        
                elif self.risk_manager.check_take_profit(symbol, current_price):
                    limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                    if limit_price is None:
                        logger.warning(f"Skipping take-profit sell for {symbol}: limit price unavailable")
                        continue

                    # Tax Safety Gate check before selling
                    if not self.risk_manager.check_tax_safety_gate(symbol, quantity, limit_price):
                        logger.warning(f"Take-profit sell for {symbol} blocked by tax safety gates")
                        continue

                    req = OrderRequest(symbol=symbol, action=OrderSide.SELL, quantity=int(quantity), order_type=OrderType.LMT, limit_price=limit_price, metadata={"entry_price": avg_cost})
                    if getattr(self, "order_manager", None):
                        order_id = self.order_manager.submit_order_with_confirmation(req)
                    else:
                        order_id = self.ib_connection.place_order(symbol, "SELL", quantity, order_type="LMT", limit_price=limit_price, metadata={"entry_price": avg_cost})
                    if order_id:
                        self.risk_manager.tax_manager.process_sell(symbol, quantity, limit_price, order_id=order_id)
                        self.risk_manager.remove_position(symbol)
                        daily_positions.record_close(symbol)
                        
        except Exception as e:
            logger.error(f"Error checking position exits: {e}")

    def _close_todays_positions(self):
        """Close all positions that were opened during today's session."""
        if not self.running or self._eod_close_done or not config.CLOSE_TODAYS_POSITIONS_AT_EOD:
            return

        logger.info("=" * 60)
        logger.info("End-of-day — closing positions opened today")
        logger.info("=" * 60)

        try:
            self.ib_connection.refresh_account_data()
            to_close = daily_positions.get_opened_today()
            if not to_close:
                logger.info("No positions opened today to close")
                self._eod_close_done = True
                return

            positions = self.ib_connection.get_positions()
            closed = []
            for symbol in to_close:
                if symbol not in positions:
                    daily_positions.record_close(symbol)
                    continue
                pos_info = positions[symbol]
                if hasattr(pos_info, "quantity"):
                    qty = getattr(pos_info, "quantity", 0)
                    avg_cost = getattr(pos_info, "avg_cost", 0.0)
                elif isinstance(pos_info, dict):
                    qty = pos_info.get("quantity", 0)
                    avg_cost = pos_info.get("avg_cost", 0.0)
                else:
                    qty = 0
                    avg_cost = 0.0

                if qty <= 0:
                    daily_positions.record_close(symbol)
                    continue
                if self.ib_connection.has_active_order(symbol, "SELL"):
                    logger.info(f"EOD: skipping {symbol} close, SELL order is already pending.")
                    continue
                limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                if limit_price is None:
                    logger.warning(f"EOD: could not price SELL for {symbol}")
                    continue

                # Tax Safety Gate check before selling
                if not self.risk_manager.check_tax_safety_gate(symbol, qty, limit_price):
                    logger.warning(f"EOD close for {symbol} blocked by tax safety gates")
                    continue

                req = OrderRequest(symbol=symbol, action=OrderSide.SELL, quantity=int(qty), order_type=OrderType.LMT, limit_price=limit_price, metadata={"entry_price": avg_cost})
                if getattr(self, "order_manager", None):
                    order_id = self.order_manager.submit_order_with_confirmation(req)
                else:
                    order_id = self.ib_connection.place_order(symbol, "SELL", qty, order_type="LMT", limit_price=limit_price, metadata={"entry_price": avg_cost})
                if order_id:
                    self.risk_manager.tax_manager.process_sell(symbol, qty, limit_price, order_id=order_id)
                    closed.append(symbol)
                    self.risk_manager.remove_position(symbol)
                    daily_positions.record_close(symbol)
                    logger.info(f"EOD close submitted: SELL {qty} {symbol} @ ${limit_price:.2f}")

            if closed:
                logger.info(f"EOD close orders submitted for: {', '.join(closed)}")
                if self.ib_connection.has_pending_orders():
                    self.ib_connection.wait_for_pending_orders(timeout=120)
            self._eod_close_done = True

        except Exception as exc:
            logger.error(f"Error closing today's positions: {exc}")
            
    def _end_of_day(self):
        """End of day routine"""
        if self.running:
            logger.info("=" * 60)
            logger.info("End of Day Summary")
            logger.info("=" * 60)
            
            try:
                if config.CLOSE_TODAYS_POSITIONS_AT_EOD and not self._eod_close_done:
                    self._close_todays_positions()

                positions = self.ib_connection.get_positions()
                account_snapshot = self.ib_connection.get_account_snapshot()
                if isinstance(account_snapshot, dict):
                    from core.models import AccountSnapshot
                    account_snapshot = AccountSnapshot(**account_snapshot)
                daily_pnl = self._update_daily_pnl()
                position_info = self.risk_manager.get_position_info()
                
                logger.info(f"Final Account Value: ${account_snapshot.net_liquidation:,.2f}")
                logger.info(f"Final Total Cash: ${account_snapshot.total_cash:,.2f}")
                logger.info(f"Final Funds for New Buys: ${account_snapshot.funds_for_new_buys:,.2f}")
                logger.info(f"Daily Trades: {self.strategy.daily_trades}")
                logger.info(f"Daily P&L: ${daily_pnl:,.2f}")
                logger.info(f"Open Positions: {position_info['num_positions']}")
                logger.info(f"Portfolio Drawdown: {position_info['drawdown_percent']:.2f}%")

                if config.PAPER_TRADING:
                    try:
                        from paper_journal import record_daily_snapshot
                        record_daily_snapshot(
                            account_snapshot,
                            positions,
                            self.strategy.daily_trades,
                            daily_pnl,
                        )
                    except Exception as exc:
                        logger.debug(f"Paper journal daily_snapshot skipped: {exc}")
                
                remaining_today = daily_positions.get_opened_today()
                if remaining_today:
                    logger.warning(f"Positions still marked open today: {remaining_today}")
                
                logger.info("End of day routine completed")
                
            except Exception as e:
                logger.error(f"Error in end of day routine: {e}")
                
    def _weekend_reset(self):
        """Weekend reset routine"""
        logger.info("Weekend reset - preparing for next week")
        self.strategy.reset_daily_stats()
        self.risk_manager.reset_daily_stats()
        
    def _close_all_positions(self):
        """Close all open positions"""
        try:
            positions = self.ib_connection.get_positions()
            
            for symbol, pos_info in positions.items():
                if hasattr(pos_info, "quantity"):
                    quantity = getattr(pos_info, "quantity", 0)
                    avg_cost = getattr(pos_info, "avg_cost", 0.0)
                elif isinstance(pos_info, dict):
                    quantity = pos_info.get('quantity', 0)
                    avg_cost = pos_info.get('avg_cost', 0.0)
                else:
                    quantity = 0
                    avg_cost = 0.0

                if quantity <= 0:
                    continue
                limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                if limit_price is None:
                    logger.warning(f"Skipping close for {symbol}: limit price unavailable")
                    continue

                # Tax Safety Gate check before selling
                if not self.risk_manager.check_tax_safety_gate(symbol, quantity, limit_price):
                    logger.warning(f"Close all for {symbol} blocked by tax safety gates")
                    continue

                req = OrderRequest(symbol=symbol, action=OrderSide.SELL, quantity=int(quantity), order_type=OrderType.LMT, limit_price=limit_price, metadata={"entry_price": avg_cost})
                if getattr(self, "order_manager", None):
                    order_id = self.order_manager.submit_order_with_confirmation(req)
                else:
                    order_id = self.ib_connection.place_order(symbol, "SELL", quantity, order_type="LMT", limit_price=limit_price, metadata={"entry_price": avg_cost})
                if order_id:
                    self.risk_manager.tax_manager.process_sell(symbol, quantity, limit_price, order_id=order_id)
                    logger.info(f"Close order submitted for position: {symbol}")
                
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            
    def graceful_shutdown_for_restart(self):
        """Finish exit checks and open orders, then disconnect for a clean restart."""
        logger.info("=" * 60)
        logger.info("Graceful restart — no new buys; finishing exits and open orders")
        logger.info("=" * 60)
        set_shutting_down(True)
        self.running = False

        try:
            if self.ib_connection.connected:
                self.ib_connection.refresh_account_data()
                time.sleep(0.5)
                self._check_position_exits()
                if self.ib_connection.has_pending_orders():
                    logger.info("Waiting for working orders to complete...")
                    if not self.ib_connection.wait_for_pending_orders():
                        logger.warning("Some orders still working after timeout; continuing restart")
        except Exception as exc:
            logger.error(f"Error during graceful restart shutdown: {exc}")
        finally:
            self.stop()
            clear_restart_request()
            clear_pid()

    def stop(self):
        """Stop the trading engine"""
        logger.info("Stopping trading engine...")
        self.running = False
        
        # Gracefully stop the event engine and its loop thread
        if hasattr(self, "event_engine"):
            try:
                # Stop the event loop inside the async thread thread-safely
                if hasattr(self, "_async_loop") and self._async_loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.event_engine.stop(), self._async_loop).result()
                    self._async_loop.call_soon_threadsafe(self._async_loop.stop)
            except Exception as e:
                logger.error("Error stopping EventEngine: %s", e)

        # Do not automatically liquidate on normal shutdown. Stop-loss/take-profit
        # and explicit strategy exits manage positions during scheduled operation.
        
        if self.ib_connection.connected:
            self.ib_connection.disconnect()
        
        logger.info("Trading engine stopped")
        
    def get_status(self):
        """Get current status"""
        return {
            'running': self.running,
            'connected': self.ib_connection.connected,
            'account': config.IB_ACCOUNT,
            'account_value': self.ib_connection.get_account_value(),
            'cash': self.ib_connection.get_cash(),
            'account_snapshot': self.ib_connection.get_account_snapshot(),
            'positions': len(self.ib_connection.get_positions()),
            'daily_trades': self.strategy.daily_trades if self.strategy else 0
        }


def main():
    """Main entry point"""
    engine = TradingEngine()
    
    if not engine.start():
        logger.error("Failed to start trading engine")
        return

    write_pid()
    logger.info("Engine registered (pid %s). Run again to graceful-restart.", os.getpid())

    try:
        while engine.running:
            if is_restart_requested():
                engine.graceful_shutdown_for_restart()
                return
            time.sleep(config.RESTART_POLL_INTERVAL)
            logger.debug(f"Status: {engine.get_status()}")
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        
    finally:
        engine.stop()
        clear_pid()
        clear_restart_request()


if __name__ == "__main__":
    main()
