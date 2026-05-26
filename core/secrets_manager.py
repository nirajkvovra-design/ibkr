"""
Institutional Secrets Manager (Phase 5 Blocker 4)
Dynamic credential vault using standard keyring bindings, falling back securely to environment configurations.
"""

import os
import logging

logger = logging.getLogger("secrets_manager")

# Keyring service name
SERVICE_NAME = "ibkr_trading_system"

class SecretsVault:
    """
    Abstractions for secure storage and rehydration of broker keys, account IDs, and webhook endpoints.
    """

    @staticmethod
    def get_secret(key_name: str, fallback_env_name: str, default_value: str = "") -> str:
        """
        Queries standard OS Keyring service, falling back to system environment variables.
        """
        try:
            import keyring
            secret = keyring.get_password(SERVICE_NAME, key_name)
            if secret:
                logger.info("[Secrets Vault] Rehydrated %s from OS Keyring.", key_name)
                return secret
        except ImportError:
            logger.debug("[Secrets Vault] keyring package not installed. Skipping keyring query for %s.", key_name)
        except Exception as exc:
            logger.warning("[Secrets Vault] Error querying OS Keyring for %s: %s", key_name, exc)

        # Fallback to environment variables
        env_val = os.getenv(fallback_env_name)
        if env_val:
            return env_val

        return default_value

    @staticmethod
    def set_secret(key_name: str, value: str) -> bool:
        """
        Store a secret securely in the OS Keyring.
        """
        try:
            import keyring
            keyring.set_password(SERVICE_NAME, key_name, value)
            logger.info("[Secrets Vault] Successfully stored %s in OS Keyring.", key_name)
            return True
        except ImportError:
            logger.error("[Secrets Vault] Cannot store secret: keyring package is not installed.")
            return False
        except Exception as exc:
            logger.error("[Secrets Vault] Failed to store secret in OS Keyring: %s", exc)
            return False
