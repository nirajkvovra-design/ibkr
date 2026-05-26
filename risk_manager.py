from utils import get_logger, send_alert
import config
from tax_manager import TaxManager

logger = get_logger(__name__)

class RiskManager:
    """Manages trading risk and position limits"""
    
    def __init__(self, ib_connection):
        self.ib_connection = ib_connection
        self.daily_loss = 0
        self.max_daily_loss = config.MAX_DAILY_LOSS
        self.max_position_size = config.MAX_POSITION_SIZE
        self.open_positions = {}
        self.stop_loss_prices = {}
        self.take_profit_prices = {}
        
        # Instantiate DataFetcher
        from data_fetcher import DataFetcher
        self.data_fetcher = DataFetcher()

        # Instantiate Tax Lot Manager
        self.tax_manager = TaxManager()
        
        # Instantiate Self-Learning feedback loop
        from self_learning import SelfLearningAgent
        self.learning_agent = SelfLearningAgent()
        
        # Instantiate Portfolio Risk Engine
        from portfolio_risk_engine import PortfolioRiskEngine
        self.portfolio_risk_engine = PortfolioRiskEngine()
        
        # Institutional Safety Sentinels
        self.kill_switch_active: bool = False
        self.symbol_cooldowns: Dict[str, float] = {}

        # Persistent State Manager
        from core.state_manager import StateManager
        self.state_manager = StateManager()
        self.rehydrate_state()

        # Macro & Geopolitical Intelligence Engine
        from core.macro_intelligence import MacroIntelligenceEngine
        self.macro_engine = MacroIntelligenceEngine(self.data_fetcher)
        
    def is_within_limits(self, symbol, quantity, entry_price):
        """Check if a trade is within risk limits"""
        # Block immediately if kill switch is active
        if self.kill_switch_active:
            logger.error("[Risk Sentry] Trade blocked: Programmatic Kill Switch is active!")
            return False

        # Check Blocker 1: Market data freshness check
        if hasattr(self.ib_connection, "wrapper") and self.ib_connection.wrapper:
            last_hb = getattr(self.ib_connection.wrapper, "last_heartbeat", None)
            if last_hb is not None and isinstance(last_hb, (int, float)) and not isinstance(last_hb, bool):
                import time
                elapsed = time.time() - last_hb
                from utils import is_market_open
                freshness_limit = getattr(config, "MARKET_DATA_FRESHNESS_LIMIT", 60)
                if elapsed > freshness_limit and is_market_open():
                    logger.critical(f"[Risk Sentry] Trade blocked: Market data is STALE! Time since last tick: {elapsed:.1f}s (Limit: {freshness_limit}s). Engaging programmatic Kill Switch.")
                    send_alert(f"Market data stale: {elapsed:.1f}s since last tick. Engaging programmatic Kill Switch.", level="ERROR")
                    self.engage_kill_switch()
                    return False

        # Block immediately if symbol is in trade cooldown
        if self.is_in_cooldown(symbol):
            logger.warning("[Risk Sentry] Trade blocked: %s is currently in cooldown state.", symbol.upper())
            return False

        # Factor in contract multipliers for futures to evaluate the true leverage-adjusted exposure
        import os
        multiplier = 1
        clean_sym = symbol.upper().replace("-USD", "").replace("=F", "")
        futures_list = getattr(config, "FUTURE_SYMBOLS", ["ES", "NQ", "YM", "CL", "GC"])
        is_future = symbol.upper() in futures_list or symbol.upper().endswith("=F") or os.getenv(f"FUTURE_EXCHANGE_{clean_sym}") is not None
        
        if is_future:
            multipliers = getattr(config, "FUTURE_MULTIPLIERS", {})
            env_val = os.getenv(f"FUTURE_MULTIPLIER_{clean_sym}")
            multiplier = int(env_val) if env_val is not None else multipliers.get(clean_sym, 1)

        position_value = quantity * entry_price * multiplier
        
        # 1. Check self-learning blacklist/cooling-off
        if self.learning_agent.is_blacklisted(symbol):
            logger.warning(f"[Risk Sentry] Trade for {symbol} blocked by self-learned cooling-off blacklist.")
            return False
            
        # Check account value limit
        account_value = self.ib_connection.get_account_value()
        if account_value <= 0:
            logger.warning("Account value is unavailable or zero; blocking trade")
            return False
            
        # 2. Determine maximum position size limit (scaled by self-learning performance metrics)
        learning_multiplier = self.learning_agent.get_sizing_multiplier(symbol)
        max_pos_limit = self.max_position_size * learning_multiplier
        if getattr(config, "DYNAMIC_RISK_SCALING", True):
            max_pos_limit = account_value * config.MAX_PORTFOLIO_POSITION_PERCENT * learning_multiplier
            
        if learning_multiplier != 1.0:
            logger.info(f"[Self-Learning Sentry] Sizing multiplier for {symbol} is {learning_multiplier}x (Max Pos: ${max_pos_limit:.2f})")
            
        # 3. Dynamic de-risking based on portfolio volatility spikes
        risk_report = self.evaluate_portfolio_risk()
        vol_multiplier = 1.0
        max_vol_limit = getattr(config, "MAX_PORTFOLIO_VOLATILITY", 25.0)
        if risk_report.portfolio_volatility > max_vol_limit:
            vol_multiplier = 0.5
            logger.warning(
                f"[Risk Sentry] High portfolio volatility detected: {risk_report.portfolio_volatility:.1f}% "
                f"(Threshold: {max_vol_limit}%). Scaling down position sizing by 50%."
            )

        # --- MACRO & GEOPOLITICAL INTELLIGENCE SHIELD ---
        macro_report = self.macro_engine.get_macro_intelligence_report()
        
        # A. Economic Event Blackout Window Check (block new buys/entries)
        if macro_report["event_blackout"]["is_blocked"]:
            logger.warning("[Risk Sentry] Trade blocked: pre-event economic blackout window engaged (%s).",
                           macro_report["event_blackout"]["reason"])
            return False

        # B. Leverage Regulation under Panic / Liquidity Stress
        regime = macro_report["regime"]
        if regime in ("PANIC", "LIQUIDITY_CRISIS"):
            current_exposure = self.get_position_info()["total_value"]
            if current_exposure + position_value > account_value:
                logger.warning(
                    "[Risk Sentry] Trade blocked: leverage cap engaged under PANIC/LIQUIDITY_CRISIS regime. "
                    "Total exposure ($%.2f) would exceed total account equity ($%.2f).",
                    current_exposure + position_value, account_value
                )
                return False

        # C. Dynamic Exposure Scaling based on Macro Stress and Regimes
        macro_multiplier = 1.0
        if regime == "LIQUIDITY_CRISIS":
            macro_multiplier = 0.15
        elif regime == "PANIC":
            macro_multiplier = 0.25
        elif regime == "GEOPOLITICAL_SHOCK":
            macro_multiplier = 0.40
        elif regime == "INFLATION_SHOCK":
            macro_multiplier = 0.50
        elif regime == "HIGH_VOL_TREND":
            macro_multiplier = 0.75
            
        # Incorporate headline sentiment de-risking factor
        macro_multiplier *= macro_report["geopolitical_multiplier"]
            
        max_pos_limit *= vol_multiplier * macro_multiplier
        if macro_multiplier != 1.0:
            logger.info("[Risk Sentry] Macro & Geopolitical regime scaling active: %.2fx (Max Pos Limit: $%.2f)",
                        macro_multiplier, max_pos_limit)
        
        # 4. Parametric Value at Risk (VaR) safety gate
        max_var_limit = account_value * getattr(config, "MAX_PORTFOLIO_VAR_PERCENT", 0.05)
        if risk_report.parametric_var_95 > max_var_limit:
            logger.warning(
                f"[Risk Sentry] Trade blocked: 95% Parametric VaR (${risk_report.parametric_var_95:.2f}) "
                f"exceeds safety threshold (${max_var_limit:.2f}, 5% of account value)."
            )
            return False

        # Check individual position limit
        if position_value > max_pos_limit:
            logger.warning(f"Position size ${position_value:.2f} exceeds learned limit of ${max_pos_limit:.2f}")
            return False
            
        if (
            config.STARTER_ACCOUNT_MODE
            and not config.PAPER_TRADING
            and not getattr(config, "DYNAMIC_RISK_SCALING", True)
            and account_value > config.STARTER_ACCOUNT_CAPITAL * 1.5
        ):
            logger.warning("Starter mode is enabled for a larger account; blocking until risk settings are reviewed")
            return False

        position_percent = (position_value / account_value) * 100
        
        max_percent = config.MAX_PORTFOLIO_POSITION_PERCENT * 100
        if position_percent > max_percent:
            logger.warning(f"Position {position_percent:.1f}% exceeds {max_percent:.1f}% limit")
            return False
            
        # Determine maximum daily loss limit
        max_loss_limit = self.max_daily_loss
        if getattr(config, "DYNAMIC_RISK_SCALING", True):
            # Scale daily loss limit relative to starter ratio (e.g. 20 / 1000 = 2% daily loss)
            loss_percent = config.MAX_DAILY_LOSS / config.STARTER_ACCOUNT_CAPITAL
            max_loss_limit = account_value * loss_percent
            
        # Check daily loss
        if self.daily_loss < -max_loss_limit:
            logger.warning(f"Daily loss limit exceeded: ${self.daily_loss:.2f} (Limit: ${max_loss_limit:.2f})")
            return False
            
        # Check fee efficiency
        if not self.is_fee_efficient(symbol, quantity, entry_price):
            return False

        return True

    def is_fee_efficient(self, symbol, quantity, price):
        """Check if expected trade profit covers round-trip transaction costs by a safe margin."""
        from utils import calculate_transaction_cost
        
        # Calculate expected profit (using strategy's take profit threshold)
        expected_profit = quantity * price * (config.TAKE_PROFIT_PERCENT / 100)
        
        # Calculate estimated round-trip transaction cost (BUY fee + SELL fee at target profit price)
        buy_cost = calculate_transaction_cost(quantity, price, "BUY")
        target_sell_price = price * (1 + config.TAKE_PROFIT_PERCENT / 100)
        sell_cost = calculate_transaction_cost(quantity, target_sell_price, "SELL")
        total_fee = buy_cost + sell_cost
        
        if expected_profit <= 0:
            return False
            
        fee_ratio = total_fee / expected_profit
        if fee_ratio > config.MAX_FEE_TO_PROFIT_RATIO:
            logger.warning(
                f"Trade for {symbol} blocked: fee-inefficient. "
                f"Expected profit: ${expected_profit:.2f}. "
                f"Est. round-trip fees: ${total_fee:.2f} ({fee_ratio * 100:.1f}% of profit, max allowed: {config.MAX_FEE_TO_PROFIT_RATIO * 100:.1f}%). "
                f"Sizing: {quantity} share(s) @ ${price:.2f}. Consider increasing MAX_POSITION_SIZE or TAKE_PROFIT_PERCENT."
            )
            return False
            
        logger.info(
            f"Fee-efficiency check passed for {symbol}: "
            f"Expected profit: ${expected_profit:.2f}, Est. round-trip fees: ${total_fee:.2f} ({fee_ratio * 100:.1f}% of profit)."
        )
        return True
        
    def set_stop_loss(self, symbol, entry_price, stop_loss_percent=2):
        """Set stop loss price for a position"""
        # Adjust stop width dynamically based on macro volatility regime
        vol_multiplier = 1.0
        try:
            macro_report = self.macro_engine.get_macro_intelligence_report()
            regime = macro_report["regime"]
            if regime in ("PANIC", "LIQUIDITY_CRISIS", "GEOPOLITICAL_SHOCK"):
                vol_multiplier = 1.5  # widen stop bounds to prevent whipsaw stoppages
                logger.info("[Risk Sentry] Widen stop loss width by 1.5x due to high-volatility macro regime: %s", regime)
        except Exception:
            pass

        stop_loss_price = entry_price * (1 - (stop_loss_percent * vol_multiplier) / 100)
        self.stop_loss_prices[symbol] = stop_loss_price
        logger.info(f"Stop loss set for {symbol}: ${stop_loss_price:.2f}")
        self.persist_state()
        return stop_loss_price
        
    def set_take_profit(self, symbol, entry_price, take_profit_percent=5):
        """Set take profit price for a position"""
        take_profit_price = entry_price * (1 + take_profit_percent / 100)
        self.take_profit_prices[symbol] = take_profit_price
        logger.info(f"Take profit set for {symbol}: ${take_profit_price:.2f}")
        self.persist_state()
        return take_profit_price
        
    def check_stop_loss(self, symbol, current_price):
        """Check if position should be stopped out"""
        if symbol in self.stop_loss_prices:
            if current_price <= self.stop_loss_prices[symbol]:
                logger.warning(f"Stop loss triggered for {symbol} at ${current_price:.2f}")
                return True
        return False
        
    def check_take_profit(self, symbol, current_price):
        """Check if position should take profit"""
        if symbol in self.take_profit_prices:
            if current_price >= self.take_profit_prices[symbol]:
                logger.info(f"Take profit triggered for {symbol} at ${current_price:.2f}")
                return True
        return False
        
    def add_position(self, symbol, quantity, entry_price):
        """Record an open position"""
        self.open_positions[symbol] = {
            'quantity': quantity,
            'entry_price': entry_price,
            'current_value': quantity * entry_price
        }
        logger.debug(f"Position added: {symbol} x {quantity} @ ${entry_price}")
        self.persist_state()
        
    def remove_position(self, symbol):
        """Remove a closed position"""
        if symbol in self.open_positions:
            del self.open_positions[symbol]
        if symbol in self.stop_loss_prices:
            del self.stop_loss_prices[symbol]
        if symbol in self.take_profit_prices:
            del self.take_profit_prices[symbol]
        logger.debug(f"Position removed: {symbol}")
        self.persist_state()
            
    def get_current_drawdown(self):
        """Calculate current portfolio drawdown"""
        account_value = self.ib_connection.get_account_value()
        if account_value <= 0:
            return 0
        return (self.daily_loss / account_value) * 100
        
    def is_trading_allowed(self):
        """Determine if new trades should be allowed"""
        drawdown = self.get_current_drawdown()
        
        # Stop trading if daily loss exceeds limit
        if drawdown <= -2:  # 2% daily loss limit
            logger.warning(f"Drawdown exceeded: {drawdown:.2f}%. Trading halted.")
            return False
            
        return True
        
    def update_daily_pnl(self, pnl):
        """Update daily profit/loss"""
        self.daily_loss = pnl
        logger.debug(f"Daily P&L: ${self.daily_loss:.2f}")
        self.persist_state()
        
    def reset_daily_stats(self):
        """Reset daily statistics"""
        self.daily_loss = 0
        logger.info("Daily statistics reset")
        self.persist_state()

    def persist_state(self) -> None:
        """Serialize current in-memory risk state to disk."""
        state = {
            "daily_loss": self.daily_loss,
            "open_positions": self.open_positions,
            "stop_loss_prices": self.stop_loss_prices,
            "take_profit_prices": self.take_profit_prices,
        }
        self.state_manager.save_state(state)

    def rehydrate_state(self) -> None:
        """Restore risk state from disk cache."""
        state = self.state_manager.load_state()
        if state:
            self.daily_loss = state.get("daily_loss", 0)
            self.open_positions = state.get("open_positions", {})
            self.stop_loss_prices = state.get("stop_loss_prices", {})
            self.take_profit_prices = state.get("take_profit_prices", {})
            logger.info(
                "[Risk Sentry] Rehydrated state: daily_loss=$%.2f, %d open positions, %d stop-losses, %d take-profits",
                self.daily_loss, len(self.open_positions), len(self.stop_loss_prices), len(self.take_profit_prices)
            )
        
    def get_position_info(self):
        """Get summary of current positions"""
        total_value = sum(pos['current_value'] for pos in self.open_positions.values())
        return {
            'num_positions': len(self.open_positions),
            'total_value': total_value,
            'daily_loss': self.daily_loss,
            'drawdown_percent': self.get_current_drawdown()
        }

    def evaluate_portfolio_risk(self):
        """Evaluate real-time portfolio risk using the Portfolio Risk Engine."""
        account_value = self.ib_connection.get_account_value()
        cash = self.ib_connection.get_cash()
        return self.portfolio_risk_engine.calculate_portfolio_risk_metrics(
            open_positions=self.open_positions,
            account_value=account_value,
            cash=cash
        )

    def evaluate_tax_implication(self, symbol: str, quantity: float, current_price: float) -> dict:
        """
        Evaluate tax implications before selling a stock.
        Logs detailed structural breakdown of the tax event.
        """
        implication = self.tax_manager.estimate_tax_implication(symbol, quantity, current_price)
        estimated_tax = implication["estimated_tax"]
        realized_pnl = implication["realized_pnl"]

        logger.info(
            "[Tax Assessment] PRE-SELL tax check for %s | Qty: %.2f @ $%.2f",
            symbol.upper(), quantity, current_price
        )
        sign_pnl = "+" if realized_pnl >= 0 else "-"
        sign_stcg = "+" if implication["short_term_gain_loss"] >= 0 else "-"
        sign_ltcg = "+" if implication["long_term_gain_loss"] >= 0 else "-"
        logger.info(
            "                 Est. Realized P&L: %s$%.2f (STCG: %s$%.2f, LTCG: %s$%.2f)",
            sign_pnl, abs(realized_pnl),
            sign_stcg, abs(implication["short_term_gain_loss"]),
            sign_ltcg, abs(implication["long_term_gain_loss"])
        )
        logger.info("                 Est. Tax Liability: $%.2f", estimated_tax)

        if estimated_tax >= config.TAX_IMPLICATION_WARNING_THRESHOLD:
            warning_msg = (
                f"[Tax Warning] Sell of {quantity} {symbol} @ ${current_price:.2f} "
                f"exceeds tax warning threshold! Est Tax: ${estimated_tax:.2f} "
                f"(Threshold: ${config.TAX_IMPLICATION_WARNING_THRESHOLD:.2f})."
            )
            logger.warning(warning_msg)
            send_alert(
                warning_msg,
                level="WARNING",
                details={
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": current_price,
                    "estimated_tax": estimated_tax,
                    "realized_pnl": realized_pnl,
                }
            )

        return implication

    def check_tax_safety_gate(self, symbol: str, quantity: float, current_price: float) -> bool:
        """
        Evaluate if a sale should be blocked or warning-flagged under tax safety gates.
        If config.ENABLE_TAX_SAFETY_GATES is True, blocks sales exceeding threshold.
        """
        implication = self.evaluate_tax_implication(symbol, quantity, current_price)
        estimated_tax = implication["estimated_tax"]

        if config.ENABLE_TAX_SAFETY_GATES and estimated_tax >= config.TAX_IMPLICATION_WARNING_THRESHOLD:
            logger.error(
                "[Tax Block] Trade BLOCKED by tax safety gate. Est. Tax $%.2f exceeds limit $%.2f.",
                estimated_tax, config.TAX_IMPLICATION_WARNING_THRESHOLD
            )
            return False

        return True

    # ========================================================
    # INSTITUTIONAL SAFETY SYSTEMS
    # ========================================================

    def activate_kill_switch(self) -> None:
        """Globally halt all new trade signal executions immediately."""
        self.kill_switch_active = True
        msg = "[Risk Sentinel] EMERGENCY KILL SWITCH ACTIVATED globally. New signal entries are locked!"
        logger.error(msg)
        send_alert(msg, level="ERROR")

    def deactivate_kill_switch(self) -> None:
        """Unlock and restore global trading capabilities."""
        self.kill_switch_active = False
        msg = "[Risk Sentinel] global Kill Switch deactivated. Trading execution unlocked."
        logger.info(msg)
        send_alert(msg, level="INFO")

    def trigger_cooldown(self, symbol: str, duration_seconds: float = 300.0) -> None:
        """Place a specific ticker under a trading lock-out cooldown period."""
        symbol_upper = symbol.upper()
        import time
        self.symbol_cooldowns[symbol_upper] = time.time() + duration_seconds
        logger.warning(
            "[Risk Sentinel] Trade COOLDOWN triggered for %s. Locked for %s seconds.",
            symbol_upper, int(duration_seconds)
        )

    def is_in_cooldown(self, symbol: str) -> bool:
        """Check if a ticker is currently locked under a cooldown period."""
        symbol_upper = symbol.upper()
        if symbol_upper not in self.symbol_cooldowns:
            return False
        import time
        if time.time() > self.symbol_cooldowns[symbol_upper]:
            del self.symbol_cooldowns[symbol_upper]
            return False
        return True

    def flatten_all_positions(self, order_manager: Optional[Any] = None) -> None:
        """
        Emergency system to cancel all working orders and liquidate all open positions.
        Automatically arms the programmatic Kill Switch to prevent new execution signals.
        """
        # 1. Immediately activate the global kill switch
        self.activate_kill_switch()

        alert_msg = "[Emergency Risk Alert] Emergency FLATTEN activated! Cancelling all orders and liquidating all positions..."
        logger.error("=" * 80)
        logger.error(alert_msg)
        logger.error("=" * 80)
        send_alert(alert_msg, level="ERROR")

        try:
            # 2. Refresh and fetch active positions
            self.ib_connection.refresh_account_data()
            positions = self.ib_connection.get_positions()
            
            if not positions:
                logger.info("[Emergency Risk Alert] No open positions detected. Flatten complete.")
                return

            from core.models import OrderRequest, OrderSide, OrderType
            import os

            for symbol, pos in positions.items():
                qty = pos.quantity
                if qty == 0:
                    continue

                logger.warning(
                    "[Emergency Risk Alert] Liquidating position: %s | Qty: %.2f | Avg Cost: $%.2f",
                    symbol, qty, pos.avg_cost
                )

                # Cancel any existing active orders for this symbol first
                if order_manager and hasattr(order_manager, "submitted_orders"):
                    for oid, order_info in list(order_manager.submitted_orders.items()):
                        if order_info["request"].symbol == symbol:
                            logger.warning("[Emergency Risk Alert] Cancelling working order %s for %s", oid, symbol)
                            self.ib_connection.cancel_order(oid)

                # Generate the liquidating order Request (opposite side)
                side = OrderSide.SELL if qty > 0 else OrderSide.BUY
                liq_qty = abs(qty)

                # Fetch best bid/ask or limit price for liquidation
                try:
                    from data_fetcher import DataFetcher
                    fetcher = DataFetcher()
                    limit_price = fetcher.get_limit_price(symbol, side.value)
                except Exception:
                    limit_price = None

                # Construct OrderRequest. Default to MKT if limit price is unavailable
                req = OrderRequest(
                    symbol=symbol,
                    action=side,
                    quantity=int(liq_qty) if isinstance(liq_qty, (int, float)) else liq_qty,
                    order_type=OrderType.MKT if limit_price is None else OrderType.LMT,
                    limit_price=limit_price,
                    metadata={"note": "Emergency Risk Flatten"},
                )

                # Submit to OMS
                if order_manager:
                    order_manager.submit_order(req)
                else:
                    self.ib_connection.place_order(req)

            logger.error("[Emergency Risk Alert] Emergency liquidation orders submitted for all open positions.")
        except Exception as exc:
            logger.critical("[Emergency Risk Error] Failed during emergency flatten: %s", exc)

    def engage_kill_switch(self):
        """Programmatically engage the Kill Switch to block all new executions."""
        if not self.kill_switch_active:
            self.kill_switch_active = True
            logger.warning("[Risk Manager] Programmatic Kill Switch has been ENGAGED.")
            send_alert("Programmatic Kill Switch ENGAGED due to system health event.", level="CRITICAL")

    def disengage_kill_switch(self):
        """Programmatically disengage the Kill Switch to allow new executions."""
        if self.kill_switch_active:
            self.kill_switch_active = False
            logger.info("[Risk Manager] Programmatic Kill Switch has been DISENGAGED.")
            send_alert("Programmatic Kill Switch DISENGAGED. Normal operations resumed.", level="INFO")


