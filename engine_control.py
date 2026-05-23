"""
Single-instance control: graceful restart when a second start is requested.

Uses a PID file and a restart-request flag file in the project directory.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import config
from utils import get_logger

logger = get_logger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parent
PID_FILE = _PROJECT_DIR / getattr(config, "ENGINE_PID_FILE", ".trading_engine.pid")
RESTART_FILE = _PROJECT_DIR / getattr(config, "ENGINE_RESTART_FILE", ".trading_engine.restart")

_shutting_down = False


def set_shutting_down(value=True):
    global _shutting_down
    _shutting_down = value


def is_shutting_down():
    return _shutting_down


def _is_process_running(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def read_pid_record():
    if not PID_FILE.exists():
        return None
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_pid(pid=None):
    pid = pid or os.getpid()
    record = {
        "pid": pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "paper": config.PAPER_TRADING,
        "port": config.IB_PORT,
    }
    PID_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")


def clear_pid():
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug(f"Could not remove PID file: {exc}")


def is_engine_running():
    record = read_pid_record()
    if not record:
        return False
    pid = record.get("pid")
    if _is_process_running(pid):
        return True
    clear_pid()
    return False


def request_restart():
    RESTART_FILE.write_text(
        json.dumps(
            {"requested_at": datetime.now().isoformat(timespec="seconds")},
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Restart requested — existing engine will finish open work and exit")


def is_restart_requested():
    return RESTART_FILE.exists()


def clear_restart_request():
    try:
        RESTART_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug(f"Could not remove restart file: {exc}")


def wait_for_engine_exit(timeout=None):
    """Wait until the old engine process has exited and released the PID file."""
    timeout = timeout if timeout is not None else config.RESTART_SHUTDOWN_TIMEOUT
    poll = config.RESTART_POLL_INTERVAL
    deadline = time.time() + timeout
    record = read_pid_record()
    pid = record.get("pid") if record else None

    logger.info(f"Waiting up to {timeout}s for existing engine (pid {pid}) to shut down...")
    while time.time() < deadline:
        if pid and not _is_process_running(pid):
            clear_pid()
            clear_restart_request()
            logger.info("Previous engine process ended")
            return True
        if not PID_FILE.exists() and (not pid or not _is_process_running(pid)):
            logger.info("Previous engine stopped")
            return True
        time.sleep(poll)

    logger.error(f"Timed out after {timeout}s waiting for engine shutdown")
    return False


def prepare_restart_handoff():
    """
    If another engine is running, ask it to shut down gracefully and wait.
    Returns True when safe to start a new instance.
    """
    if not is_engine_running():
        clear_restart_request()
        return True

    logger.info("Trading engine already running — coordinating graceful restart")
    request_restart()
    if wait_for_engine_exit():
        clear_restart_request()
        return True

    record = read_pid_record()
    pid = record.get("pid") if record else None
    if pid and _is_process_running(pid):
        logger.warning(f"Force-stopping unresponsive engine (pid {pid})")
        if os.name == "nt":
            import subprocess
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                check=False,
            )
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        time.sleep(2)
    clear_pid()
    clear_restart_request()
    return True
