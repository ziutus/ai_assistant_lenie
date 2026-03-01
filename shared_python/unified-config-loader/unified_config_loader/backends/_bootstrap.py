"""Bootstrap helpers shared across backends."""

import logging
import os

logger = logging.getLogger(__name__)

# Bootstrap env vars always read from the real environment,
# regardless of which backend is selected.
BOOTSTRAP_VARS = frozenset({
    "SECRETS_BACKEND",
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "SECRETS_ENV",
    "VAULT_ENV",  # deprecated: use SECRETS_ENV
    "ENV_DATA",
    "AWS_REGION",
    "PROJECT_CODE",
})


def get_secrets_env() -> str:
    """Return the environment name (dev/prod/qa).

    Reads ``SECRETS_ENV`` first; falls back to ``VAULT_ENV`` for backward
    compatibility.  Defaults to ``dev``.
    """
    env = os.environ.get("SECRETS_ENV") or os.environ.get("VAULT_ENV")
    if env is None:
        return "dev"
    if os.environ.get("VAULT_ENV") and not os.environ.get("SECRETS_ENV"):
        logger.warning("VAULT_ENV is deprecated, use SECRETS_ENV instead")
    return env


def get_project_code() -> str:
    """Return the project code (default ``lenie``)."""
    return os.environ.get("PROJECT_CODE", "lenie")
