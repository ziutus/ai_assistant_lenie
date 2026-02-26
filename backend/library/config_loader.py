"""Unified configuration loader with pluggable backends.

Provides a centralized Config object that replaces scattered os.getenv()
calls.  Backends: ``env`` (dotenv), ``vault`` (HashiCorp Vault KV v2),
``aws`` (stub for Story 20.3).

Usage::

    from library.config_loader import get_config

    cfg = get_config()
    db_host = cfg.require("POSTGRESQL_HOST")
    debug  = cfg.require("DEBUG", "false")
"""

import logging
import os
import sys
from abc import ABC, abstractmethod

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config object
# ---------------------------------------------------------------------------


class Config(dict):
    """dict subclass with a ``require()`` helper that mirrors the legacy
    ``fetch_env_var()`` behaviour: return value, fall back to *default*,
    or log-and-exit when the key is missing."""

    def require(self, key: str, default=None):
        value = self.get(key)
        if value is not None:
            return value
        if default is not None:
            return default
        logging.error("ERROR: missing OS variables %s, exiting... ", key)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class ConfigBackend(ABC):
    """Base class for configuration backends."""

    @abstractmethod
    def load(self) -> dict[str, str]:
        """Return a mapping of configuration key→value pairs."""


class EnvBackend(ConfigBackend):
    """Loads configuration from ``.env`` file + real environment variables.

    Calls ``load_dotenv()`` so that library modules still using raw
    ``os.getenv()`` keep working during the incremental migration.
    """

    def load(self) -> dict[str, str]:
        load_dotenv()
        return dict(os.environ)


# Bootstrap env vars that are always read from the real environment,
# regardless of which backend is selected.
_BOOTSTRAP_VARS = frozenset({
    "SECRETS_BACKEND",
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "ENV_DATA",
    "AWS_REGION",
})


class VaultBackend(ConfigBackend):
    """Loads configuration from HashiCorp Vault KV v2.

    Secrets are stored at ``secret/lenie/{ENV_DATA}`` as a single KV v2
    secret containing all configuration key-value pairs.

    Bootstrap env vars (``VAULT_ADDR``, ``VAULT_TOKEN``, ``ENV_DATA``)
    must be set in the real environment (e.g. ``.env`` or shell).
    """

    def load(self) -> dict[str, str]:
        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        env_data = os.environ.get("ENV_DATA", "dev")

        if not vault_addr:
            logging.error("VAULT_ADDR must be set when using vault backend")
            sys.exit(1)
        if not vault_token:
            logging.error("VAULT_TOKEN must be set when using vault backend")
            sys.exit(1)

        try:
            import hvac
        except ImportError:
            logging.error("hvac package is required for vault backend: pip install hvac")
            sys.exit(1)

        try:
            client = hvac.Client(url=vault_addr, token=vault_token)
            if not client.is_authenticated():
                logging.error(
                    "Vault authentication failed at %s — check VAULT_TOKEN", vault_addr
                )
                sys.exit(1)

            secret_path = f"lenie/{env_data}"
            logging.info("Vault: reading secret at secret/%s", secret_path)
            response = client.secrets.kv.v2.read_secret_version(
                path=secret_path,
                mount_point="secret",
            )
            vault_data = response["data"]["data"]
        except SystemExit:
            raise
        except Exception as exc:
            logging.error(
                "Failed to load config from Vault at %s: %s", vault_addr, exc
            )
            sys.exit(1)

        # Start with bootstrap env vars, overlay with Vault secrets.
        result = {k: os.environ[k] for k in _BOOTSTRAP_VARS if k in os.environ}
        result.update(vault_data)
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_KNOWN_BACKENDS = {"env", "vault", "aws"}


def _create_backend(name: str) -> ConfigBackend:
    """Instantiate a backend by name."""
    if name == "env":
        return EnvBackend()
    if name == "vault":
        return VaultBackend()
    if name == "aws":
        raise NotImplementedError(
            "AWS backend is not yet implemented (see Story 20.3)."
        )
    logging.error(
        "Unknown SECRETS_BACKEND value: '%s'. Valid options: %s",
        name,
        ", ".join(sorted(_KNOWN_BACKENDS)),
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_config: Config | None = None


def load_config() -> Config:
    """Create (or return cached) Config from the selected backend.

    The backend is chosen via ``SECRETS_BACKEND`` env-var (default ``env``).
    """
    global _config
    if _config is not None:
        return _config

    backend_name = os.environ.get("SECRETS_BACKEND", "env")
    logging.info("Config loader: using '%s' backend", backend_name)
    backend = _create_backend(backend_name)
    _config = Config(backend.load())
    return _config


def get_config() -> Config:
    """Return the cached Config, auto-loading on first call."""
    if _config is None:
        return load_config()
    return _config


def reset_config() -> None:
    """Clear the cached Config (intended for tests only)."""
    global _config
    _config = None
