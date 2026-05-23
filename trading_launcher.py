"""
Start the trading engine with graceful restart if another instance is already running.
"""

import sys

from engine_control import prepare_restart_handoff
from utils import get_logger, setup_logging

logger = get_logger(__name__)


def main():
    setup_logging()
    if not prepare_restart_handoff():
        logger.error("Could not prepare restart handoff; aborting start")
        sys.exit(1)

    from trading_engine import main as run_engine

    run_engine()


if __name__ == "__main__":
    main()
