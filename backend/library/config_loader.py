"""Unified configuration loader with pluggable backends.

Story 20.1 — provides a centralized Config object that replaces scattered
os.getenv() calls.  Only the ``env`` backend is functional; ``vault`` and
``aws`` are stubs for Stories 20.2 / 20.3.

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


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_KNOWN_BACKENDS = {"env", "vault", "aws"}


def _create_backend(name: str) -> ConfigBackend:
    """Instantiate a backend by name."""
    if name == "env":
        return EnvBackend()
    if name == "vault":
        raise NotImplementedError(
            "Vault backend is not yet implemented (see Story 20.2)."
        )
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
