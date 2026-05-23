"""
Continuous Health Sentry for the IBKR Trading Engine.
Monitors TWS API port and engine PID, auto-starting the engine when connection becomes available.
"""

import os
import sys
import time
import socket
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Add workspace directory to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import engine_control
from utils import get_logger, setup_logging
from self_learning import SelfLearningAgent

logger = get_logger("engine_sentry")

_PROJECT_DIR = Path(__file__).resolve().parent
SENTRY_STATUS_FILE = _PROJECT_DIR / "sentry_health.json"
ENGINE_HEARTBEAT_FILE = _PROJECT_DIR / "trading_health.json"
DAILY_POSITIONS_FILE = Path(getattr(config, "DAILY_POSITIONS_FILE", "daily_positions.json"))

class EngineSentry:
    def __init__(self):
        setup_logging()
        self.host = config.IB_HOST
        self.port = config.IB_PORT
        self.restart_history = []
        self.total_restarts = 0
        self.last_restart_time = None
        self.sentry_status = "INITIALIZING"
        self.learning_agent = SelfLearningAgent()
        
    def is_tws_online(self):
        """Perform a quick TCP socket ping to TWS API port."""
        try:
            with socket.create_connection((self.host, self.port), timeout=2.0) as conn:
                return True
        except OSError:
            return False

    def get_active_positions(self):
        """Read currently opened daily positions from today's tracker."""
        if not DAILY_POSITIONS_FILE.exists():
            return {}
        try:
            data = json.loads(DAILY_POSITIONS_FILE.read_text(encoding="utf-8"))
            return data.get("opens", {})
        except Exception:
            return {}

    def clean_restart_history(self):
        """Remove restart timestamps older than 1 hour."""
        now = datetime.now()
        self.restart_history = [t for t in self.restart_history if now - t < timedelta(hours=1)]

    def can_restart(self):
        """Check if we are within the safety threshold of 5 restarts per hour."""
        self.clean_restart_history()
        return len(self.restart_history) < 5

    def launch_engine(self):
        """Execute trading_launcher.py in a background subprocess."""
        if not self.can_restart():
            self.sentry_status = "COOLDOWN_LIMIT"
            logger.error("[Sentry] Engine restart blocked: exceeded rate limit of 5 boots/hour.")
            return False

        logger.info("[Sentry] Launching trading engine...")
        self.sentry_status = "RECOVERING"
        try:
            # Set environment variables for the subprocess to match our configs
            env = os.environ.copy()
            env["PAPER_TRADING"] = str(config.PAPER_TRADING)
            env["IB_PORT"] = str(config.IB_PORT)
            env["ENABLE_LIVE_TRADING"] = str(config.ENABLE_LIVE_TRADING)
            
            # Start background process using python interpreter path or fallback
            python_cmd = sys.executable or "python"
            launcher_path = Path(__file__).resolve().parent / "trading_launcher.py"
            
            # On Windows, use subprocess.Popen with creationflags to run detached
            if os.name == "nt":
                subprocess.Popen(
                    [python_cmd, str(launcher_path)],
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                    close_fds=True
                )
            else:
                subprocess.Popen(
                    [python_cmd, str(launcher_path)],
                    env=env,
                    preexec_fn=os.setpgrp,
                    close_fds=True
                )
            
            now = datetime.now()
            self.restart_history.append(now)
            self.total_restarts += 1
            self.last_restart_time = now.isoformat(timespec="seconds")
            logger.info(f"[Sentry] Engine launched successfully (session restarts: {self.total_restarts})")
            return True
        except Exception as e:
            logger.exception(f"[Sentry] Failed to launch trading engine: {e}")
            self.sentry_status = "LAUNCH_FAILED"
            return False

    def update_aggregated_status(self):
        """Generate comprehensive diagnostic JSON and overwrite health status."""
        tws_active = self.is_tws_online()
        engine_active = engine_control.is_engine_running()
        
        # Parse internal engine heartbeat if available
        heartbeat = {}
        if ENGINE_HEARTBEAT_FILE.exists():
            try:
                heartbeat = json.loads(ENGINE_HEARTBEAT_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Determine sentry status phase
        if not tws_active:
            self.sentry_status = "TWS_OFFLINE"
        elif self.sentry_status not in ("COOLDOWN_LIMIT", "LAUNCH_FAILED"):
            if engine_active:
                self.sentry_status = "HEALTHY"
            else:
                self.sentry_status = "RECOVERING"
        
        # Read PID file details
        pid_record = engine_control.read_pid_record()
        engine_pid = pid_record.get("pid") if pid_record else None
        engine_started_at = pid_record.get("started_at") if pid_record else None

        # Fetch self-learning metrics
        try:
            learning_summary = self.learning_agent.get_learning_summary()
        except Exception as e:
            logger.debug(f"Failed to fetch learning summary: {e}")
            learning_summary = {"total_analyzed": 0, "blacklisted": [], "boosted": [], "penalized": [], "details": {}}

        # Fetch positions
        positions = self.get_active_positions()

        # Account ID override from active heartbeat
        account_id = heartbeat.get("account") or config.IB_ACCOUNT or "Demo Account"

        status_record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "connected": tws_active,
            "engine_running": engine_active,
            "engine_pid": engine_pid,
            "engine_started_at": engine_started_at,
            "sentry_status": self.sentry_status,
            "restart_count": self.total_restarts,
            "last_restart_time": self.last_restart_time,
            "account": account_id,
            "port": self.port,
            "mode": "PAPER" if config.PAPER_TRADING else "LIVE",
            "positions": positions,
            "self_learning": learning_summary
        }

        try:
            SENTRY_STATUS_FILE.write_text(json.dumps(status_record, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[Sentry] Failed to write status record: {exc}")

    def run(self):
        """Main monitoring loop."""
        logger.info(f"[Sentry] Engine Health Sentry active. Monitoring port {self.port} every 15s...")
        while True:
            try:
                tws_active = self.is_tws_online()
                engine_active = engine_control.is_engine_running()
                
                # Auto-recovery logic: TWS is online, but trading engine is dead
                if tws_active and not engine_active:
                    logger.warning("[Sentry] TWS is ONLINE but Trading Engine is OFFLINE. Attempting automated re-bind...")
                    self.launch_engine()
                
                # Periodically write detailed diagnostic files
                self.update_aggregated_status()
                
            except Exception as e:
                logger.exception(f"[Sentry] Exception in monitoring loop: {e}")
                
            time.sleep(15)

if __name__ == "__main__":
    sentry = EngineSentry()
    sentry.run()
