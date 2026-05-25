#!/usr/bin/env python
"""
Options Intelligence Engine
Institutional-grade quantitative analytics for derivative contracts.
Features:
1. Black-Scholes-Merton Pricing Model for Call and Put options.
2. Analytic calculation of Option Greeks (Delta, Gamma, Vega, Theta, Rho).
3. Numerical Implied Volatility (IV) solver using the Newton-Raphson method.
4. Volatility metrics: Implied Volatility Rank and Percentile.
5. Probability of Profit (PoP) & Break-even calculations for synthetic setups.
"""

from typing import Dict, List, Tuple, Union, Optional
import math
import numpy as np
from utils import get_logger

logger = get_logger(__name__)


def norm_pdf(x: float) -> float:
    """Standard normal probability density function (PDF)."""
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)


def norm_cdf(x: float) -> float:
    """
    Standard normal cumulative distribution function (CDF).
    Uses the highly accurate Abramowitz and Stegun approximation (error < 7.5e-8).
    """
    if x < 0.0:
        return 1.0 - norm_cdf(-x)
        
    # constants
    p = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    
    t = 1.0 / (1.0 + p * x)
    # Horner's method for polynomial evaluation
    poly = t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))))
    pdf = math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)
    
    return 1.0 - pdf * poly


class OptionsIntelligenceEngine:
    """Quantitative options valuation and risk analytics engine."""

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize the options intelligence engine.
        
        Args:
            risk_free_rate: Annualized risk-free interest rate (default: 5% / 0.05)
        """
        self.risk_free_rate = risk_free_rate

    @staticmethod
    def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> Tuple[float, float]:
        """Calculate d1 and d2 components of the Black-Scholes formula."""
        if T <= 0:
            T = 1e-6  # Prevent division by zero for expired options
        if sigma <= 0:
            sigma = 1e-6
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return float(d1), float(d2)

    def calculate_price(
        self,
        symbol: str,
        strike: float,
        days_to_expiry: float,
        underlying_price: float,
        volatility: float,
        option_type: str = "CALL"
    ) -> float:
        """
        Calculate the Black-Scholes-Merton theoretical price of an option.
        
        Args:
            symbol: Ticker symbol of underlying asset
            strike: Strike price (K)
            days_to_expiry: Days remaining until expiration
            underlying_price: Current price of the underlying asset (S)
            volatility: Annualized implied volatility (sigma, e.g., 0.25 for 25%)
            option_type: 'CALL' or 'PUT'
            
        Returns:
            Theoretical option price (USD)
        """
        try:
            S = float(underlying_price)
            K = float(strike)
            T = float(days_to_expiry) / 365.0  # Annualized time to expiry
            r = self.risk_free_rate
            sigma = float(volatility)
            opt_type = option_type.upper()

            if T <= 0:
                # Intrinsic value at expiration
                if opt_type == "CALL":
                    return max(0.0, S - K)
                else:
                    return max(0.0, K - S)

            d1, d2 = self._d1_d2(S, K, T, r, sigma)

            if opt_type == "CALL":
                price = S * norm_cdf(d1) - K * np.exp(-r * T) * norm_cdf(d2)
            elif opt_type == "PUT":
                price = K * np.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
            else:
                raise ValueError("option_type must be either 'CALL' or 'PUT'")

            return float(max(0.01, price))

        except Exception as e:
            logger.error("Error calculating Black-Scholes price for %s: %s", symbol, e)
            return 0.0

    def calculate_greeks(
        self,
        symbol: str,
        strike: float,
        days_to_expiry: float,
        underlying_price: float,
        volatility: float,
        option_type: str = "CALL"
    ) -> Dict[str, float]:
        """
        Analytically calculate standard Option Greeks (Delta, Gamma, Vega, Theta, Rho).
        
        Returns:
            Dict containing Delta, Gamma, Vega, Theta, and Rho values.
        """
        try:
            S = float(underlying_price)
            K = float(strike)
            T = float(days_to_expiry) / 365.0
            r = self.risk_free_rate
            sigma = float(volatility)
            opt_type = option_type.upper()

            if T <= 0:
                T = 1e-6

            d1, d2 = self._d1_d2(S, K, T, r, sigma)

            # Cumulative and probability density distributions
            n_d1 = norm_pdf(d1)
            N_d1 = norm_cdf(d1)
            N_d2 = norm_cdf(d2)

            # Delta (change in option price per $1 change in stock)
            if opt_type == "CALL":
                delta = N_d1
            else:
                delta = N_d1 - 1.0

            # Gamma (acceleration of Delta per $1 change in stock)
            gamma = n_d1 / (S * sigma * np.sqrt(T))

            # Vega (sensitivity of option price per 1% change in IV)
            vega = S * np.sqrt(T) * n_d1 / 100.0

            # Theta (daily time decay of option price, annualized / 365)
            theta_call = (- (S * n_d1 * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * N_d2) / 365.0
            theta_put = (- (S * n_d1 * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm_cdf(-d2)) / 365.0
            theta = theta_call if opt_type == "CALL" else theta_put

            # Rho (sensitivity of option price per 1% change in interest rates)
            if opt_type == "CALL":
                rho = K * T * np.exp(-r * T) * N_d2 / 100.0
            else:
                rho = -K * T * np.exp(-r * T) * norm_cdf(-d2) / 100.0

            return {
                "delta": float(delta),
                "gamma": float(gamma),
                "vega": float(vega),
                "theta": float(theta),
                "rho": float(rho)
            }

        except Exception as e:
            logger.error("Error calculating Greeks for %s: %s", symbol, e)
            return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

    def calculate_implied_volatility(
        self,
        symbol: str,
        strike: float,
        days_to_expiry: float,
        underlying_price: float,
        option_price: float,
        option_type: str = "CALL",
        max_iterations: int = 100,
        precision: float = 1e-5
    ) -> float:
        """
        Solve for Implied Volatility (IV) using the Newton-Raphson numerical search method.
        Falls back to Bisection search if derivative (Vega) approaches zero.
        """
        try:
            S = float(underlying_price)
            K = float(strike)
            T = float(days_to_expiry) / 365.0
            r = self.risk_free_rate
            market_price = float(option_price)
            opt_type = option_type.upper()

            # Intrinsic value floor
            intrinsic_value = max(0.0, S - K) if opt_type == "CALL" else max(0.0, K - S)
            if market_price <= intrinsic_value:
                return 0.0001  # Option is trading under parity, minimum IV

            # Initial guess: standard ATM straddle volatility approximation
            sigma = 0.50

            for _ in range(max_iterations):
                theoretical_price = self.calculate_price(symbol, K, days_to_expiry, S, sigma, opt_type)
                diff = theoretical_price - market_price

                if abs(diff) < precision:
                    return float(sigma)

                greeks = self.calculate_greeks(symbol, K, days_to_expiry, S, sigma, opt_type)
                vega = greeks["vega"] * 100.0  # Convert back to standard vega unit for dPrice / dSigma

                if abs(vega) < 1e-4:
                    # Fall back to bisection search in extremely low vega zones (deep ITM/OTM)
                    break
                
                # Newton step: sigma_new = sigma - f(sigma) / f'(sigma)
                step = diff / vega
                sigma -= step

                # Keep volatility bounded inside realistic zones [0.1%, 500%]
                sigma = np.clip(sigma, 0.001, 5.0)

            # Bisection Method fallback
            low = 0.001
            high = 5.0
            for _ in range(100):
                sigma = 0.5 * (low + high)
                theoretical_price = self.calculate_price(symbol, K, days_to_expiry, S, sigma, opt_type)
                diff = theoretical_price - market_price

                if abs(diff) < precision:
                    return float(sigma)

                if diff > 0:
                    high = sigma
                else:
                    low = sigma

            return float(sigma)

        except Exception as e:
            logger.error("Error solving IV for %s: %s", symbol, e)
            return 0.25  # Fallback to standard market volatility index baseline

    @staticmethod
    def calculate_iv_rank_and_percentile(
        current_iv: float,
        historical_ivs: Union[List[float], np.ndarray]
    ) -> Tuple[float, float]:
        """
        Calculate Implied Volatility (IV) Rank and Percentile against historical IV data.
        
        Args:
            current_iv: Current Implied Volatility (e.g., 0.32)
            historical_ivs: List or array of historical IV data points over lookback period (e.g. 1 year)
            
        Returns:
            iv_rank: Value between 0 and 100 representing position relative to high/low bounds.
            iv_percentile: Value between 0 and 100 representing percentage of days below current IV.
        """
        try:
            ivs = np.array(historical_ivs)
            if len(ivs) == 0:
                return 50.0, 50.0

            min_iv = float(np.min(ivs))
            max_iv = float(np.max(ivs))

            # 1. IV Rank
            if max_iv == min_iv:
                iv_rank = 50.0
            else:
                iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100.0

            # 2. IV Percentile
            days_below = np.sum(ivs < current_iv)
            iv_percentile = (days_below / len(ivs)) * 100.0

            return float(np.clip(iv_rank, 0.0, 100.0)), float(np.clip(iv_percentile, 0.0, 100.0))

        except Exception as e:
            logger.error("Error calculating IV rank/percentile: %s", e)
            return 50.0, 50.0

    def calculate_probability_of_profit(
        self,
        current_price: float,
        days_to_expiry: float,
        volatility: float,
        lower_break_even: Optional[float] = None,
        upper_break_even: Optional[float] = None
    ) -> float:
        """
        Calculate the Probability of Profit (PoP) for an options position.
        Uses a standard normal log-distribution with drift diffusion logic.
        
        Args:
            current_price: Current stock price (S)
            days_to_expiry: Days until option expiration
            volatility: Annualized implied volatility (sigma)
            lower_break_even: Lower strike boundary of profitable range (None for uncapped downside)
            upper_break_even: Upper strike boundary of profitable range (None for uncapped upside)
            
        Returns:
            Probability of Profit as a percentage (e.g., 68.5 for 68.5%)
        """
        try:
            S = float(current_price)
            T = float(days_to_expiry) / 365.0
            sigma = float(volatility)
            r = self.risk_free_rate

            if T <= 0 or sigma <= 0:
                # Expired or zero volatility
                if lower_break_even and S < lower_break_even:
                    return 0.0
                if upper_break_even and S > upper_break_even:
                    return 0.0
                return 100.0

            # Compute standard deviation of log returns at expiry
            std_dev = sigma * np.sqrt(T)
            
            # Log drift component
            drift = (r - 0.5 * sigma ** 2) * T

            # Probability of ending above lower break-even
            if lower_break_even and lower_break_even > 0:
                d_lower = (np.log(lower_break_even / S) - drift) / std_dev
                prob_above_lower = norm_cdf(-d_lower)
            else:
                prob_above_lower = 1.0

            # Probability of ending below upper break-even
            if upper_break_even and upper_break_even > 0:
                d_upper = (np.log(upper_break_even / S) - drift) / std_dev
                prob_below_upper = norm_cdf(d_upper)
            else:
                prob_below_upper = 1.0

            # Combined range probability
            if lower_break_even and upper_break_even:
                # Symmetrical spread logic: P(Lower < S_expiry < Upper)
                pop = (prob_above_lower + prob_below_upper - 1.0) * 100.0
            elif lower_break_even:
                # Bull Put / Long call: P(S_expiry > Lower)
                pop = prob_above_lower * 100.0
            elif upper_break_even:
                # Bear Call / Long put: P(S_expiry < Upper)
                pop = prob_below_upper * 100.0
            else:
                pop = 100.0

            return float(np.clip(pop, 0.0, 100.0))

        except Exception as e:
            logger.error("Error calculating Probability of Profit (PoP): %s", e)
            return 50.0
