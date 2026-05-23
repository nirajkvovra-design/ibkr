import os
import schedule
import time
import threading
from datetime import datetime
import pytz
import config
from utils import get_logger, is_market_open, format_trade_log, setup_logging, send_alert, update_health_status
from ib_connection import InteractiveBrokersConnection
from strategies import MomentumStrategy, GridTradingStrategy, MachineLearningStrategy
from risk_manager import RiskManager
from data_fetcher import DataFetcher
from stock_screener import StockScreener
from trade_research import TradeResearch
import daily_positions
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
        self.risk_manager = RiskManager(self.ib_connection)
        self.data_fetcher = DataFetcher()
        self.stock_screener = StockScreener()
        self.research = TradeResearch(self.data_fetcher)
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
        starting = {sym.upper(): info.get("quantity", 0) for sym, info in positions.items()}
        daily_positions.reset_if_new_day(starting)

        # Initialize strategy based on configuration
        strategy_choice = getattr(config, "SELECTED_STRATEGY", "MOMENTUM").upper()
        if strategy_choice == "ML":
            self.strategy = MachineLearningStrategy(self.ib_connection, self.risk_manager)
            logger.info(f"Instantiated MachineLearningStrategy using {config.ML_MODEL_TYPE} model.")
        else:
            self.strategy = MomentumStrategy(self.ib_connection, self.risk_manager)
            logger.info("Instantiated default MomentumStrategy.")
        
        logger.info(f"Connected to account: {config.IB_ACCOUNT}")
        logger.info(f"Trading mode: {'PAPER' if config.PAPER_TRADING else 'LIVE'}")
        logger.info(f"Live orders armed: {config.ENABLE_LIVE_TRADING}")
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
        
    def start(self):
        """Start the automated trading engine"""
        set_shutting_down(False)
        if not self.initialize():
            return False
            
        self.running = True
        logger.info("Trading engine started successfully")
        
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
            self.ib_connection.cancel_stale_orders()

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
        current_value = account_snapshot.get('net_liquidation')
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
                
                logger.info(f"Account Value: ${account_snapshot['net_liquidation']:,.2f}")
                logger.info(f"Total Cash: ${account_snapshot['total_cash']:,.2f}")
                logger.info(f"Available Funds: ${account_snapshot['available_funds']:,.2f}")
                logger.info(f"Settled Cash: ${account_snapshot['settled_cash']:,.2f}")
                logger.info(f"Funds for New Buys: ${account_snapshot['funds_for_new_buys']:,.2f}")
                logger.info(f"Open Positions: {len(positions)}")
                
                # Reset daily stats and seed opening account value for P&L tracking
                self.strategy.reset_daily_stats()
                self.risk_manager.reset_daily_stats()
                self.opening_account_value = account_snapshot.get('net_liquidation')
                self.strategy.daily_profit_loss = 0
                self.risk_manager.update_daily_pnl(0)
                
                # Capture starting positions for today's session
                starting = {sym.upper(): info.get("quantity", 0) for sym, info in positions.items()}
                daily_positions.reset_if_new_day(starting)
                self._eod_close_done = False
                
                logger.info(f"Opening Account Value: ${self.opening_account_value:,.2f}")
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

                avg_cost = positions[symbol].get('avg_cost')
                quantity = positions[symbol].get('quantity', 0)
                
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
                    order_id = self.ib_connection.place_order(
                        symbol,
                        "SELL",
                        quantity,
                        order_type="LMT",
                        limit_price=limit_price,
                        metadata={"entry_price": avg_cost},
                    )
                    if order_id:
                        self.risk_manager.remove_position(symbol)
                        daily_positions.record_close(symbol)
                        
                elif self.risk_manager.check_take_profit(symbol, current_price):
                    limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                    if limit_price is None:
                        logger.warning(f"Skipping take-profit sell for {symbol}: limit price unavailable")
                        continue
                    order_id = self.ib_connection.place_order(
                        symbol,
                        "SELL",
                        quantity,
                        order_type="LMT",
                        limit_price=limit_price,
                        metadata={"entry_price": avg_cost},
                    )
                    if order_id:
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
                qty = positions[symbol]["quantity"]
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
                order_id = self.ib_connection.place_order(
                    symbol,
                    "SELL",
                    qty,
                    order_type="LMT",
                    limit_price=limit_price,
                    metadata={"entry_price": positions[symbol].get("avg_cost")},
                )
                if order_id:
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
                daily_pnl = self._update_daily_pnl()
                position_info = self.risk_manager.get_position_info()
                
                logger.info(f"Final Account Value: ${account_snapshot['net_liquidation']:,.2f}")
                logger.info(f"Final Total Cash: ${account_snapshot['total_cash']:,.2f}")
                logger.info(f"Final Funds for New Buys: ${account_snapshot['funds_for_new_buys']:,.2f}")
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
                quantity = pos_info['quantity']
                if quantity <= 0:
                    continue
                limit_price = self.data_fetcher.get_limit_price(symbol, "SELL")
                if limit_price is None:
                    logger.warning(f"Skipping close for {symbol}: limit price unavailable")
                    continue
                order_id = self.ib_connection.place_order(
                    symbol,
                    "SELL",
                    quantity,
                    order_type="LMT",
                    limit_price=limit_price,
                    metadata={"entry_price": pos_info.get("avg_cost")},
                )
                if order_id:
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
