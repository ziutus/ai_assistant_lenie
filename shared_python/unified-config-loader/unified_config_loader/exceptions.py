"""Custom exceptions for unified_config_loader."""


class ConfigError(Exception):
    """Base exception for configuration errors."""


class MissingVariableError(ConfigError):
    """Raised when a required configuration variable is missing."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Missing configuration variable: {key}")
