"""Unified configuration loader with pluggable backends (env/vault/aws)."""

from unified_config_loader.config import (
    Config,
    load_config,
    get_config,
    reset_config,
    _create_backend,
    _injected_keys,
)
from unified_config_loader.backends.env import ConfigBackend, EnvBackend
from unified_config_loader.backends.vault import VaultBackend
from unified_config_loader.backends.aws import AWSSSMBackend
from unified_config_loader.backends._bootstrap import (
    BOOTSTRAP_VARS,
    get_secrets_env,
    get_project_code,
)
from unified_config_loader.exceptions import ConfigError, MissingVariableError

__all__ = [
    "Config",
    "load_config",
    "get_config",
    "reset_config",
    "ConfigBackend",
    "EnvBackend",
    "VaultBackend",
    "AWSSSMBackend",
    "BOOTSTRAP_VARS",
    "get_secrets_env",
    "get_project_code",
    "ConfigError",
    "MissingVariableError",
    "_create_backend",
    "_injected_keys",
]
