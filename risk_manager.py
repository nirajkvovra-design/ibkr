from utils import get_logger
import config

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
        
        # Instantiate Self-Learning feedback loop
        from self_learning import SelfLearningAgent
        self.learning_agent = SelfLearningAgent()
        
    def is_within_limits(self, symbol, quantity, entry_price):
        """Check if a trade is within risk limits"""
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
        stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
        self.stop_loss_prices[symbol] = stop_loss_price
        logger.info(f"Stop loss set for {symbol}: ${stop_loss_price:.2f}")
        return stop_loss_price
        
    def set_take_profit(self, symbol, entry_price, take_profit_percent=5):
        """Set take profit price for a position"""
        take_profit_price = entry_price * (1 + take_profit_percent / 100)
        self.take_profit_prices[symbol] = take_profit_price
        logger.info(f"Take profit set for {symbol}: ${take_profit_price:.2f}")
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
        
    def remove_position(self, symbol):
        """Remove a closed position"""
        if symbol in self.open_positions:
            del self.open_positions[symbol]
        if symbol in self.stop_loss_prices:
            del self.stop_loss_prices[symbol]
        if symbol in self.take_profit_prices:
            del self.take_profit_prices[symbol]
        logger.debug(f"Position removed: {symbol}")
            
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
        
    def reset_daily_stats(self):
        """Reset daily statistics"""
        self.daily_loss = 0
        logger.info("Daily statistics reset")
        
    def get_position_info(self):
        """Get summary of current positions"""
        total_value = sum(pos['current_value'] for pos in self.open_positions.values())
        return {
            'num_positions': len(self.open_positions),
            'total_value': total_value,
            'daily_loss': self.daily_loss,
            'drawdown_percent': self.get_current_drawdown()
        }
