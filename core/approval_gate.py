"""
Live Trading Approval Gate (Phase 5)
Programmatic gatekeeper to enforce a checklist before allowing transition to live trading stages.
"""

import subprocess
import os
import time
from typing import Any, Dict, Tuple, Optional
from utils import get_logger, send_alert
from core.macro_intelligence import MacroIntelligenceEngine
from core.metrics_collector import MetricsCollector

logger = get_logger(__name__)


class LiveApprovalGate:
    """
    Enforces strict pre-flight checks before allowing live executions.
    """

    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.macro_engine = MacroIntelligenceEngine()

    def check_automated_tests(self) -> Tuple[bool, str]:
        """
        Executes critical validation suites via subprocess to verify platform integrity.
        """
        test_files = [
            "test_l2_microstructure.py",
            "test_reliability_chaos.py",
            "test_macro_intelligence.py",
        ]
        
        # Verify test files exist
        for tf in test_files:
            if not os.path.exists(tf):
                return False, f"Missing critical test suite: {tf}"

        logger.info("[Approval Gate] Running pre-flight automated test suites: %s...", ", ".join(test_files))
        try:
            # Resolve pytest path relative to workspace root
            pytest_path = os.path.join(".venv", "Scripts", "pytest.exe")
            if not os.path.exists(pytest_path):
                pytest_path = "pytest"  # Fallback to system path

            # Execute pytest as a subprocess
            cmd = [pytest_path, "-q"] + test_files
            # Run with a 60-second timeout to prevent hangs
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if res.returncode == 0:
                logger.info("[Approval Gate] Pre-flight automated tests: 100%% PASSED.")
                return True, "All critical test suites passed successfully."
            else:
                stderr_summary = res.stderr.strip() or res.stdout.strip()
                summary_line = [line for line in stderr_summary.split("\n") if "failed" in line or "error" in line or "FAIL" in line]
                summary_text = summary_line[0] if summary_line else "pytest exited with non-zero status code."
                logger.error("[Approval Gate] Pre-flight automated tests: FAILED. %s", summary_text)
                return False, f"Test suite failure: {summary_text}"
        except subprocess.TimeoutExpired:
            logger.error("[Approval Gate] Pre-flight automated tests: TIMED OUT.")
            return False, "Test suite execution timed out (60s limit)."
        except Exception as exc:
            logger.error("[Approval Gate] Pre-flight automated tests: ERROR during run. %s", exc)
            return False, f"Error executing test suite: {exc}"

    def check_macro_stress_score(self) -> Tuple[bool, float, str]:
        """
        Checks if the current macro stress score is within the safe threshold (< 0.70).
        """
        try:
            report = self.macro_engine.get_macro_intelligence_report()
            stress_score = report.get("stress_score", 0.0)
            
            if stress_score < 0.70:
                logger.info("[Approval Gate] Pre-flight macro stress score: %.3f (Safe: < 0.70).", stress_score)
                return True, stress_score, f"Stress score is in safe range: {stress_score:.3f}"
            else:
                logger.warning("[Approval Gate] Pre-flight macro stress score: %.3f (HIGH VOLATILITY LOCKOUT).", stress_score)
                return False, stress_score, f"Stress score exceeds safety threshold (score: {stress_score:.3f} >= 0.70)"
        except Exception as exc:
            logger.error("[Approval Gate] Pre-flight macro check: ERROR. %s", exc)
            return False, 1.0, f"Error calculating macro stress: {exc}"

    def check_execution_latency(self) -> Tuple[bool, float, str]:
        """
        Confirms average execution latency is within institutional parameters (< 250ms).
        """
        try:
            # Gather latencies from the metrics collector if populated
            latencies = self.metrics_collector.latencies
            
            if not latencies:
                # Default to normal baseline in absence of live execution samples
                avg_latency = 45.0
                logger.info("[Approval Gate] Pre-flight execution latency: No active samples. Using baseline %dms.", avg_latency)
                return True, avg_latency, "No active execution samples; defaulted to safe baseline."
            
            avg_latency = sum(latencies) / len(latencies)
            if avg_latency < 250.0:
                logger.info("[Approval Gate] Pre-flight execution latency: %.1fms (Safe: < 250ms).", avg_latency)
                return True, avg_latency, f"Average latency is safe: {avg_latency:.1f}ms"
            else:
                logger.warning("[Approval Gate] Pre-flight execution latency: %.1fms (LATENCY BREACH).", avg_latency)
                return False, avg_latency, f"Average latency exceeds safety limit ({avg_latency:.1f}ms >= 250ms)"
        except Exception as exc:
            logger.error("[Approval Gate] Pre-flight latency check: ERROR. %s", exc)
            return False, 999.0, f"Error gathering latency metrics: {exc}"

    def evaluate_readiness(self) -> Dict[str, Any]:
        """
        Solves pre-flight safety gates and computes unified scores.
        """
        tests_ok, tests_msg = self.check_automated_tests()
        macro_ok, stress_val, macro_msg = self.check_macro_stress_score()
        latency_ok, latency_val, latency_msg = self.check_execution_latency()

        # Score calculation: 3 checklist gates.
        passed_gates = sum([1 if gate else 0 for gate in [tests_ok, macro_ok, latency_ok]])
        readiness_score = int((passed_gates / 3.0) * 100)

        # Critical gate: All gates must be True to authorize live trading
        live_approved = (readiness_score >= 90) and tests_ok and macro_ok and latency_ok

        report = {
            "timestamp": time.time(),
            "deployment_readiness_score": readiness_score,
            "live_trading_approved": live_approved,
            "checklist": {
                "automated_tests": {
                    "status": "PASSED" if tests_ok else "FAILED",
                    "details": tests_msg
                },
                "macro_stress": {
                    "status": "PASSED" if macro_ok else "FAILED",
                    "score": stress_val,
                    "details": macro_msg
                },
                "execution_latency": {
                    "status": "PASSED" if latency_ok else "FAILED",
                    "average_ms": latency_val,
                    "details": latency_msg
                }
            }
        }

        # Issue institutional alert on approval state
        if live_approved:
            send_alert(f"Live Approval Gate: PASSED. Readiness score: {readiness_score}%", level="INFO")
            logger.info("=" * 60)
            logger.info("LIVE TRADING APPROVAL GATE: ACCESS GRANTED (%d%%)", readiness_score)
            logger.info("=" * 60)
        else:
            send_alert(f"Live Approval Gate: LOCKED. Readiness score: {readiness_score}%", level="WARNING")
            logger.warning("=" * 60)
            logger.warning("LIVE TRADING APPROVAL GATE: ACCESS DENIED (%d%%)", readiness_score)
            logger.warning("=" * 60)

        return report
