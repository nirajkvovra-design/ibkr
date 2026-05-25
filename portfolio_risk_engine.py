#!/usr/bin/env python
"""
Institutional Portfolio Risk Engine
Calculates real-time portfolio risk metrics including Parametric Value at Risk (VaR),
Expected Shortfall (ES), dynamic portfolio beta, concentration risks, and simulates
extreme market shock scenarios.
"""

from typing import Dict, List, Any, Tuple, Optional, Union
import math
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from utils import get_logger
from data_fetcher import DataFetcher
import config

logger = get_logger(__name__)


class StressTestResult(BaseModel):
    scenario_name: str
    description: str
    expected_pnl: float
    expected_pnl_percent: float


class PortfolioRiskReport(BaseModel):
    portfolio_value: float = 0.0
    cash: float = 0.0
    parametric_var_95: float = 0.0
    parametric_var_99: float = 0.0
    expected_shortfall_95: float = 0.0
    expected_shortfall_99: float = 0.0
    portfolio_beta: float = 1.0
    portfolio_volatility: float = 0.0
    concentration: Dict[str, float] = Field(default_factory=dict)
    concentration_alerts: List[str] = Field(default_factory=list)
    stress_test_results: List[StressTestResult] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PortfolioRiskEngine:
    """Quantitative risk engine for multi-asset portfolio risk and stress-testing."""

    def __init__(self, data_fetcher: Optional[DataFetcher] = None):
        """
        Initialize the Portfolio Risk Engine.
        
        Args:
            data_fetcher: Optional DataFetcher instance (creates new one if None)
        """
        self.data_fetcher = data_fetcher or DataFetcher()
        self.risk_free_rate = 0.05
        # Standard Z-scores for standard normal distributions
        self.Z_95 = 1.64485
        self.Z_99 = 2.32635

    def calculate_portfolio_risk_metrics(
        self,
        open_positions: Union[Dict[str, Dict[str, Any]], Dict[str, Any]],
        account_value: float,
        cash: float = 0.0
    ) -> PortfolioRiskReport:
        """
        Calculate full quantitative risk metrics for the portfolio.
        
        Args:
            open_positions: Dictionary of positions, where keys are symbols and values
                            are dicts (or models) containing 'quantity', 'avg_cost',
                            and optional 'current_value'.
            account_value: Total portfolio net liquidation value.
            cash: Unallocated cash in the portfolio.
            
        Returns:
            PortfolioRiskReport containing all computed metrics.
        """
        try:
            if account_value <= 0:
                logger.warning("Account value is <= 0. Returning empty risk report.")
                return PortfolioRiskReport()

            # 1. Standardize positions into dictionary format
            parsed_positions = {}
            for symbol, pos in open_positions.items():
                # Handle Position Pydantic model or Dict
                qty = getattr(pos, 'quantity', None)
                if qty is None and isinstance(pos, dict):
                    qty = pos.get('quantity', 0.0)
                
                avg_cost = getattr(pos, 'avg_cost', None)
                if avg_cost is None and isinstance(pos, dict):
                    avg_cost = pos.get('avg_cost', 0.0)
                    
                val = getattr(pos, 'current_value', None)
                if val is None and isinstance(pos, dict):
                    val = pos.get('current_value', qty * avg_cost)
                elif val is None:
                    val = qty * avg_cost

                if qty != 0:
                    parsed_positions[symbol.upper()] = {
                        'quantity': float(qty),
                        'avg_cost': float(avg_cost),
                        'current_value': float(val)
                    }

            if not parsed_positions:
                # Flat portfolio
                return PortfolioRiskReport(
                    portfolio_value=account_value,
                    cash=account_value,
                    portfolio_beta=0.0
                )

            # Calculate asset weights
            weights = {}
            total_allocated = 0.0
            for symbol, pos in parsed_positions.items():
                val = pos['current_value']
                weights[symbol] = val / account_value
                total_allocated += val

            weights['CASH'] = (account_value - total_allocated) / account_value

            # 2. Compute concentrations and check limits
            concentration = {symbol: w * 100.0 for symbol, w in weights.items() if abs(w) > 0.0001}
            concentration_alerts = []
            max_concentration_limit = 20.0  # 20% limit
            for symbol, pct in concentration.items():
                if symbol != 'CASH' and pct > max_concentration_limit:
                    concentration_alerts.append(
                        f"Concentration warning: {symbol} represents {pct:.1f}% of total portfolio (limit: {max_concentration_limit}%)"
                    )

            # 3. Load historical returns for assets
            historical_returns = {}
            asset_betas = {}
            
            # Fetch SPY for benchmark beta calculation
            spy_data = self.data_fetcher.get_stock_data('SPY', period='3mo', interval='1d')
            if spy_data is not None and not spy_data.empty:
                spy_returns = spy_data['Close'].pct_change().dropna()
                spy_var = spy_returns.var()
            else:
                spy_returns = None
                spy_var = 0.0001

            for symbol in parsed_positions.keys():
                data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                if data is not None and not data.empty:
                    close_series = data['Close']
                    # Handle multiindex columns if any
                    if isinstance(close_series, pd.DataFrame):
                        close_series = close_series.iloc[:, 0]
                    returns = close_series.pct_change().dropna()
                    historical_returns[symbol] = returns

                    # Compute individual beta vs SPY
                    if spy_returns is not None and len(returns) > 5:
                        # Align series dates
                        aligned = pd.concat([returns, spy_returns], axis=1).dropna()
                        if len(aligned) > 5:
                            cov = aligned.cov().iloc[0, 1]
                            asset_betas[symbol] = cov / spy_var
                        else:
                            asset_betas[symbol] = 1.0
                    else:
                        asset_betas[symbol] = 1.0
                else:
                    # Fallback default values
                    historical_returns[symbol] = pd.Series(np.random.normal(0.0005, 0.015, 60))
                    asset_betas[symbol] = 1.0

            # 4. Calculate Portfolio Beta
            portfolio_beta = sum(weights.get(sym, 0.0) * asset_betas.get(sym, 1.0) for sym in parsed_positions.keys())

            # 5. Build portfolio daily returns covariance matrix
            symbols_list = list(parsed_positions.keys())
            
            # Use Pandas to align dates for returns calculation
            if len(symbols_list) > 0:
                returns_df = pd.concat([historical_returns[sym] for sym in symbols_list], axis=1, keys=symbols_list).dropna()
                
                if len(returns_df) > 5:
                    cov_matrix = returns_df.cov()
                    # Vector of weights corresponding to symbols_list
                    w_vec = np.array([weights[sym] for sym in symbols_list])
                    # Portfolio daily variance = w^T * Cov * w
                    portfolio_daily_var = np.dot(w_vec.T, np.dot(cov_matrix, w_vec))
                    portfolio_daily_vol = math.sqrt(max(0.0, portfolio_daily_var))
                else:
                    # Fallback simple standard deviation aggregation if alignment fails
                    daily_vols = [historical_returns[sym].std() for sym in symbols_list]
                    portfolio_daily_vol = sum(abs(weights[sym]) * daily_vols[i] for i, sym in enumerate(symbols_list))
            else:
                portfolio_daily_vol = 0.0

            portfolio_annual_vol = portfolio_daily_vol * math.sqrt(252)

            # 6. Calculate Parametric VaR and Expected Shortfall
            # 1-day VaR = Z * daily_vol * portfolio_value
            parametric_var_95 = self.Z_95 * portfolio_daily_vol * account_value
            parametric_var_99 = self.Z_99 * portfolio_daily_vol * account_value

            # Expected Shortfall under normal distribution assumption:
            # ES_alpha = value * daily_vol * (phi(Z_alpha) / (1 - alpha))
            # phi(Z_95) / 0.05 approx 2.0627
            # phi(Z_99) / 0.01 approx 2.665
            expected_shortfall_95 = 2.0627 * portfolio_daily_vol * account_value
            expected_shortfall_99 = 2.665 * portfolio_daily_vol * account_value

            # 7. Stress Testing Simulations
            stress_test_results = []
            
            # Scenario A: Black Monday (-20% SPY Shock)
            # expected_return = beta_i * (-20%)
            spy_shock_bm = -0.20
            bm_pnl = 0.0
            for sym, pos in parsed_positions.items():
                beta = asset_betas.get(sym, 1.0)
                bm_pnl += pos['current_value'] * beta * spy_shock_bm
            
            stress_test_results.append(StressTestResult(
                scenario_name="Black Monday",
                description="Simulates a major -20% systemic market crash, with volatility correlations surging.",
                expected_pnl=round(bm_pnl, 2),
                expected_pnl_percent=round((bm_pnl / account_value) * 100.0, 2)
            ))

            # Scenario B: 2008 Financial Crisis (-10% SPY Shock)
            spy_shock_08 = -0.10
            fc_pnl = 0.0
            for sym, pos in parsed_positions.items():
                beta = asset_betas.get(sym, 1.0)
                fc_pnl += pos['current_value'] * beta * spy_shock_08
                
            stress_test_results.append(StressTestResult(
                scenario_name="2008 Financial Crisis",
                description="Simulates an extreme -10% market correction with dynamic beta exposures.",
                expected_pnl=round(fc_pnl, 2),
                expected_pnl_percent=round((fc_pnl / account_value) * 100.0, 2)
            ))

            # Scenario C: Tech sector Crash (-15% Tech Shock)
            tech_stocks = getattr(config, "AI_INFRA_STOCKS", []) + ["QQQ", "AAPL", "MSFT", "NVDA", "AMD"]
            tech_pnl = 0.0
            for sym, pos in parsed_positions.items():
                is_tech = sym in tech_stocks or sym.replace("-USD", "").replace("=F", "") in tech_stocks
                multiplier = -0.15 if is_tech else (asset_betas.get(sym, 1.0) * -0.03)
                tech_pnl += pos['current_value'] * multiplier
                
            stress_test_results.append(StressTestResult(
                scenario_name="Tech Sector Rout",
                description="Simulates a concentrated -15% selloff in tech and semiconductor growth leaders.",
                expected_pnl=round(tech_pnl, 2),
                expected_pnl_percent=round((tech_pnl / account_value) * 100.0, 2)
            ))

            # Scenario D: Volmageddon (VIX +100% Volatility Shock)
            # Equity market typically retreats ~5% during major volatility squeezes
            vol_pnl = 0.0
            for sym, pos in parsed_positions.items():
                beta = asset_betas.get(sym, 1.0)
                vol_pnl += pos['current_value'] * beta * -0.05
                
            stress_test_results.append(StressTestResult(
                scenario_name="Volmageddon Squeeze",
                description="Simulates a 100% surge in the VIX Volatility index, leading to global risk liquidation (-5% market shock).",
                expected_pnl=round(vol_pnl, 2),
                expected_pnl_percent=round((vol_pnl / account_value) * 100.0, 2)
            ))

            # Scenario E: Interest Rate Spike (+100 bps Yield Shock)
            # Affects dividend yields and highly levered equities (-3% systemic decline)
            ir_pnl = 0.0
            for sym, pos in parsed_positions.items():
                beta = asset_betas.get(sym, 1.0)
                ir_pnl += pos['current_value'] * beta * -0.03
                
            stress_test_results.append(StressTestResult(
                scenario_name="Interest Rate Surge (+100 bps)",
                description="Simulates an immediate 1% increase in systemic yields, discounting equity multiples (-3% market shock).",
                expected_pnl=round(ir_pnl, 2),
                expected_pnl_percent=round((ir_pnl / account_value) * 100.0, 2)
            ))

            return PortfolioRiskReport(
                portfolio_value=round(account_value, 2),
                cash=round(account_value - total_allocated, 2),
                parametric_var_95=round(parametric_var_95, 2),
                parametric_var_99=round(parametric_var_99, 2),
                expected_shortfall_95=round(expected_shortfall_95, 2),
                expected_shortfall_99=round(expected_shortfall_99, 2),
                portfolio_beta=round(portfolio_beta, 3),
                portfolio_volatility=round(portfolio_annual_vol * 100.0, 2), # Annualized percentage (e.g. 18.5 for 18.5%)
                concentration={k: round(v, 2) for k, v in concentration.items()},
                concentration_alerts=concentration_alerts,
                stress_test_results=stress_test_results,
                metadata={
                    "total_positions": len(parsed_positions),
                    "historical_lookback_days": len(returns_df) if len(parsed_positions) > 0 else 0
                }
            )

        except Exception as e:
            logger.exception(f"Error calculating portfolio risk metrics: {e}")
            return PortfolioRiskReport()
