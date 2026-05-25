"""
Persistent State Manager
Handles JSON-based serialization and rehydration of active risk bounds, stop losses,
take-profit values, daily PnL, and open positions across system restarts.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

from utils import get_logger

logger = get_logger(__name__)


class StateManager:
    """
    Thread-safe persistent state manager.
    Saves and rehydrates volatile RAM state to/from a local disk cache.
    """

    def __init__(self, cache_filename: str = ".state_cache.json"):
        self.filepath = os.path.abspath(cache_filename)
        self.lock = threading.Lock()
        logger.info("[State Manager] Initialized with state cache: %s", self.filepath)

    def save_state(self, state_data: Dict[str, Any]) -> bool:
        """
        Thread-safely persist a state dictionary to the disk cache.
        """
        with self.lock:
            try:
                # Write to a temporary file first, then rename to guarantee atomic write
                temp_filepath = f"{self.filepath}.tmp"
                with open(temp_filepath, "w") as f:
                    json.dump(state_data, f, indent=4)
                
                if os.path.exists(self.filepath):
                    os.remove(self.filepath)
                os.rename(temp_filepath, self.filepath)
                logger.debug("[State Manager] Successfully persisted system state.")
                return True
            except Exception as e:
                logger.error("[State Manager] Failed to save state cache: %s", e)
                return False

    def load_state(self) -> Dict[str, Any]:
        """
        Thread-safely load and return the state cache from disk.
        Returns an empty dict if the file does not exist or is corrupted.
        """
        with self.lock:
            if not os.path.exists(self.filepath):
                logger.debug("[State Manager] No existing state cache found. Starting fresh.")
                return {}
            
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                logger.info("[State Manager] Successfully rehydrated system state from cache.")
                return data
            except Exception as e:
                logger.error("[State Manager] Failed to read state cache or file is corrupted: %s", e)
                return {}

    def clear_state(self) -> None:
        """
        Remove the state cache from disk.
        """
        with self.lock:
            if os.path.exists(self.filepath):
                try:
                    os.remove(self.filepath)
                    logger.info("[State Manager] Cleared state cache from disk.")
                except Exception as e:
                    logger.error("[State Manager] Failed to remove state cache: %s", e)
