"""
Production Finalization & Reliability Verification Suite (Phase 5)
Tests:
1. Connection Watchdog Auto-Reconnection & Risk Lockdown.
2. Live Approval Gate pre-flight checks and Readiness Scores.
3. Environment variables configuration binding.
"""

import asyncio
import os
import importlib
import unittest
from unittest.mock import MagicMock, patch

import config
from trading_engine import TradingEngine
from risk_manager import RiskManager
from core.approval_gate import LiveApprovalGate
from core.metrics_collector import MetricsCollector


class TestProductionFinalization(unittest.TestCase):

    def setUp(self):
        # Save original env
        self.original_env = dict(os.environ)

    def tearDown(self):
        # Restore original env
        os.environ.clear()
        os.environ.update(self.original_env)
        # Reload config to restore baseline settings
        importlib.reload(config)

    @patch("asyncio.sleep")
    @patch("trading_engine.setup_logging")
    @patch("trading_engine.InteractiveBrokersConnection")
    @patch("trading_engine.OrderManager")
    @patch("trading_engine.RiskManager")
    def test_watchdog_auto_reconnection_lockdown(
        self, mock_risk_cls, mock_order_cls, mock_conn_cls, mock_setup_logging, mock_sleep
    ):
        """Verify the Connection Watchdog locks execution and recovers on broker disconnect."""
        # Setup mocks
        mock_conn = mock_conn_cls.return_value
        mock_conn.connected = False  # Trigger watchdog recovery
        
        # Connection connect mock: first two attempts fail, third attempt succeeds
        connect_results = [False, False, True]
        def mock_connect(*args, **kwargs):
            return connect_results.pop(0) if connect_results else True
        mock_conn.connect = MagicMock(side_effect=mock_connect)
        mock_conn.get_positions.return_value = {}

        mock_risk = mock_risk_cls.return_value
        mock_order = mock_order_cls.return_value

        # Instantiate TradingEngine
        engine = TradingEngine()
        engine.ib_connection = mock_conn
        engine.risk_manager = mock_risk
        engine.order_manager = mock_order
        engine.running = True

        # Make the async loop run exactly one iteration by modifying engine.running to False after sleep
        async def mock_sleep_impl(seconds):
            # Shutdown the loop during the first sleep inside watchdog to prevent infinite cycle
            engine.running = False

        mock_sleep.side_effect = mock_sleep_impl

        # Execute watchdog loop iteration
        asyncio.run(engine.monitor_broker_connection())

        # Assert watchdog performed lockdown and recovery operations
        mock_risk.engage_kill_switch.assert_called_once()
        mock_order.cancel_stale_orders.assert_called_once()
        self.assertTrue(mock_conn.connect.called)
        mock_risk.disengage_kill_switch.assert_called_once()

    def test_live_approval_gate_scoring_solver(self):
        """Verify LiveApprovalGate solves checklist scores and correctly gates live executions."""
        metrics = MetricsCollector()
        gate = LiveApprovalGate(metrics)

        # Case 1: 100% Passed pre-flight
        with patch.object(gate, "check_automated_tests", return_value=(True, "Tests passed")), \
             patch.object(gate, "check_macro_stress_score", return_value=(True, 0.22, "Low stress")), \
             patch.object(gate, "check_execution_latency", return_value=(True, 35.0, "Latency normal")):
            
            report = gate.evaluate_readiness()
            self.assertEqual(report["deployment_readiness_score"], 100)
            self.assertTrue(report["live_trading_approved"])

    def test_live_approval_gate_fails_on_macro_stress(self):
        """Verify LiveApprovalGate locks execution if macro stress score is too high."""
        metrics = MetricsCollector()
        gate = LiveApprovalGate(metrics)

        # Case 2: Fails on high macro stress score (>= 0.70)
        with patch.object(gate, "check_automated_tests", return_value=(True, "Tests passed")), \
             patch.object(gate, "check_macro_stress_score", return_value=(False, 0.85, "Macro panic engaged")), \
             patch.object(gate, "check_execution_latency", return_value=(True, 35.0, "Latency normal")):
            
            report = gate.evaluate_readiness()
            self.assertLess(report["deployment_readiness_score"], 90)
            self.assertFalse(report["live_trading_approved"])

    def test_live_approval_gate_fails_on_test_failure(self):
        """Verify LiveApprovalGate locks execution if test suite fails."""
        metrics = MetricsCollector()
        gate = LiveApprovalGate(metrics)

        # Case 3: Fails on automated test failure
        with patch.object(gate, "check_automated_tests", return_value=(False, "test_reliability_chaos.py failed")), \
             patch.object(gate, "check_macro_stress_score", return_value=(True, 0.25, "Low stress")), \
             patch.object(gate, "check_execution_latency", return_value=(True, 35.0, "Latency normal")):
            
            report = gate.evaluate_readiness()
            self.assertFalse(report["live_trading_approved"])

    def test_dynamic_environment_binding(self):
        """Verify config.py dynamically binds environment variables without hardcoded fallbacks."""
        # Inject custom env variables
        os.environ["IB_HOST"] = "192.168.10.88"
        os.environ["IB_PORT"] = "4002"
        os.environ["IB_CLIENTID"] = "88"
        os.environ["IB_ACCOUNT"] = "DU1234567"
        os.environ["PAPER_TRADING"] = "False"
        os.environ["ENABLE_LIVE_TRADING"] = "True"

        # Reload the config module to parse new environments
        importlib.reload(config)

        # Assert config binds custom values
        self.assertEqual(config.IB_HOST, "192.168.10.88")
        self.assertEqual(config.IB_PORT, 4002)
        self.assertEqual(config.IB_CLIENTID, 88)
        self.assertEqual(config.IB_ACCOUNT, "DU1234567")
        self.assertFalse(config.PAPER_TRADING)
        self.assertTrue(config.ENABLE_LIVE_TRADING)

    @patch("asyncio.sleep")
    @patch("trading_engine.setup_logging")
    @patch("trading_engine.InteractiveBrokersConnection")
    @patch("trading_engine.OrderManager")
    @patch("trading_engine.RiskManager")
    def test_watchdog_detects_stale_market_data(
        self, mock_risk_cls, mock_order_cls, mock_conn_cls, mock_setup_logging, mock_sleep
    ):
        """Verify watchdog detects stale market data and engages programmatic Kill Switch."""
        # Setup mocks
        mock_conn = mock_conn_cls.return_value
        mock_conn.connected = True
        
        # Inject old heartbeat (100 seconds ago) to simulate stale data
        import time
        mock_conn.wrapper = MagicMock()
        mock_conn.wrapper.last_heartbeat = time.time() - 100.0
        
        mock_risk = mock_risk_cls.return_value
        mock_risk.kill_switch_active = False
        mock_order = mock_order_cls.return_value
        
        engine = TradingEngine()
        engine.ib_connection = mock_conn
        engine.risk_manager = mock_risk
        engine.order_manager = mock_order
        engine.running = True
        
        # Mock sleep to run only one watchdog loop iteration
        async def mock_sleep_impl(seconds):
            engine.running = False
            
        mock_sleep.side_effect = mock_sleep_impl
        
        # Force is_market_open to return True
        with patch("utils.is_market_open", return_value=True):
            asyncio.run(engine.monitor_broker_connection())
            
        # Watchdog must engage Kill Switch and cancel stale orders
        mock_risk.engage_kill_switch.assert_called_once()
        mock_order.cancel_stale_orders.assert_called_once()

    @patch("asyncio.sleep")
    @patch("trading_engine.setup_logging")
    @patch("trading_engine.InteractiveBrokersConnection")
    @patch("trading_engine.OrderManager")
    @patch("trading_engine.RiskManager")
    def test_watchdog_detects_position_drift_mismatch(
        self, mock_risk_cls, mock_order_cls, mock_conn_cls, mock_setup_logging, mock_sleep
    ):
        """Verify watchdog detects position mismatch (manual trade drift) and engages Kill Switch."""
        # Setup mocks
        mock_conn = mock_conn_cls.return_value
        mock_conn.connected = True
        
        # Fresh heartbeat (0 seconds ago) to avoid stale data block
        import time
        mock_conn.wrapper = MagicMock()
        mock_conn.wrapper.last_heartbeat = time.time()
        
        # Inject a position mismatch: local expects 0 positions, live has AAPL x 10
        mock_conn.get_positions.return_value = {
            "AAPL": MagicMock(quantity=10, avg_cost=150.00)
        }
        
        mock_risk = mock_risk_cls.return_value
        mock_risk.open_positions = {}  # Local expects empty positions
        mock_risk.kill_switch_active = False
        
        mock_order = mock_order_cls.return_value
        
        engine = TradingEngine()
        engine.ib_connection = mock_conn
        engine.risk_manager = mock_risk
        engine.order_manager = mock_order
        engine.running = True
        
        # Mock sleep to run only one watchdog loop iteration
        async def mock_sleep_impl(seconds):
            engine.running = False
            
        mock_sleep.side_effect = mock_sleep_impl
        
        # Run watchdog loop iteration
        asyncio.run(engine.monitor_broker_connection())
        
        # Watchdog must engage Kill Switch due to untracked positions mismatch
        mock_risk.engage_kill_switch.assert_called_once()

    def test_secrets_vault_keyring_retrieval(self):
        """Verify SecretsVault retrieves passwords from OS Keyring."""
        import sys
        from unittest.mock import MagicMock
        
        # Backup original sys.modules keyring if it exists
        orig_keyring = sys.modules.get("keyring")
        
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "VAULT_VAL_123"
        sys.modules["keyring"] = mock_keyring
        
        try:
            from core.secrets_manager import SecretsVault
            val = SecretsVault.get_secret("TEST_SECRET", "TEST_ENV_FALLBACK", "default")
            self.assertEqual(val, "VAULT_VAL_123")
            mock_keyring.get_password.assert_called_once_with("ibkr_trading_system", "TEST_SECRET")
        finally:
            # Restore keyring module state
            if orig_keyring is not None:
                sys.modules["keyring"] = orig_keyring
            else:
                sys.modules.pop("keyring", None)

    def test_secrets_vault_env_fallback(self):
        """Verify SecretsVault falls back to environment variables when keyring has no stored key."""
        import sys
        from unittest.mock import MagicMock
        
        # Backup original sys.modules keyring
        orig_keyring = sys.modules.get("keyring")
        
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        sys.modules["keyring"] = mock_keyring
        
        try:
            from core.secrets_manager import SecretsVault
            os.environ["TEST_ENV_FALLBACK"] = "ENV_VAL_999"
            val = SecretsVault.get_secret("TEST_SECRET_ABSENT", "TEST_ENV_FALLBACK", "default")
            self.assertEqual(val, "ENV_VAL_999")
        finally:
            if "TEST_ENV_FALLBACK" in os.environ:
                del os.environ["TEST_ENV_FALLBACK"]
            # Restore keyring module state
            if orig_keyring is not None:
                sys.modules["keyring"] = orig_keyring
            else:
                sys.modules.pop("keyring", None)
