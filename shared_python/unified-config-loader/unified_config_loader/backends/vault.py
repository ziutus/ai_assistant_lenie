"""HashiCorp Vault KV v2 configuration backend."""

import logging
import os
import sys

from unified_config_loader.backends._bootstrap import BOOTSTRAP_VARS, get_secrets_env, get_project_code

logger = logging.getLogger(__name__)


class VaultBackend:
    """Loads configuration from HashiCorp Vault KV v2.

    Path: ``secret/{PROJECT_CODE}/{SECRETS_ENV}``.
    """

    def load(self) -> dict[str, str]:
        vault_addr = os.environ.get("VAULT_ADDR")
        vault_token = os.environ.get("VAULT_TOKEN")
        secrets_env = get_secrets_env()
        project_code = get_project_code()

        if not vault_addr:
            logger.error("VAULT_ADDR must be set when using vault backend")
            sys.exit(1)
        if not vault_token:
            logger.error("VAULT_TOKEN must be set when using vault backend")
            sys.exit(1)

        try:
            import hvac
        except ImportError:
            logger.error("hvac package is required for vault backend: pip install hvac")
            sys.exit(1)

        try:
            client = hvac.Client(url=vault_addr, token=vault_token)
            if not client.is_authenticated():
                logger.error("Vault authentication failed at %s", vault_addr)
                sys.exit(1)

            secret_path = f"{project_code}/{secrets_env}"
            logger.info("Vault: reading secret at secret/%s", secret_path)
            response = client.secrets.kv.v2.read_secret_version(
                path=secret_path,
                mount_point="secret",
            )
            vault_data = response["data"]["data"]
        except SystemExit:
            raise
        except Exception as exc:
            logger.error("Failed to load config from Vault at %s: %s", vault_addr, exc)
            sys.exit(1)

        result = {k: os.environ[k] for k in BOOTSTRAP_VARS if k in os.environ}
        result.update(vault_data)
        return result
