"""Backward-compatible re-export from unified_config_loader."""

from unified_config_loader import (  # noqa: F401
    Config,
    load_config,
    get_config,
    reset_config,
    ConfigBackend,
    EnvBackend,
    VaultBackend,
    AWSSSMBackend,
    ConfigError,
    MissingVariableError,
    get_secrets_env as _get_secrets_env,
    get_project_code as _get_project_code,
    _create_backend,
)
