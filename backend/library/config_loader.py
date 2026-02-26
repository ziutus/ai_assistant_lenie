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
    "VAULT_ENV",
    "ENV_DATA",
    "AWS_REGION",
})


class VaultBackend(ConfigBackend):
    """Loads configuration from HashiCorp Vault KV v2.

    Secrets are stored at ``secret/lenie/{VAULT_ENV}`` as a single KV v2
    secret containing all configuration key-value pairs.

    Bootstrap env vars (``VAULT_ADDR``, ``VAULT_TOKEN``, ``VAULT_ENV``)
    must be set in the real environment (e.g. ``.env`` or shell).
    ``VAULT_ENV`` defaults to ``dev`` if not set.
    """

    def load(self) -> dict[str, str]:
        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        vault_env = os.environ.get("VAULT_ENV", "dev")

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

            secret_path = f"lenie/{vault_env}"
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
    ``/lenie/{VAULT_ENV}/<key>`` and loaded via ``GetParametersByPath``.

    Bootstrap env vars (``AWS_REGION``, ``VAULT_ENV``) must be set in
    the real environment.  ``VAULT_ENV`` defaults to ``dev``.
    Uses default boto3 credential chain (env vars, profile, instance role).
    """

    def load(self) -> dict[str, str]:
        vault_env = os.environ.get("VAULT_ENV", "dev")
        aws_region = os.environ.get("AWS_REGION", "eu-central-1")

        try:
            import boto3
        except ImportError:
            logging.error("boto3 package is required for aws backend: pip install boto3")
            sys.exit(1)

        prefix = f"/lenie/{vault_env}/"
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
