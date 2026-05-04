"""MCP server configuration — loads env vars via unified_config_loader at import time."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from library.config_loader import load_config

# Configure logging early via os.environ so that warnings emitted during
# _load_settings() (e.g. missing OBSIDIAN_VAULT_PATH) already use JSON format.
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)

logger = logging.getLogger(__name__)


@dataclass
class McpSettings:
    postgresql_host: str
    postgresql_database: str
    postgresql_user: str
    postgresql_password: str
    postgresql_port: str
    obsidian_vault_path: str
    secrets_backend: str
    server_name: str
    log_level: str


def _load_settings() -> McpSettings:
    cfg = load_config()

    vault_path = cfg.require("OBSIDIAN_VAULT_PATH")
    if not Path(vault_path).exists():
        logger.warning("OBSIDIAN_VAULT_PATH does not exist: %s", vault_path)

    return McpSettings(
        postgresql_host=cfg.require("POSTGRESQL_HOST"),
        postgresql_database=cfg.require("POSTGRESQL_DATABASE"),
        postgresql_user=cfg.require("POSTGRESQL_USER"),
        postgresql_password=cfg.require("POSTGRESQL_PASSWORD"),
        postgresql_port=cfg.require("POSTGRESQL_PORT"),
        obsidian_vault_path=vault_path,
        secrets_backend=cfg.require("SECRETS_BACKEND", "env"),
        server_name=cfg.require("MCP_SERVER_NAME", "lenie-mcp"),
        log_level=cfg.require("LOG_LEVEL", "INFO"),
    )


settings = _load_settings()
