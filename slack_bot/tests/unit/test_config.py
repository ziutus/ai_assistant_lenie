"""Unit tests for src.config module."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.config import (
    AWSSSMBackend,
    Config,
    EnvBackend,
    VaultBackend,
    _create_backend,
    _get_project_code,
    _get_secrets_env,
    load_config,
    reset_config,
)


class TestConfig:
    """Tests for Config dict subclass."""

    def test_require_returns_value_when_present(self):
        cfg = Config({"KEY": "value"})
        assert cfg.require("KEY") == "value"

    def test_require_returns_default_when_key_missing(self):
        cfg = Config({})
        assert cfg.require("MISSING", "fallback") == "fallback"

    def test_require_exits_when_key_missing_no_default(self):
        cfg = Config({})
        with pytest.raises(SystemExit) as exc_info:
            cfg.require("MISSING")
        assert exc_info.value.code == 1

    def test_require_returns_value_even_with_default(self):
        cfg = Config({"KEY": "actual"})
        assert cfg.require("KEY", "default") == "actual"

    def test_require_returns_empty_string_as_value(self):
        cfg = Config({"KEY": ""})
        assert cfg.require("KEY") == ""

    def test_config_is_dict(self):
        cfg = Config({"A": "1", "B": "2"})
        assert cfg["A"] == "1"
        assert len(cfg) == 2


class TestEnvBackend:
    """Tests for EnvBackend."""

    def test_load_returns_environ_dict(self):
        backend = EnvBackend()
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}, clear=False):
            result = backend.load()
        assert result["TEST_VAR"] == "test_value"
        assert isinstance(result, dict)

    def test_load_includes_existing_env_vars(self):
        backend = EnvBackend()
        result = backend.load()
        # PATH should always exist
        assert "PATH" in result


class TestGetSecretsEnv:
    """Tests for _get_secrets_env helper."""

    def test_defaults_to_dev(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SECRETS_ENV", None)
            os.environ.pop("VAULT_ENV", None)
            assert _get_secrets_env() == "dev"

    def test_reads_secrets_env(self):
        with patch.dict(os.environ, {"SECRETS_ENV": "prod"}, clear=False):
            assert _get_secrets_env() == "prod"

    def test_falls_back_to_vault_env(self):
        env = {k: v for k, v in os.environ.items()}
        env.pop("SECRETS_ENV", None)
        env["VAULT_ENV"] = "qa"
        with patch.dict(os.environ, env, clear=True):
            assert _get_secrets_env() == "qa"


class TestGetProjectCode:
    """Tests for _get_project_code helper."""

    def test_defaults_to_lenie(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECT_CODE", None)
            assert _get_project_code() == "lenie"

    def test_reads_project_code(self):
        with patch.dict(os.environ, {"PROJECT_CODE": "myproject"}, clear=False):
            assert _get_project_code() == "myproject"


class TestCreateBackend:
    """Tests for _create_backend factory."""

    def test_creates_env_backend(self):
        backend = _create_backend("env")
        assert isinstance(backend, EnvBackend)

    def test_creates_vault_backend(self):
        backend = _create_backend("vault")
        assert isinstance(backend, VaultBackend)

    def test_creates_aws_backend(self):
        backend = _create_backend("aws")
        assert isinstance(backend, AWSSSMBackend)

    def test_exits_on_unknown_backend(self):
        with pytest.raises(SystemExit) as exc_info:
            _create_backend("unknown")
        assert exc_info.value.code == 1


class TestLoadConfig:
    """Tests for load_config singleton factory."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_returns_config_instance(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            cfg = load_config()
        assert isinstance(cfg, Config)

    def test_returns_singleton(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            cfg1 = load_config()
            cfg2 = load_config()
        assert cfg1 is cfg2

    def test_defaults_to_env_backend(self):
        with patch("unified_config_loader.config._load_bootstrap_dotenv", return_value=None):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SECRETS_BACKEND", None)
                cfg = load_config()
        assert isinstance(cfg, Config)

    def test_reset_clears_singleton(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            cfg1 = load_config()
            reset_config()
            cfg2 = load_config()
        assert cfg1 is not cfg2


class TestVaultBackendUnit:
    """Unit tests for VaultBackend (mocked hvac)."""

    def test_exits_without_vault_addr(self):
        backend = VaultBackend()
        with patch.dict(os.environ, {"VAULT_TOKEN": "tok"}, clear=True):
            with pytest.raises(SystemExit):
                backend.load()

    def test_exits_without_vault_token(self):
        backend = VaultBackend()
        with patch.dict(os.environ, {"VAULT_ADDR": "http://vault:8200"}, clear=True):
            with pytest.raises(SystemExit):
                backend.load()

    def test_loads_from_vault(self):
        backend = VaultBackend()
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"SLACK_BOT_TOKEN": "xoxb-test", "API_KEY": "secret123"}}
        }
        mock_hvac.Client.return_value = mock_client

        env = {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "test-token",
            "SECRETS_ENV": "dev",
            "PROJECT_CODE": "lenie",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"hvac": mock_hvac}):
                result = backend.load()

        assert result["SLACK_BOT_TOKEN"] == "xoxb-test"
        assert result["API_KEY"] == "secret123"
        assert result["VAULT_ADDR"] == "http://vault:8200"
