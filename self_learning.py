"""
Self-Learning Agent: analyzes past trade history to detect mistakes,
applies dynamic blacklists (cooling-off periods), and scales position sizes dynamically.
"""

import os
import sys

# Ensure local workspace path is in python search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
import config
from paper_journal import load_trade_history

logger = logging.getLogger(__name__)

class SelfLearningAgent:
    """Empirical Self-Learning Feedback Loop"""

    def __init__(self):
        self.cooling_off_days = getattr(config, "COOLING_OFF_DAYS", 3)
        self.consecutive_loss_limit = getattr(config, "CONSECUTIVE_LOSS_LIMIT", 2)
        self.min_win_rate = getattr(config, "MIN_WIN_RATE", 0.35)
        self.min_trades_for_learning = getattr(config, "MIN_TRADES_FOR_LEARNING", 3)

    def analyze_performance(self):
        """
        Analyze past trade history to evaluate wins, losses, and trends.
        Reconstructs PnL dynamically using FIFO accounting if columns are missing.
        Returns:
            metrics: dict with symbol -> performance statistics
        """
        metrics = {}
        try:
            trades = load_trade_history()
            if not trades:
                return metrics

            # Group all executions by symbol
            symbol_history = {}
            for t in trades:
                symbol = t.get("symbol", "").upper()
                if not symbol:
                    continue
                if symbol not in symbol_history:
                    symbol_history[symbol] = []
                symbol_history[symbol].append(t)

            symbol_trades = {}
            for symbol, t_list in symbol_history.items():
                # Parse timestamps and sort chronological
                t_list_sorted = []
                for t in t_list:
                    ts_str = t.get("timestamp", "")
                    try:
                        dt = datetime.fromisoformat(ts_str)
                    except ValueError:
                        dt = datetime.now()
                    t_copy = t.copy()
                    t_copy["dt"] = dt
                    t_list_sorted.append(t_copy)
                
                t_list_sorted.sort(key=lambda x: x["dt"])
                
                # FIFO matching queue
                buy_queue = []
                completed_sells = []
                
                for t in t_list_sorted:
                    side = t.get("side", "").upper()
                    try:
                        price = float(t.get("price", 0))
                        qty = float(t.get("quantity", 0))
                    except (ValueError, TypeError):
                        continue
                        
                    if side == "BUY":
                        buy_queue.append({"qty": qty, "price": price})
                    elif side == "SELL":
                        pnl_val = t.get("pnl")
                        
                        # Fallback FIFO calculation if PnL is missing in log
                        if pnl_val in (None, ""):
                            matched_buys_val = 0.0
                            matched_qty = 0.0
                            needed_qty = qty
                            
                            while needed_qty > 0 and buy_queue:
                                earliest_buy = buy_queue[0]
                                if earliest_buy["qty"] <= needed_qty:
                                    matched_buys_val += earliest_buy["qty"] * earliest_buy["price"]
                                    matched_qty += earliest_buy["qty"]
                                    needed_qty -= earliest_buy["qty"]
                                    buy_queue.pop(0)
                                else:
                                    matched_buys_val += needed_qty * earliest_buy["price"]
                                    matched_qty += needed_qty
                                    earliest_buy["qty"] -= needed_qty
                                    needed_qty = 0
                                    
                            if matched_qty > 0:
                                avg_entry = matched_buys_val / matched_qty
                                pnl = qty * (price - avg_entry)
                            else:
                                pnl = 0.0
                        else:
                            try:
                                pnl = float(pnl_val)
                            except (ValueError, TypeError):
                                pnl = 0.0
                            
                        completed_sells.append({
                            "pnl": pnl,
                            "dt": t["dt"],
                            "price": price,
                            "quantity": qty
                        })
                
                if completed_sells:
                    symbol_trades[symbol] = completed_sells

            # Calculate stats for each symbol
            for symbol, t_list in symbol_trades.items():
                # Sort by date (oldest to newest)
                t_list.sort(key=lambda x: x["dt"])

                total_trades = len(t_list)
                wins = [t for t in t_list if t["pnl"] > 0]
                losses = [t for t in t_list if t["pnl"] < 0]
                
                win_rate = len(wins) / total_trades if total_trades > 0 else 1.0
                total_pnl = sum(t["pnl"] for t in t_list)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

                # Count consecutive losses (from newest back to oldest)
                consecutive_losses = 0
                for t in reversed(t_list):
                    if t["pnl"] < 0:
                        consecutive_losses += 1
                    else:
                        break

                # Get latest trade date
                latest_trade_dt = t_list[-1]["dt"] if t_list else datetime.now()

                metrics[symbol] = {
                    "total_trades": total_trades,
                    "wins_count": len(wins),
                    "losses_count": len(losses),
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl,
                    "consecutive_losses": consecutive_losses,
                    "latest_trade_date": latest_trade_dt
                }

        except Exception as e:
            logger.error(f"Error during self-learning analysis: {e}")

        return metrics

    def is_blacklisted(self, symbol):
        """
        Check if a stock is placed on the cooling-off blacklist due to recent losses.
        Returns:
            bool: True if blacklisted, False otherwise
        """
        symbol = symbol.upper()
        metrics = self.analyze_performance()
        
        if symbol not in metrics:
            return False

        stats = metrics[symbol]
        
        # Rule 1: High number of consecutive losses
        if stats["consecutive_losses"] >= self.consecutive_loss_limit:
            # Check if cooling-off window is still active
            co_limit = timedelta(days=self.cooling_off_days)
            if datetime.now() - stats["latest_trade_date"] < co_limit:
                logger.warning(
                    f"[Self-Learning Sentry] {symbol} is blacklisted. "
                    f"Hit {stats['consecutive_losses']} consecutive losses on {stats['latest_trade_date'].strftime('%Y-%m-%d')}. "
                    f"Cooling-off active for {self.cooling_off_days} days."
                )
                return True

        # Rule 2: Low overall win rate
        if stats["total_trades"] >= self.min_trades_for_learning and stats["win_rate"] < self.min_win_rate:
            co_limit = timedelta(days=self.cooling_off_days)
            if datetime.now() - stats["latest_trade_date"] < co_limit:
                logger.warning(
                    f"[Self-Learning Sentry] {symbol} is blacklisted. "
                    f"Win rate too low: {stats['win_rate']*100:.1f}% (Minimum: {self.min_win_rate*100:.0f}%). "
                    f"Cooling-off active."
                )
                return True

        return False

    def get_sizing_multiplier(self, symbol):
        """
        Compute custom position scaling factor based on performance.
        Returns:
            float: Sizing multiplier between 0.0 and 1.2
        """
        symbol = symbol.upper()
        if self.is_blacklisted(symbol):
            return 0.0

        metrics = self.analyze_performance()
        if symbol not in metrics:
            return 1.0  # Default sizing for untested stocks

        stats = metrics[symbol]
        
        # Scale only if we have sufficient learning sample size
        if stats["total_trades"] < self.min_trades_for_learning:
            return 1.0

        # Highly profitable stock: boost priority
        if stats["win_rate"] >= 0.60 and stats["total_pnl"] > 0:
            return 1.2

        # Poorly performing stock: restrict size
        if stats["win_rate"] <= 0.40 or stats["total_pnl"] < 0:
            return 0.5

        return 1.0

    def get_learning_summary(self):
        """Build summary report of learned behaviors"""
        metrics = self.analyze_performance()
        summary = {
            "total_analyzed": len(metrics),
            "blacklisted": [],
            "boosted": [],
            "penalized": [],
            "details": {}
        }

        for symbol, stats in metrics.items():
            multiplier = self.get_sizing_multiplier(symbol)
            is_bl = self.is_blacklisted(symbol)

            summary_item = {
                "trades": stats["total_trades"],
                "win_rate": f"{stats['win_rate']*100:.1f}%",
                "pnl": f"${stats['total_pnl']:+.2f}",
                "consecutive_losses": stats["consecutive_losses"],
                "multiplier": f"{multiplier}x",
                "status": "BLACKLISTED" if is_bl else "BOOSTED" if multiplier > 1.0 else "PENALIZED" if multiplier < 1.0 else "NORMAL"
            }

            summary["details"][symbol] = summary_item

            if is_bl:
                summary["blacklisted"].append(symbol)
            elif multiplier > 1.0:
                summary["boosted"].append(symbol)
            elif multiplier < 1.0:
                summary["penalized"].append(symbol)

        return summary
