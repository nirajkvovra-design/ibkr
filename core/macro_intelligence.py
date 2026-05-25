"""
Macro & Geopolitical Intelligence Engine (Phase 4)
Monitors cross-asset stress parameters (VIX, MOVE, OVX, GVZ),
classifies global macro regimes, and maintains the pre-event economic calendar sentry.
"""

from __future__ import annotations

from enum import Enum
import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from data_fetcher import DataFetcher
from news_sentiment import NewsSentiment
from utils import get_logger

logger = get_logger(__name__)


class MacroRegime(str, Enum):
    LOW_VOL_TREND = "LOW_VOL_TREND"
    HIGH_VOL_TREND = "HIGH_VOL_TREND"
    PANIC = "PANIC"
    GEOPOLITICAL_SHOCK = "GEOPOLITICAL_SHOCK"
    INFLATION_SHOCK = "INFLATION_SHOCK"
    LIQUIDITY_CRISIS = "LIQUIDITY_CRISIS"


class MacroIntelligenceEngine:
    """
    Quantitative Macro & Geopolitical Intelligence Layer.
    """

    def __init__(self, data_fetcher: Optional[DataFetcher] = None):
        self.data_fetcher = data_fetcher or DataFetcher()
        self.news_sentiment = NewsSentiment()
        
        # Volatility thresholds (normal, elevated, panic)
        self.VIX_ELEVATED = 20.0
        self.VIX_PANIC = 30.0
        self.MOVE_PANIC = 120.0  # Fixed-income volatility
        self.OVX_PANIC = 45.0    # Crude oil volatility
        
        # Mock economic calendar for event blackout gates (scheduled dates as ISO strings)
        # In production, this can be hydrated dynamically from an API.
        self.scheduled_fomc_dates: List[str] = []
        self.scheduled_cpi_dates: List[str] = []

    def register_scheduled_events(self, fomc_dates: List[str], cpi_dates: List[str]) -> None:
        """
        Hydrate the economic calendar sentry with scheduled FOMC and CPI announcement dates.
        Dates format: "YYYY-MM-DD"
        """
        self.scheduled_fomc_dates = fomc_dates
        self.scheduled_cpi_dates = cpi_dates
        logger.info("[Macro Sentry] Economic calendar loaded: %d FOMC dates, %d CPI dates registered.",
                    len(fomc_dates), len(cpi_dates))

    def check_pre_event_blackout(self, days_buffer: int = 1) -> Dict[str, Any]:
        """
        Evaluate if today falls within a pre-scheduled high-impact macro event window.
        Returns block flag and descriptions.
        """
        today = datetime.now().date()
        result = {
            "is_blocked": False,
            "reason": "",
            "event_type": None
        }

        # Check FOMC blackout
        for d_str in self.scheduled_fomc_dates:
            try:
                ev_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                days_diff = (ev_date - today).days
                if 0 <= days_diff <= days_buffer:
                    result["is_blocked"] = True
                    result["reason"] = f"Pre-scheduled FOMC Release in {days_diff} days on {d_str}"
                    result["event_type"] = "FOMC"
                    logger.warning("[Macro Sentry] PRE-EVENT BLACKOUT engaged: %s", result["reason"])
                    return result
            except ValueError:
                continue

        # Check CPI blackout
        for d_str in self.scheduled_cpi_dates:
            try:
                ev_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                days_diff = (ev_date - today).days
                if 0 <= days_diff <= days_buffer:
                    result["is_blocked"] = True
                    result["reason"] = f"Pre-scheduled CPI Release in {days_diff} days on {d_str}"
                    result["event_type"] = "CPI"
                    logger.warning("[Macro Sentry] PRE-EVENT BLACKOUT engaged: %s", result["reason"])
                    return result
            except ValueError:
                continue

        return result

    def get_cross_asset_volatility(self) -> Dict[str, float]:
        """
        Fetch real-time volatility index prices from yfinance or fallback to stable mock defaults.
        """
        vols = {
            "VIX": 15.0,   # S&P 500 Volatility
            "MOVE": 80.0,  # Treasury Volatility
            "OVX": 30.0,   # Crude Oil Volatility
            "GVZ": 18.0    # Gold Volatility
        }

        for symbol, default_val in list(vols.items()):
            try:
                # yfinance symbols require prefix carat
                yf_sym = f"^{symbol}"
                price = self.data_fetcher.get_stock_data(yf_sym, period="5d", interval="1d")
                if price is not None and not price.empty:
                    val = float(price["Close"].iloc[-1])
                    if val > 0:
                        vols[symbol] = round(val, 2)
            except Exception:
                # Silently fallback to default during backtests/rejections
                vols[symbol] = default_val

        return vols

    def calculate_macro_stress_score(self, vols: Dict[str, float]) -> float:
        """
        Normalize and aggregate cross-asset volatility indices into a Stress Score (0.0 to 1.0).
        """
        # Baseline normal and extreme parameters
        # Score = weight * norm_vol
        norm_vix = min(1.0, max(0.0, (vols["VIX"] - 12.0) / (40.0 - 12.0)))
        norm_move = min(1.0, max(0.0, (vols["MOVE"] - 50.0) / (160.0 - 50.0)))
        norm_ovx = min(1.0, max(0.0, (vols["OVX"] - 20.0) / (60.0 - 20.0)))
        norm_gvz = min(1.0, max(0.0, (vols["GVZ"] - 12.0) / (45.0 - 12.0)))

        # Weighted aggregate: 45% VIX, 25% MOVE, 15% OVX, 15% GVZ
        stress_score = (
            norm_vix * 0.45 +
            norm_move * 0.25 +
            norm_ovx * 0.15 +
            norm_gvz * 0.15
        )
        return round(float(stress_score), 3)

    def classify_regime(
        self,
        vols: Dict[str, float],
        stress_score: float,
        geopolitical_multiplier: float
    ) -> MacroRegime:
        """
        Solve the macro-economic and geopolitical market regime.
        """
        # 1. LIQUIDITY CRISIS: Extreme spikes across both stocks & bonds
        if vols["VIX"] > self.VIX_PANIC and vols["MOVE"] > self.MOVE_PANIC:
            return MacroRegime.LIQUIDITY_CRISIS

        # 2. PANIC: Volatility explosion in equities
        if vols["VIX"] >= self.VIX_PANIC or stress_score > 0.75:
            return MacroRegime.PANIC

        # 3. GEOPOLITICAL SHOCK: Extreme commodity spikes coupled with severe news de-risking multiplier
        if geopolitical_multiplier <= 0.5 or (vols["OVX"] > self.OVX_PANIC and vols["VIX"] > self.VIX_ELEVATED):
            return MacroRegime.GEOPOLITICAL_SHOCK

        # 4. INFLATION SHOCK: Extreme fixed-income yield and bond volatility spikes
        if vols["MOVE"] > self.MOVE_PANIC:
            return MacroRegime.INFLATION_SHOCK

        # 5. HIGH VOLATILITY TREND
        if vols["VIX"] >= self.VIX_ELEVATED:
            return MacroRegime.HIGH_VOL_TREND

        # 6. LOW VOLATILITY TREND (Default Baseline)
        return MacroRegime.LOW_VOL_TREND

    def get_macro_intelligence_report(self) -> Dict[str, Any]:
        """
        Perform complete macro diagnostics and return structural intelligence report.
        """
        vols = self.get_cross_asset_volatility()
        stress_score = self.calculate_macro_stress_score(vols)
        geo_multiplier = self.news_sentiment.get_geopolitical_risk_multiplier()
        regime = self.classify_regime(vols, stress_score, geo_multiplier)
        blackout = self.check_pre_event_blackout()

        return {
            "timestamp": time.time(),
            "regime": regime.value,
            "stress_score": stress_score,
            "geopolitical_multiplier": geo_multiplier,
            "vols": vols,
            "event_blackout": blackout
        }
