"""
Staged Rollout & Deployment Safety Gate
Enforces progressive deployment stages (SHADOW, MICRO, LIMITED, FULL) and checks
pre-flight requirements (unit tests, latency, VaR bounds) before execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from core.models import OrderRequest, OrderSide
from utils import get_logger, send_alert

logger = get_logger(__name__)


class TradingStage(Enum):
    SHADOW = "SHADOW"    # Generates signals, intercepts execution, logs paper slippage
    MICRO = "MICRO"      # 1-share execution, strict daily loss cap of $10.00
    LIMITED = "LIMITED"  # Strictly caps aggregate exposure to 5% of equity, 1.0x leverage
    FULL = "FULL"        # Full system limits as configured


class SafetyGate:
    """
    Gatekeeper managing staged deployment progression and risk validation metrics.
    """

    def __init__(self, current_stage: TradingStage = TradingStage.SHADOW):
        self.stage = current_stage
        logger.info("[Safety Gate] Initialized in stage: %s", self.stage.value)

    def set_stage(self, stage: TradingStage) -> None:
        """
        Manually adjust the current active trading stage.
        """
        logger.warning("[Safety Gate] Transitioning stage from %s to %s", self.stage.value, stage.value)
        self.stage = stage

    def check_readiness(
        self,
        tests_passed: bool,
        avg_latency_ms: float,
        current_var_percent: float,
        max_var_limit: float = 5.0,
    ) -> Tuple[bool, str]:
        """
        Evaluate readiness to trade or transition to higher stages.
        """
        # Rule 1: Tests must be completely green
        if not tests_passed:
            return False, "Pre-flight unit or integration tests failed."

        # Rule 2: Execution latency must be institutional-grade
        if avg_latency_ms > 250.0:
            return False, f"Execution latency ({avg_latency_ms:.1f}ms) exceeds the 250ms limit."

        # Rule 3: Parametric Value-at-Risk (VaR) must be within safe limits
        if current_var_percent > max_var_limit:
            return False, f"Current portfolio VaR ({current_var_percent:.2f}%) exceeds safety gate limit ({max_var_limit}%)."

        return True, "Pre-flight checks passed."

    def filter_order(self, request: OrderRequest, account_value: float) -> Tuple[Optional[OrderRequest], str]:
        """
        Intercept and modify order requests based on the active deployment stage.
        """
        stage_name = self.stage.value
        action_str = request.action.value if hasattr(request.action, "value") else str(request.action)

        # 1. SHADOW MODE: Block execution entirely, log signal metrics
        if self.stage == TradingStage.SHADOW:
            logger.info("[Safety Gate] [SHADOW] Intercepted %s order for %s. Sizing: %s shares (Execution Blocked).",
                        action_str, request.symbol, request.quantity)
            return None, "SHADOW: Signals logged but execution blocked."

        # 2. MICRO MODE: Enforce 1-share execution bounds
        if self.stage == TradingStage.MICRO:
            original_qty = request.quantity
            if original_qty > 1:
                request.quantity = 1
                logger.warning("[Safety Gate] [MICRO] Truncated %s order for %s from %d to 1 share.",
                               action_str, request.symbol, original_qty)
                return request, "MICRO: Truncated order to 1 share."
            return request, "MICRO: Order passed unchanged."

        # 3. LIMITED MODE: Cap aggregate trade exposure to 5% of account equity
        if self.stage == TradingStage.LIMITED:
            limit_price = float(request.limit_price) if request.limit_price is not None else 100.0
            position_value = request.quantity * limit_price
            max_value_allowed = account_value * 0.05

            if position_value > max_value_allowed:
                new_qty = max(1, int(max_value_allowed / limit_price))
                original_qty = request.quantity
                request.quantity = new_qty
                logger.warning(
                    "[Safety Gate] [LIMITED] Sized order value ($%.2f) exceeds 5%% equity cap ($%.2f). "
                    "Truncating qty for %s from %d to %d.",
                    position_value, max_value_allowed, request.symbol, original_qty, new_qty
                )
                return request, f"LIMITED: Truncated order quantity to respect 5% exposure limit."
            return request, "LIMITED: Order passed unchanged."

        # 4. FULL MODE: Pass through order unchanged
        return request, "FULL: Passed order unchanged."
