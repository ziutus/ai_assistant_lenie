"""Unified configuration loader with pluggable backends.

Provides a centralized Config object that replaces scattered os.getenv()
calls.  Backends: ``env`` (dotenv), ``vault`` (HashiCorp Vault KV v2),
``aws`` (AWS SSM Parameter Store).

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

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # Lambda environment — no .env files

# ---------------------------------------------------------------------------
# Config object
# ---------------------------------------------------------------------------


class Config(dict):
    """dict subclass with a ``require()`` helper that mirrors the legacy
    ``fetch_env_var()`` behaviour: return value, fall back to *default*,
    or log-and-exit when the key is missing."""

    def require(self, key: str, default: str | None = None) -> str:
        value = self.get(key)
        if value is not None:
            return value
        if default is not None:
            return default
        logging.error("Missing configuration variable %s, exiting...", key)
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
        if load_dotenv is not None:
            load_dotenv()
        return dict(os.environ)


# Bootstrap env vars that are always read from the real environment,
# regardless of which backend is selected.
_BOOTSTRAP_VARS = frozenset({
    "SECRETS_BACKEND",
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "SECRETS_ENV",
    "VAULT_ENV",  # deprecated: use SECRETS_ENV
    "ENV_DATA",
    "AWS_REGION",
    "PROJECT_CODE",
})


def _get_secrets_env() -> str:
    """Return the environment name (dev/prod/qa).

    Reads ``SECRETS_ENV`` first; falls back to ``VAULT_ENV`` for backward
    compatibility.  Defaults to ``dev``.
    """
    env = os.environ.get("SECRETS_ENV") or os.environ.get("VAULT_ENV")
    if env is None:
        return "dev"
    if os.environ.get("VAULT_ENV") and not os.environ.get("SECRETS_ENV"):
        logging.warning(
            "VAULT_ENV is deprecated for environment selection, use SECRETS_ENV instead"
        )
    return env


def _get_project_code() -> str:
    """Return the project code (default ``lenie``)."""
    return os.environ.get("PROJECT_CODE", "lenie")


class VaultBackend(ConfigBackend):
    """Loads configuration from HashiCorp Vault KV v2.

    Secrets are stored at ``secret/{PROJECT_CODE}/{SECRETS_ENV}`` as a
    single KV v2 secret containing all configuration key-value pairs.

    Bootstrap env vars (``VAULT_ADDR``, ``VAULT_TOKEN``, ``SECRETS_ENV``)
    must be set in the real environment (e.g. ``.env`` or shell).
    ``SECRETS_ENV`` defaults to ``dev`` if not set.
    """

    def load(self) -> dict[str, str]:
        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        secrets_env = _get_secrets_env()
        project_code = _get_project_code()

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

            secret_path = f"{project_code}/{secrets_env}"
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


class AWSSSMBackend(ConfigBackend):
    """Loads configuration from AWS SSM Parameter Store.

    All parameters are stored as SecureString under
    ``/{PROJECT_CODE}/{SECRETS_ENV}/<key>`` and loaded via
    ``GetParametersByPath``.

    Bootstrap env vars (``AWS_REGION``, ``SECRETS_ENV``) must be set in
    the real environment.  ``SECRETS_ENV`` defaults to ``dev``.
    Uses default boto3 credential chain (env vars, profile, instance role).
    """

    def load(self) -> dict[str, str]:
        secrets_env = _get_secrets_env()
        aws_region = os.environ.get("AWS_REGION", "eu-central-1")
        project_code = _get_project_code()

        try:
            import boto3
        except ImportError:
            logging.error("boto3 package is required for aws backend: pip install boto3")
            sys.exit(1)

        prefix = f"/{project_code}/{secrets_env}/"
        logging.info("AWS SSM: reading parameters under %s (region: %s)", prefix, aws_region)

        try:
            session = boto3.Session(region_name=aws_region)
            ssm = session.client("ssm")

            params = {}
            paginator = ssm.get_paginator("get_parameters_by_path")
            for page in paginator.paginate(
                Path=prefix,
                Recursive=False,
                WithDecryption=True,
            ):
                for param in page["Parameters"]:
                    key = param["Name"][len(prefix):]
                    params[key] = param["Value"]

        except Exception as exc:
            logging.error("Failed to load config from AWS SSM (%s): %s", prefix, exc)
            sys.exit(1)

        if not params:
            logging.warning("AWS SSM: no parameters found under %s", prefix)

        # Start with bootstrap env vars, overlay with SSM parameters.
        result = {k: os.environ[k] for k in _BOOTSTRAP_VARS if k in os.environ}
        result.update(params)
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
        return AWSSSMBackend()
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
_injected_keys: set[str] = set()


def load_config() -> Config:
    """Create (or return cached) Config from the selected backend.

    The backend is chosen via ``SECRETS_BACKEND`` env-var (default ``env``).

    For non-env backends (vault, aws), loaded values are injected into
    ``os.environ`` so that library modules still using ``os.getenv()``
    continue to work during the incremental migration.
    """
    global _config
    if _config is not None:
        return _config

    backend_name = os.environ.get("SECRETS_BACKEND", "env")
    logging.info("Config loader: using '%s' backend", backend_name)
    backend = _create_backend(backend_name)
    _config = Config(backend.load())

    # Inject into os.environ for backward compatibility with os.getenv() calls.
    if backend_name != "env":
        for key, value in _config.items():
            if isinstance(value, str):
                os.environ[key] = value
                _injected_keys.add(key)

    return _config


def get_config() -> Config:
    """Return the cached Config, auto-loading on first call."""
    if _config is None:
        return load_config()
    return _config


def reset_config() -> None:
    """Clear the cached Config and undo os.environ injection (intended for tests only)."""
    global _config
    _config = None
    for key in _injected_keys:
        os.environ.pop(key, None)
    _injected_keys.clear()
