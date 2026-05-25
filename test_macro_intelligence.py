"""
Verification & Validation Suite for Macro, News, and Geopolitical Intelligence Engine.
Tests:
1. Volatility index normalization and unified Stress Score calculation.
2. MacroRegime transitions (PANIC, GEOPOLITICAL_SHOCK, LIQUIDITY_CRISIS).
3. Economic Event calendar sentry and pre-event blackout gates.
4. Dynamic Risk scaling and headline sentiment multiplier integration.
5. Leverage regulation cash caps and volatility-adjusted stop losses.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from core.macro_intelligence import MacroIntelligenceEngine, MacroRegime
from core.models import OrderRequest, OrderSide, OrderType
from news_sentiment import NewsSentiment
from risk_manager import RiskManager


class TestMacroIntelligence(unittest.TestCase):

    def setUp(self):
        self.symbol = "AAPL"
        self.mock_fetcher = MagicMock()
        self.engine = MacroIntelligenceEngine(self.mock_fetcher)

    def test_stress_score_and_regime_classification(self):
        """Verify cross-asset volatility indices yield correct normalized Stress Scores and regimes."""
        # Scenario A: Baseline Normal Volatility (Low Stress)
        vols_normal = {"VIX": 13.50, "MOVE": 62.00, "OVX": 22.00, "GVZ": 14.00}
        score_normal = self.engine.calculate_macro_stress_score(vols_normal)
        regime_normal = self.engine.classify_regime(vols_normal, score_normal, 1.0)
        
        self.assertTrue(score_normal < 0.20, "Baseline stress score should be low.")
        self.assertEqual(regime_normal, MacroRegime.LOW_VOL_TREND)

        # Scenario B: High Volatility Trend (Elevated VIX)
        vols_high = {"VIX": 24.00, "MOVE": 95.00, "OVX": 35.00, "GVZ": 22.00}
        score_high = self.engine.calculate_macro_stress_score(vols_high)
        regime_high = self.engine.classify_regime(vols_high, score_high, 1.0)
        self.assertEqual(regime_high, MacroRegime.HIGH_VOL_TREND)

        # Scenario C: Equity Panic (VIX > 30)
        vols_panic = {"VIX": 38.00, "MOVE": 95.00, "OVX": 35.00, "GVZ": 22.00}
        score_panic = self.engine.calculate_macro_stress_score(vols_panic)
        regime_panic = self.engine.classify_regime(vols_panic, score_panic, 1.0)
        self.assertEqual(regime_panic, MacroRegime.PANIC)

        # Scenario D: Commodity and Geopolitical Shock (OVX > 45, VIX elevated)
        vols_geo = {"VIX": 22.00, "MOVE": 85.00, "OVX": 48.00, "GVZ": 28.00}
        score_geo = self.engine.calculate_macro_stress_score(vols_geo)
        regime_geo = self.engine.classify_regime(vols_geo, score_geo, 1.0)
        self.assertEqual(regime_geo, MacroRegime.GEOPOLITICAL_SHOCK)

        # Scenario E: Liquidity Crisis (VIX and MOVE simultaneously in panic bounds)
        vols_liq = {"VIX": 35.00, "MOVE": 140.00, "OVX": 40.00, "GVZ": 30.00}
        score_liq = self.engine.calculate_macro_stress_score(vols_liq)
        regime_liq = self.engine.classify_regime(vols_liq, score_liq, 1.0)
        self.assertEqual(regime_liq, MacroRegime.LIQUIDITY_CRISIS)

    def test_economic_event_blackout_sentries(self):
        """Verify economic calendar blackout windows correctly block trade signals."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        next_week_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        # Register CPI tomorrow, FOMC next week
        self.engine.register_scheduled_events(fomc_dates=[next_week_str], cpi_dates=[tomorrow_str])
        
        # Blackout check should trigger because CPI is tomorrow (within 1-day buffer)
        blackout = self.engine.check_pre_event_blackout(days_buffer=1)
        self.assertTrue(blackout["is_blocked"])
        self.assertEqual(blackout["event_type"], "CPI")
        self.assertIn("CPI", blackout["reason"])

    def test_risk_manager_macro_exposure_scaling(self):
        """Verify RiskManager dynamically scales position size limits according to macro stress scores."""
        mock_ib = MagicMock()
        mock_ib.get_account_value.return_value = 10000.0
        
        rm = RiskManager(mock_ib)
        rm.macro_engine = self.engine
        
        # Force baseline LOW_VOL_TREND (multiplier = 1.0x)
        self.engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "LOW_VOL_TREND",
            "stress_score": 0.15,
            "geopolitical_multiplier": 1.0,
            "event_blackout": {"is_blocked": False, "reason": ""}
        })
        
        # Standard limits check: BUY 10 AAPL @ 150.00 ($1,500 position) should pass
        res_normal = rm.is_within_limits(self.symbol, quantity=10, entry_price=150.00)
        self.assertTrue(res_normal)

        # Force GEOPOLITICAL_SHOCK (multiplier = 0.40x) coupled with severe news de-risking multiplier (0.50x)
        # Total macro sizing scaling factor = 0.40 * 0.50 = 0.20x!
        # Max pos limit = account_value (10000) * MAX_PORTFOLIO_POSITION_PERCENT (0.15) * 0.20x = $300.00
        self.engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "GEOPOLITICAL_SHOCK",
            "stress_score": 0.55,
            "geopolitical_multiplier": 0.50,
            "event_blackout": {"is_blocked": False, "reason": ""}
        })
        
        # BUY $1,500 position should now be blocked because it exceeds the scaled limit ($300.00)
        res_scaled = rm.is_within_limits(self.symbol, quantity=10, entry_price=150.00)
        self.assertFalse(res_scaled, "RiskManager failed to block trade exceeding macro scaled limits.")

    def test_dynamic_stop_loss_widening(self):
        """Verify stop loss width increases by 1.5x during high-volatility macro regimes."""
        mock_ib = MagicMock()
        rm = RiskManager(mock_ib)
        rm.macro_engine = self.engine
        
        # 1. Normal Volatility Regime stop loss (2%) -> Stop price = 100 * 0.98 = 98.00
        self.engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "LOW_VOL_TREND",
            "stress_score": 0.10,
            "geopolitical_multiplier": 1.0,
            "event_blackout": {"is_blocked": False}
        })
        stop_normal = rm.set_stop_loss(self.symbol, entry_price=100.00, stop_loss_percent=2.0)
        self.assertEqual(stop_normal, 98.00)
        
        # 2. Panic Regime stop loss (2% * 1.5x = 3%) -> Stop price = 100 * 0.97 = 97.00
        self.engine.get_macro_intelligence_report = MagicMock(return_value={
            "regime": "PANIC",
            "stress_score": 0.85,
            "geopolitical_multiplier": 1.0,
            "event_blackout": {"is_blocked": False}
        })
        stop_panic = rm.set_stop_loss(self.symbol, entry_price=100.00, stop_loss_percent=2.0)
        self.assertEqual(stop_panic, 97.00, "RiskManager failed to widen stop-loss width under Panic regime.")

    def test_geopolitical_headlines_sentiment_scoring(self):
        """Verify NewsSentiment extracts geopolitical conflict multipliers accurately from headlines."""
        ns = NewsSentiment()
        
        # Inject standard stable headlines
        mock_stable = [{"title": "AAPL launches new dynamic display model"}, {"title": "Bond yields consolidate near support"}]
        mult_stable = ns.get_geopolitical_risk_multiplier(mock_stable)
        self.assertEqual(mult_stable, 1.0)
        
        # Inject war and sanctions headlines
        mock_conflict = [{"title": "Sanctions tightened on energy imports"}, {"title": "Escalating war prompts emergency measures"}]
        mult_conflict = ns.get_geopolitical_risk_multiplier(mock_conflict)
        # Minimum severity trigger is "war" (0.4)
        self.assertEqual(mult_conflict, 0.4, "NewsSentiment failed to solve correct de-risking multiplier for conflict headlines.")


if __name__ == "__main__":
    unittest.main()
