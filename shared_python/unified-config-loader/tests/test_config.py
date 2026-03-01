"""Unit tests for unified_config_loader package."""

import os
from unittest.mock import MagicMock, patch

import pytest

from unified_config_loader import (
    AWSSSMBackend,
    Config,
    EnvBackend,
    VaultBackend,
    _create_backend,
    _injected_keys,
    get_config,
    get_project_code,
    get_secrets_env,
    load_config,
    reset_config,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    """Config dict subclass basics."""

    def test_dict_access(self):
        cfg = Config({"A": "1", "B": "2"})
        assert cfg["A"] == "1"
        assert "B" in cfg

    def test_require_existing_key(self):
        cfg = Config({"HOST": "localhost"})
        assert cfg.require("HOST") == "localhost"

    def test_require_with_default(self):
        cfg = Config({})
        assert cfg.require("MISSING", "fallback") == "fallback"

    def test_require_missing_exits(self):
        cfg = Config({})
        with pytest.raises(SystemExit):
            cfg.require("NONEXISTENT")

    def test_require_none_value_uses_default(self):
        cfg = Config({"KEY": None})
        assert cfg.require("KEY", "default") == "default"

    def test_require_returns_empty_string_as_value(self):
        cfg = Config({"KEY": ""})
        assert cfg.require("KEY") == ""

    def test_require_returns_value_even_with_default(self):
        cfg = Config({"KEY": "actual"})
        assert cfg.require("KEY", "default") == "actual"


# ---------------------------------------------------------------------------
# EnvBackend
# ---------------------------------------------------------------------------


class TestEnvBackend:
    """EnvBackend loads os.environ after load_dotenv()."""

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_load_returns_environ(self, mock_dotenv):
        backend = EnvBackend()
        with patch.dict(os.environ, {"TEST_VAR": "hello"}, clear=False):
            result = backend.load()
        mock_dotenv.assert_called_once()
        assert result["TEST_VAR"] == "hello"
        assert isinstance(result, dict)

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_load_returns_copy(self, mock_dotenv):
        backend = EnvBackend()
        result = backend.load()
        result["NEW_KEY"] = "injected"
        assert "NEW_KEY" not in os.environ

    def test_load_includes_existing_env_vars(self):
        backend = EnvBackend()
        result = backend.load()
        assert "PATH" in result


# ---------------------------------------------------------------------------
# _create_backend factory
# ---------------------------------------------------------------------------


class TestCreateBackend:
    """Backend factory."""

    def test_env_backend(self):
        backend = _create_backend("env")
        assert isinstance(backend, EnvBackend)

    def test_vault_backend(self):
        backend = _create_backend("vault")
        assert isinstance(backend, VaultBackend)

    def test_aws_backend(self):
        backend = _create_backend("aws")
        assert isinstance(backend, AWSSSMBackend)

    def test_unknown_backend_exits(self):
        with pytest.raises(SystemExit):
            _create_backend("redis")


# ---------------------------------------------------------------------------
# load_config / get_config / reset_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """load_config / get_config / reset_config."""

    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_default_backend_is_env(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg = load_config()
        assert isinstance(cfg, Config)

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_explicit_env_backend(self, mock_dotenv):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            cfg = load_config()
        assert isinstance(cfg, Config)

    def test_unknown_backend_exits(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "redis"}, clear=False):
            with pytest.raises(SystemExit):
                load_config()

    @patch("unified_config_loader.backends.vault.VaultBackend.load")
    def test_vault_backend_loads(self, mock_vault_load):
        mock_vault_load.return_value = {"DB_HOST": "vault-host", "ENV_DATA": "dev"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            cfg = load_config()
        assert cfg["DB_HOST"] == "vault-host"
        mock_vault_load.assert_called_once()

    @patch("unified_config_loader.backends.aws.AWSSSMBackend.load")
    def test_aws_backend_loads(self, mock_ssm_load):
        mock_ssm_load.return_value = {"DB_HOST": "ssm-host", "ENV_DATA": "dev"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "aws"}, clear=False):
            cfg = load_config()
        assert cfg["DB_HOST"] == "ssm-host"
        mock_ssm_load.assert_called_once()

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_singleton_same_instance(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg1 = load_config()
            cfg2 = load_config()
        assert cfg1 is cfg2

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_get_config_auto_loads(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg = get_config()
        assert isinstance(cfg, Config)

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_reset_clears_cache(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg1 = load_config()
            reset_config()
            cfg2 = load_config()
        assert cfg1 is not cfg2


# ---------------------------------------------------------------------------
# VaultBackend
# ---------------------------------------------------------------------------


class TestVaultBackend:
    """VaultBackend reads secrets from HashiCorp Vault KV v2."""

    def test_missing_vault_addr_exits(self):
        with patch.dict(os.environ, {"VAULT_TOKEN": "tok"}, clear=True):
            backend = VaultBackend()
            with pytest.raises(SystemExit):
                backend.load()

    def test_missing_vault_token_exits(self):
        with patch.dict(os.environ, {"VAULT_ADDR": "http://vault:8200"}, clear=True):
            backend = VaultBackend()
            with pytest.raises(SystemExit):
                backend.load()

    def test_auth_failure_exits(self):
        mock_hvac_module = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        mock_hvac_module.Client.return_value = mock_client

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "bad-token",
            "SECRETS_ENV": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                with pytest.raises(SystemExit):
                    backend.load()

    def test_successful_load(self):
        mock_hvac_module = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {
                    "POSTGRESQL_HOST": "db.vault.local",
                    "OPENAI_API_KEY": "sk-vault-secret",
                }
            }
        }
        mock_hvac_module.Client.return_value = mock_client

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "test-token",
            "SECRETS_ENV": "dev",
            "SECRETS_BACKEND": "vault",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                result = backend.load()

        assert result["POSTGRESQL_HOST"] == "db.vault.local"
        assert result["OPENAI_API_KEY"] == "sk-vault-secret"
        assert result["VAULT_ADDR"] == "http://vault:8200"
        assert result["SECRETS_ENV"] == "dev"
        assert result["SECRETS_BACKEND"] == "vault"
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="lenie/dev",
            mount_point="secret",
        )

    def test_connection_error_exits(self):
        mock_hvac_module = MagicMock()
        mock_hvac_module.Client.side_effect = ConnectionError("refused")

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "tok",
            "SECRETS_ENV": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                with pytest.raises(SystemExit):
                    backend.load()

    def test_vault_secret_overrides_bootstrap(self):
        """Vault secrets take precedence over bootstrap env vars."""
        mock_hvac_module = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"ENV_DATA": "prod"}}
        }
        mock_hvac_module.Client.return_value = mock_client

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "tok",
            "SECRETS_ENV": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                result = backend.load()

        assert result["ENV_DATA"] == "prod"

    def test_vault_env_backward_compat(self):
        """VAULT_ENV still works when SECRETS_ENV is not set."""
        mock_hvac_module = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"KEY": "val"}}
        }
        mock_hvac_module.Client.return_value = mock_client

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "tok",
            "VAULT_ENV": "staging",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                result = backend.load()

        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="lenie/staging",
            mount_point="secret",
        )
        assert result["KEY"] == "val"


# ---------------------------------------------------------------------------
# AWSSSMBackend
# ---------------------------------------------------------------------------


class TestAWSSSMBackend:
    """AWSSSMBackend reads secrets from AWS SSM Parameter Store."""

    def test_successful_load(self):
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Parameters": [
                    {"Name": "/lenie/dev/POSTGRESQL_HOST", "Value": "db.ssm.local"},
                    {"Name": "/lenie/dev/OPENAI_API_KEY", "Value": "sk-ssm-secret"},
                ]
            }
        ]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
            "SECRETS_BACKEND": "aws",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        assert result["POSTGRESQL_HOST"] == "db.ssm.local"
        assert result["OPENAI_API_KEY"] == "sk-ssm-secret"
        assert result["SECRETS_ENV"] == "dev"
        assert result["AWS_REGION"] == "eu-central-1"
        assert result["SECRETS_BACKEND"] == "aws"
        mock_paginator.paginate.assert_called_once_with(
            Path="/lenie/dev/",
            Recursive=False,
            WithDecryption=True,
        )

    def test_default_env_is_dev(self):
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Parameters": [{"Name": "/lenie/dev/KEY", "Value": "val"}]}
        ]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        mock_paginator.paginate.assert_called_once_with(
            Path="/lenie/dev/",
            Recursive=False,
            WithDecryption=True,
        )
        assert result["KEY"] == "val"

    def test_connection_error_exits(self):
        mock_boto3_module = MagicMock()
        mock_boto3_module.Session.side_effect = Exception("No credentials")

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                with pytest.raises(SystemExit):
                    backend.load()

    def test_empty_result_warns_but_returns(self):
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"Parameters": []}]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        assert result["SECRETS_ENV"] == "dev"
        assert "POSTGRESQL_HOST" not in result

    def test_ssm_overrides_bootstrap(self):
        """SSM parameters take precedence over bootstrap env vars."""
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Parameters": [{"Name": "/lenie/dev/ENV_DATA", "Value": "prod"}]}
        ]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
            "ENV_DATA": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        assert result["ENV_DATA"] == "prod"

    def test_vault_env_backward_compat(self):
        """VAULT_ENV still works when SECRETS_ENV is not set."""
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Parameters": [{"Name": "/lenie/staging/KEY", "Value": "val"}]}
        ]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {
            "VAULT_ENV": "staging",
            "AWS_REGION": "eu-central-1",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        mock_paginator.paginate.assert_called_once_with(
            Path="/lenie/staging/",
            Recursive=False,
            WithDecryption=True,
        )
        assert result["KEY"] == "val"

    def test_project_code_parametrization(self):
        """PROJECT_CODE env var overrides hardcoded 'lenie' in path."""
        mock_boto3_module = MagicMock()
        mock_ssm = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Parameters": [{"Name": "/myproj/dev/KEY", "Value": "val"}]}
        ]
        mock_ssm.get_paginator.return_value = mock_paginator
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ssm
        mock_boto3_module.Session.return_value = mock_session

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
            "PROJECT_CODE": "myproj",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                result = backend.load()

        mock_paginator.paginate.assert_called_once_with(
            Path="/myproj/dev/",
            Recursive=False,
            WithDecryption=True,
        )
        assert result["KEY"] == "val"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """get_secrets_env and get_project_code helpers."""

    def test_secrets_env_from_secrets_env(self):
        with patch.dict(os.environ, {"SECRETS_ENV": "prod"}, clear=True):
            assert get_secrets_env() == "prod"

    def test_secrets_env_fallback_to_vault_env(self):
        with patch.dict(os.environ, {"VAULT_ENV": "staging"}, clear=True):
            assert get_secrets_env() == "staging"

    def test_secrets_env_prefers_secrets_env(self):
        with patch.dict(os.environ, {"SECRETS_ENV": "prod", "VAULT_ENV": "dev"}, clear=True):
            assert get_secrets_env() == "prod"

    def test_secrets_env_default_dev(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_secrets_env() == "dev"

    def test_project_code_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_project_code() == "lenie"

    def test_project_code_custom(self):
        with patch.dict(os.environ, {"PROJECT_CODE": "myproj"}, clear=True):
            assert get_project_code() == "myproj"


# ---------------------------------------------------------------------------
# Backward compatibility injection
# ---------------------------------------------------------------------------


class TestBackwardCompatInjection:
    """Verify os.environ injection for backward compatibility."""

    def setup_method(self):
        reset_config()

    def teardown_method(self):
        reset_config()

    @patch("unified_config_loader.backends.vault.VaultBackend.load")
    def test_vault_values_injected_into_environ(self, mock_vault_load):
        mock_vault_load.return_value = {"DB_HOST": "vault-host", "DB_PORT": "5432"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            assert os.environ.get("DB_HOST") == "vault-host"
            assert os.environ.get("DB_PORT") == "5432"

    @patch("unified_config_loader.backends.aws.AWSSSMBackend.load")
    def test_aws_values_injected_into_environ(self, mock_ssm_load):
        mock_ssm_load.return_value = {"DB_HOST": "ssm-host", "API_KEY": "ssm-key"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "aws"}, clear=False):
            load_config()
            assert os.environ.get("DB_HOST") == "ssm-host"
            assert os.environ.get("API_KEY") == "ssm-key"

    @patch("unified_config_loader.backends.env.load_dotenv")
    def test_env_backend_does_not_inject(self, mock_dotenv):
        """env backend should NOT inject into os.environ."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            load_config()
            assert len(_injected_keys) == 0

    @patch("unified_config_loader.backends.vault.VaultBackend.load")
    def test_reset_removes_injected_keys(self, mock_vault_load):
        mock_vault_load.return_value = {"INJECTED_TEST_KEY": "test-value"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            assert os.environ.get("INJECTED_TEST_KEY") == "test-value"
            reset_config()
            assert os.environ.get("INJECTED_TEST_KEY") is None

    @patch("unified_config_loader.backends.vault.VaultBackend.load")
    def test_injected_values_accessible_via_os_getenv(self, mock_vault_load):
        """Library modules using os.getenv() should see injected values."""
        mock_vault_load.return_value = {
            "POSTGRESQL_HOST": "vault-db.local",
            "POSTGRESQL_PORT": "5432",
        }
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            assert os.getenv("POSTGRESQL_HOST") == "vault-db.local"
            assert os.getenv("POSTGRESQL_PORT") == "5432"
