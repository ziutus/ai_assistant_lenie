"""Unified configuration loader with pluggable backends.

Provides a centralized Config object with support for env/vault/aws backends.

Usage::

    from unified_config_loader import load_config

    cfg = load_config()
    db_host = cfg.require("POSTGRESQL_HOST")
    debug   = cfg.require("DEBUG", "false")
"""

import logging
import os
import sys

try:
    from dotenv import find_dotenv, load_dotenv
except ImportError:
    find_dotenv = None
    load_dotenv = None

from unified_config_loader.backends.env import EnvBackend
from unified_config_loader.backends.vault import VaultBackend
from unified_config_loader.backends.aws import AWSSSMBackend

logger = logging.getLogger(__name__)


class Config(dict):
    """dict subclass with a ``require()`` helper that returns value, falls
    back to *default*, or exits when the key is missing."""

    def require(self, key: str, default: str | None = None) -> str:
        value = self.get(key)
        if value is not None:
            return value
        if default is not None:
            return default
        logger.error("Missing configuration variable %s, exiting...", key)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_KNOWN_BACKENDS = {"env", "vault", "aws"}


def _create_backend(name: str):
    """Instantiate a backend by name."""
    if name == "env":
        return EnvBackend()
    if name == "vault":
        return VaultBackend()
    if name == "aws":
        return AWSSSMBackend()
    logger.error(
        "Unknown SECRETS_BACKEND value. Valid options: %s",
        ", ".join(sorted(_KNOWN_BACKENDS)),
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_config: Config | None = None
_injected_keys: set[str] = set()


def _load_bootstrap_dotenv() -> str | None:
    """Load ``.env`` for bootstrap variables before backend selection."""
    if load_dotenv is None:
        return None
    env_path = find_dotenv(usecwd=True) if find_dotenv is not None else None
    if env_path:
        load_dotenv(dotenv_path=env_path)
    return env_path or None


def load_config() -> Config:
    """Create (or return cached) Config from the selected backend.

    The backend is chosen via ``SECRETS_BACKEND`` env-var (default ``env``).
    For non-env backends, loaded values are injected into ``os.environ``.
    """
    global _config
    if _config is not None:
        return _config

    dotenv_path = _load_bootstrap_dotenv()
    if dotenv_path:
        logger.info("Config: loaded .env from %s", dotenv_path)

    backend_name = os.environ.get("SECRETS_BACKEND", "env")
    logger.debug("Config: backend selected")
    backend = _create_backend(backend_name)
    _config = Config(backend.load())

    if backend_name != "env":
        for key, value in _config.items():
            if isinstance(value, str):
                os.environ[key] = value
                _injected_keys.add(key)

    logger.info("Config: loaded %d variables", len(_config))
    return _config


def get_config() -> Config:
    """Return the cached Config, auto-loading on first call."""
    if _config is None:
        return load_config()
    return _config


def reset_config() -> None:
    """Clear cached Config and undo os.environ injection (for tests)."""
    global _config
    _config = None
    for key in _injected_keys:
        os.environ.pop(key, None)
    _injected_keys.clear()
