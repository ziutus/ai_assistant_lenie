"""Unit tests for mcp_server.config — config loading, missing vars, vault path warning."""

import sys
import logging
import tempfile
import pytest
from unittest.mock import patch

pytest.importorskip("unified_config_loader")  # Skip if not installed (e.g. uvx isolated env)

from unified_config_loader import Config  # noqa: E402


def _make_cfg(**kwargs) -> Config:
    """Build a Config object (dict subclass) with sensible defaults for testing."""
    full = {
        "POSTGRESQL_HOST": "localhost",
        "POSTGRESQL_DATABASE": "testdb",
        "POSTGRESQL_USER": "u",
        "POSTGRESQL_PASSWORD": "p",
        "POSTGRESQL_PORT": "5432",
        "OBSIDIAN_VAULT_PATH": tempfile.gettempdir(),  # cross-platform, always exists
    }
    full.update(kwargs)
    return Config(full)


def _reload_config_module(fake_cfg: Config):
    """Patch load_config and force-reload mcp_server.config from scratch."""
    sys.modules.pop("mcp_server.config", None)
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        import mcp_server.config as cfg_module
    return cfg_module


def test_settings_loads_with_all_required():
    """All required vars present → settings object created with correct defaults."""
    fake_cfg = _make_cfg()
    cfg_module = _reload_config_module(fake_cfg)
    assert cfg_module.settings.server_name == "lenie-mcp"
    assert cfg_module.settings.log_level == "INFO"
    assert cfg_module.settings.secrets_backend == "env"
    assert cfg_module.settings.postgresql_host == "localhost"


def test_settings_custom_server_name():
    """MCP_SERVER_NAME env var overrides the default server name."""
    fake_cfg = _make_cfg(MCP_SERVER_NAME="my-custom-mcp")
    cfg_module = _reload_config_module(fake_cfg)
    assert cfg_module.settings.server_name == "my-custom-mcp"


def test_settings_exits_on_missing_postgresql_host():
    """Missing POSTGRESQL_HOST causes SystemExit(1) at import time."""
    fake_cfg = Config({
        "POSTGRESQL_DATABASE": "testdb",
        "POSTGRESQL_USER": "u",
        "POSTGRESQL_PASSWORD": "p",
        "POSTGRESQL_PORT": "5432",
        "OBSIDIAN_VAULT_PATH": "/fake/vault",
    })
    sys.modules.pop("mcp_server.config", None)
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        with pytest.raises(SystemExit):
            import mcp_server.config  # noqa: F401


def test_settings_exits_on_missing_obsidian_vault_path():
    """Missing OBSIDIAN_VAULT_PATH causes SystemExit(1) at import time."""
    fake_cfg = Config({
        "POSTGRESQL_HOST": "localhost",
        "POSTGRESQL_DATABASE": "testdb",
        "POSTGRESQL_USER": "u",
        "POSTGRESQL_PASSWORD": "p",
        "POSTGRESQL_PORT": "5432",
    })
    sys.modules.pop("mcp_server.config", None)
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        with pytest.raises(SystemExit):
            import mcp_server.config  # noqa: F401


def test_settings_obsidian_path_nonexistent_warns(caplog):
    """Non-existent OBSIDIAN_VAULT_PATH logs a WARNING but does not raise."""
    fake_cfg = _make_cfg(OBSIDIAN_VAULT_PATH="/nonexistent/path/xyz123")
    sys.modules.pop("mcp_server.config", None)
    with patch("library.config_loader.load_config", return_value=fake_cfg):
        with caplog.at_level(logging.WARNING, logger="mcp_server.config"):
            import mcp_server.config  # noqa: F401
    assert "OBSIDIAN_VAULT_PATH does not exist" in caplog.text


def test_settings_log_level_override():
    """LOG_LEVEL env var is respected."""
    fake_cfg = _make_cfg(LOG_LEVEL="DEBUG")
    cfg_module = _reload_config_module(fake_cfg)
    assert cfg_module.settings.log_level == "DEBUG"
