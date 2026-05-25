"""
Multi-Regime Volatility Stress Injector & Monte Carlo Simulator
Supports historical shock periods (2008, COVID, 2022, Volmageddon)
and injects realistic execution slippage, random rejections, and bootstrap re-sampling.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backtester import BacktestEngine, MockIBConnection
from utils import calculate_transaction_cost, get_logger

logger = get_logger("backtest_stress")


class StressMockIBConnection(MockIBConnection):
    """
    Hardened mock broker connection simulating execution failures,
    severe slippage, and random order rejections.
    """

    def __init__(
        self,
        starting_cash: float = 10000.0,
        slippage_shock_pct: float = 0.5,  # 0.5% average slippage shock
        order_reject_rate: float = 0.05,  # 5% order rejection rate
    ):
        super().__init__(starting_cash)
        self.slippage_shock_pct = slippage_shock_pct / 100.0
        self.order_reject_rate = order_reject_rate

    def place_order(self, symbol: str, side: str, quantity: float, order_type: str = "LMT", limit_price: float = 0.0, metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        trade_date = metadata.get("date") if metadata else "UNKNOWN"

        # 1. Simulate Broker Order Rejections / Queue Drops
        if random.random() < self.order_reject_rate:
            logger.warning("[%s] [Stress Mock] ORDER REJECTED: Network timeout/Broker queue dropped for %s", trade_date, symbol)
            return None

        # 2. Simulate Volatility-Induced Slippage Shock
        slippage_mult = random.uniform(0.1, 2.5) * self.slippage_shock_pct
        if side.upper() == "BUY":
            slipped_price = round(limit_price * (1.0 + slippage_mult), 2)
        else:
            slipped_price = round(limit_price * (1.0 - slippage_mult), 2)

        # 3. Process execution
        fee = calculate_transaction_cost(quantity, slipped_price, side)
        trade_value = quantity * slipped_price

        if side.upper() == "BUY":
            total_cost = trade_value + fee
            if total_cost > self.cash:
                logger.warning("[%s] [Stress Mock] BUY Rejected: Insufficient cash (Need $%.2f, Have $%.2f)", trade_date, total_cost, self.cash)
                return None

            self.cash -= total_cost
            if symbol in self.positions:
                old_qty = self.positions[symbol]['quantity']
                old_cost = self.positions[symbol]['avg_cost']
                new_qty = old_qty + quantity
                new_cost = ((old_cost * old_qty) + (slipped_price * quantity)) / new_qty
                self.positions[symbol] = {'quantity': new_qty, 'avg_cost': new_cost}
            else:
                self.positions[symbol] = {'quantity': quantity, 'avg_cost': slipped_price}

        elif side.upper() == "SELL":
            if symbol not in self.positions:
                return None

            qty_held = self.positions[symbol]['quantity']
            qty_to_sell = min(quantity, qty_held)
            self.cash += (qty_to_sell * slipped_price) - fee

            if qty_to_sell == qty_held:
                del self.positions[symbol]
            else:
                self.positions[symbol]['quantity'] -= qty_to_sell

        trade_record = {
            "date": trade_date,
            "symbol": symbol,
            "side": side.upper(),
            "quantity": quantity,
            "price": slipped_price,
            "fee": fee,
            "total_value": trade_value,
            "slippage_applied_pct": round(slippage_mult * 100.0, 3)
        }
        self.trades.append(trade_record)
        return 200000 + len(self.trades)


class StressBacktestEngine(BacktestEngine):
    """
    Advanced Stress backtesting engine supporting custom shock periods and Monte Carlo simulation.
    """

    CRISIS_PERIODS = {
        "2008_CRISIS": ("2008-01-01", "2009-03-01"),
        "2010_FLASH_CRASH": ("2010-04-15", "2010-05-15"),
        "2018_VOLMAGEDDON": ("2018-01-25", "2018-03-01"),
        "2020_COVID": ("2020-02-15", "2020-04-15"),
        "2022_BEAR": ("2022-01-01", "2022-12-31")
    }

    def __init__(
        self,
        tickers: List[str],
        regime_name: str,
        starting_cash: float = 10000.0,
        slippage_shock_pct: float = 0.5,
        order_reject_rate: float = 0.05
    ):
        if regime_name not in self.CRISIS_PERIODS:
            raise ValueError(f"Unknown stress regime: {regime_name}. Available: {list(self.CRISIS_PERIODS.keys())}")
        
        start, end = self.CRISIS_PERIODS[regime_name]
        super().__init__(tickers, start, end, starting_cash)
        self.regime_name = regime_name
        self.slippage_shock_pct = slippage_shock_pct
        self.order_reject_rate = order_reject_rate

    def run(self, strategy_class, model_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Execute the backtest on the configured historical shock timeline, using the stress mock connections.
        """
        if not self.historical_data:
            self.load_data()

        # Get intersection of dates where we have data
        all_dates = []
        for df in self.historical_data.values():
            all_dates.extend(df.index.tolist())
        all_dates = sorted(list(set(all_dates)))

        sim_dates = [d for d in all_dates if self.start_date <= d <= self.end_date]
        if not sim_dates:
            logger.error("No simulated overlap dates found for stress period %s", self.regime_name)
            return None

        logger.info("[Stress Injector] Starting STRESS simulation [%s] from %s to %s",
                    self.regime_name, sim_dates[0].strftime('%Y-%m-%d'), sim_dates[-1].strftime('%Y-%m-%d'))

        # Instantiate stress mocks
        self.ib_mock = StressMockIBConnection(self.starting_cash, self.slippage_shock_pct, self.order_reject_rate)
        self.data_fetcher_mock = self.data_fetcher_mock or self.historical_data
        
        # We manually build the core logic using parents loop but substituting our stress mock
        # Let's bypass to parents logic, but set our custom ib_mock first.
        # BacktestEngine.run does: self.ib_mock = MockIBConnection(self.starting_cash)
        # We override run to inject our custom IBMock.
        
        # To do this safely and cleanly, we temporarily monkeypatch MockIBConnection in backtester module!
        import backtester
        original_mock_class = backtester.MockIBConnection
        backtester.MockIBConnection = lambda cash: StressMockIBConnection(cash, self.slippage_shock_pct, self.order_reject_rate)
        
        try:
            results = super().run(strategy_class, model_type)
        finally:
            # Restore class definition
            backtester.MockIBConnection = original_mock_class

        if results:
            results["regime_name"] = self.regime_name
            results["monte_carlo"] = self.run_monte_carlo(results["trade_history"])
            
        return results

    def run_monte_carlo(self, trades: List[Dict[str, Any]], iterations: int = 1000) -> Dict[str, Any]:
        """
        Run bootstrap Monte Carlo trade re-sampling.
        Estimates tail risk, ruin probability, and worst-case drawdowns.
        """
        if not trades:
            return {"drawdown_percentiles": {}, "ruin_probability": 0.0, "worst_case_drawdown_pct": 0.0}

        # Calculate trade PnL array
        # We match BUYs and SELLs as closed round-trip PnLs
        pnls = []
        buy_prices = {}
        for t in trades:
            sym = t['symbol']
            side = t['side']
            price = t['price']
            qty = t['quantity']
            fee = t['fee']

            if side == 'BUY':
                buy_prices[sym] = buy_prices.get(sym, []) + [(price, fee)] * int(qty)
            elif side == 'SELL':
                if sym in buy_prices and buy_prices[sym]:
                    matching_buys = buy_prices[sym][:int(qty)]
                    buy_prices[sym] = buy_prices[sym][int(qty):]
                    avg_buy = np.mean([b[0] for b in matching_buys])
                    buy_fees = sum([b[1] for b in matching_buys])
                    profit = (price - avg_buy) * qty - fee - buy_fees
                    pnls.append(profit)

        if not pnls:
            return {"drawdown_percentiles": {}, "ruin_probability": 0.0, "worst_case_drawdown_pct": 0.0}

        pnl_array = np.array(pnls)
        simulated_drawdowns = []
        ruin_events = 0
        ruin_barrier = self.starting_cash * 0.20  # 80% drawdown ruin threshold

        for _ in range(iterations):
            # Bootstrap shuffle trades with replacement
            shuffled = np.random.choice(pnl_array, size=len(pnl_array), replace=True)
            equity_curve = self.starting_cash + np.cumsum(shuffled)
            
            # Check ruin
            if np.any(equity_curve < ruin_barrier):
                ruin_events += 1

            # Drawdown calculation
            peaks = np.maximum.accumulate(equity_curve)
            drawdowns = (equity_curve - peaks) / peaks * 100.0
            simulated_drawdowns.append(drawdowns.min())

        simulated_drawdowns = np.array(simulated_drawdowns)
        ruin_prob = (ruin_events / iterations) * 100.0

        return {
            "ruin_probability_pct": ruin_prob,
            "worst_case_drawdown_pct": float(simulated_drawdowns.min()),
            "drawdown_percentiles": {
                "50th": float(np.percentile(simulated_drawdowns, 50)),
                "95th": float(np.percentile(simulated_drawdowns, 95)),
                "99th": float(np.percentile(simulated_drawdowns, 99)),
            }
        }
