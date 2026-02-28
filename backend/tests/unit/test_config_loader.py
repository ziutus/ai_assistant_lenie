import os
import unittest
from unittest.mock import patch, MagicMock

from library.config_loader import (
    AWSSSMBackend,
    Config,
    EnvBackend,
    VaultBackend,
    _create_backend,
    _get_project_code,
    _get_secrets_env,
    get_config,
    load_config,
    reset_config,
)


class TestConfig(unittest.TestCase):
    """Config dict subclass basics."""

    def test_dict_access(self):
        cfg = Config({"A": "1", "B": "2"})
        self.assertEqual(cfg["A"], "1")
        self.assertIn("B", cfg)

    def test_require_existing_key(self):
        cfg = Config({"HOST": "localhost"})
        self.assertEqual(cfg.require("HOST"), "localhost")

    def test_require_with_default(self):
        cfg = Config({})
        self.assertEqual(cfg.require("MISSING", "fallback"), "fallback")

    def test_require_missing_exits(self):
        cfg = Config({})
        with self.assertRaises(SystemExit):
            cfg.require("NONEXISTENT")

    def test_require_none_value_uses_default(self):
        cfg = Config({"KEY": None})
        self.assertEqual(cfg.require("KEY", "default"), "default")


class TestEnvBackend(unittest.TestCase):
    """EnvBackend loads os.environ after load_dotenv()."""

    @patch("library.config_loader.load_dotenv")
    def test_load_returns_environ(self, mock_dotenv):
        backend = EnvBackend()
        with patch.dict(os.environ, {"TEST_VAR": "hello"}, clear=False):
            result = backend.load()
        mock_dotenv.assert_called_once()
        self.assertEqual(result["TEST_VAR"], "hello")
        self.assertIsInstance(result, dict)

    @patch("library.config_loader.load_dotenv")
    def test_load_returns_copy(self, mock_dotenv):
        backend = EnvBackend()
        result = backend.load()
        result["NEW_KEY"] = "injected"
        self.assertNotIn("NEW_KEY", os.environ)


class TestCreateBackend(unittest.TestCase):
    """Backend factory."""

    def test_env_backend(self):
        backend = _create_backend("env")
        self.assertIsInstance(backend, EnvBackend)

    def test_vault_backend(self):
        backend = _create_backend("vault")
        self.assertIsInstance(backend, VaultBackend)

    def test_aws_backend(self):
        backend = _create_backend("aws")
        self.assertIsInstance(backend, AWSSSMBackend)

    def test_unknown_backend_exits(self):
        with self.assertRaises(SystemExit):
            _create_backend("redis")


class TestLoadConfig(unittest.TestCase):
    """load_config / get_config / reset_config."""

    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    @patch("library.config_loader.load_dotenv")
    def test_default_backend_is_env(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg = load_config()
        self.assertIsInstance(cfg, Config)

    @patch("library.config_loader.load_dotenv")
    def test_explicit_env_backend(self, mock_dotenv):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            cfg = load_config()
        self.assertIsInstance(cfg, Config)

    def test_unknown_backend_exits(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "redis"}, clear=False):
            with self.assertRaises(SystemExit):
                load_config()

    @patch("library.config_loader.VaultBackend.load")
    def test_vault_backend_loads(self, mock_vault_load):
        mock_vault_load.return_value = {"DB_HOST": "vault-host", "ENV_DATA": "dev"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            cfg = load_config()
        self.assertEqual(cfg["DB_HOST"], "vault-host")
        mock_vault_load.assert_called_once()

    @patch("library.config_loader.AWSSSMBackend.load")
    def test_aws_backend_loads(self, mock_ssm_load):
        mock_ssm_load.return_value = {"DB_HOST": "ssm-host", "ENV_DATA": "dev"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "aws"}, clear=False):
            cfg = load_config()
        self.assertEqual(cfg["DB_HOST"], "ssm-host")
        mock_ssm_load.assert_called_once()

    @patch("library.config_loader.load_dotenv")
    def test_singleton_same_instance(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg1 = load_config()
            cfg2 = load_config()
        self.assertIs(cfg1, cfg2)

    @patch("library.config_loader.load_dotenv")
    def test_get_config_auto_loads(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg = get_config()
        self.assertIsInstance(cfg, Config)

    @patch("library.config_loader.load_dotenv")
    def test_reset_clears_cache(self, mock_dotenv):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRETS_BACKEND", None)
            cfg1 = load_config()
            reset_config()
            cfg2 = load_config()
        self.assertIsNot(cfg1, cfg2)


class TestVaultBackend(unittest.TestCase):
    """VaultBackend reads secrets from HashiCorp Vault KV v2."""

    def test_missing_vault_addr_exits(self):
        with patch.dict(os.environ, {"VAULT_TOKEN": "tok"}, clear=True):
            backend = VaultBackend()
            with self.assertRaises(SystemExit):
                backend.load()

    def test_missing_vault_token_exits(self):
        with patch.dict(os.environ, {"VAULT_ADDR": "http://vault:8200"}, clear=True):
            backend = VaultBackend()
            with self.assertRaises(SystemExit):
                backend.load()

    @patch("library.config_loader.hvac", create=True)
    def test_auth_failure_exits(self, mock_hvac_module):
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        mock_hvac_module.Client.return_value = mock_client

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "bad-token",
            "SECRETS_ENV": "dev",
        }, clear=True):
            # Need to patch hvac import inside VaultBackend.load()
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                with self.assertRaises(SystemExit):
                    backend.load()

    @patch("library.config_loader.hvac", create=True)
    def test_successful_load(self, mock_hvac_module):
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

        # Vault secrets present
        self.assertEqual(result["POSTGRESQL_HOST"], "db.vault.local")
        self.assertEqual(result["OPENAI_API_KEY"], "sk-vault-secret")
        # Bootstrap env vars preserved
        self.assertEqual(result["VAULT_ADDR"], "http://vault:8200")
        self.assertEqual(result["SECRETS_ENV"], "dev")
        self.assertEqual(result["SECRETS_BACKEND"], "vault")
        # Correct Vault path called
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="lenie/dev",
            mount_point="secret",
        )

    @patch("library.config_loader.hvac", create=True)
    def test_connection_error_exits(self, mock_hvac_module):
        mock_hvac_module.Client.side_effect = ConnectionError("refused")

        with patch.dict(os.environ, {
            "VAULT_ADDR": "http://vault:8200",
            "VAULT_TOKEN": "tok",
            "SECRETS_ENV": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                with self.assertRaises(SystemExit):
                    backend.load()

    @patch("library.config_loader.hvac", create=True)
    def test_vault_secret_overrides_bootstrap(self, mock_hvac_module):
        """Vault secrets take precedence over bootstrap env vars."""
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

        # Vault value overrides bootstrap
        self.assertEqual(result["ENV_DATA"], "prod")

    @patch("library.config_loader.hvac", create=True)
    def test_vault_env_backward_compat(self, mock_hvac_module):
        """VAULT_ENV still works when SECRETS_ENV is not set (backward compat)."""
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
        self.assertEqual(result["KEY"], "val")


class TestAWSSSMBackend(unittest.TestCase):
    """AWSSSMBackend reads secrets from AWS SSM Parameter Store."""

    @patch("library.config_loader.boto3", create=True)
    def test_successful_load(self, mock_boto3_module):
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

        self.assertEqual(result["POSTGRESQL_HOST"], "db.ssm.local")
        self.assertEqual(result["OPENAI_API_KEY"], "sk-ssm-secret")
        # Bootstrap env vars preserved
        self.assertEqual(result["SECRETS_ENV"], "dev")
        self.assertEqual(result["AWS_REGION"], "eu-central-1")
        self.assertEqual(result["SECRETS_BACKEND"], "aws")
        # Correct path used
        mock_paginator.paginate.assert_called_once_with(
            Path="/lenie/dev/",
            Recursive=False,
            WithDecryption=True,
        )

    @patch("library.config_loader.boto3", create=True)
    def test_default_env_is_dev(self, mock_boto3_module):
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

        # Default VAULT_ENV=dev, so path is /lenie/dev/
        mock_paginator.paginate.assert_called_once_with(
            Path="/lenie/dev/",
            Recursive=False,
            WithDecryption=True,
        )
        self.assertEqual(result["KEY"], "val")

    @patch("library.config_loader.boto3", create=True)
    def test_connection_error_exits(self, mock_boto3_module):
        mock_boto3_module.Session.side_effect = Exception("No credentials")

        with patch.dict(os.environ, {
            "SECRETS_ENV": "dev",
            "AWS_REGION": "eu-central-1",
        }, clear=True):
            with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
                backend = AWSSSMBackend()
                with self.assertRaises(SystemExit):
                    backend.load()

    @patch("library.config_loader.boto3", create=True)
    def test_empty_result_warns_but_returns(self, mock_boto3_module):
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

        # Should return bootstrap vars even with no SSM params
        self.assertEqual(result["SECRETS_ENV"], "dev")
        self.assertNotIn("POSTGRESQL_HOST", result)

    @patch("library.config_loader.boto3", create=True)
    def test_ssm_overrides_bootstrap(self, mock_boto3_module):
        """SSM parameters take precedence over bootstrap env vars."""
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

        self.assertEqual(result["ENV_DATA"], "prod")

    @patch("library.config_loader.boto3", create=True)
    def test_vault_env_backward_compat(self, mock_boto3_module):
        """VAULT_ENV still works when SECRETS_ENV is not set (backward compat)."""
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
        self.assertEqual(result["KEY"], "val")

    @patch("library.config_loader.boto3", create=True)
    def test_project_code_parametrization(self, mock_boto3_module):
        """PROJECT_CODE env var overrides hardcoded 'lenie' in path."""
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
        self.assertEqual(result["KEY"], "val")


class TestHelpers(unittest.TestCase):
    """_get_secrets_env and _get_project_code helpers."""

    def test_secrets_env_from_secrets_env(self):
        with patch.dict(os.environ, {"SECRETS_ENV": "prod"}, clear=True):
            self.assertEqual(_get_secrets_env(), "prod")

    def test_secrets_env_fallback_to_vault_env(self):
        with patch.dict(os.environ, {"VAULT_ENV": "staging"}, clear=True):
            self.assertEqual(_get_secrets_env(), "staging")

    def test_secrets_env_prefers_secrets_env(self):
        with patch.dict(os.environ, {"SECRETS_ENV": "prod", "VAULT_ENV": "dev"}, clear=True):
            self.assertEqual(_get_secrets_env(), "prod")

    def test_secrets_env_default_dev(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_secrets_env(), "dev")

    def test_project_code_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_project_code(), "lenie")

    def test_project_code_custom(self):
        with patch.dict(os.environ, {"PROJECT_CODE": "myproj"}, clear=True):
            self.assertEqual(_get_project_code(), "myproj")


class TestBackwardCompatInjection(unittest.TestCase):
    """Verify os.environ injection for backward compatibility with library modules
    that still use os.getenv() during the incremental migration."""

    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    @patch("library.config_loader.VaultBackend.load")
    def test_vault_values_injected_into_environ(self, mock_vault_load):
        mock_vault_load.return_value = {"DB_HOST": "vault-host", "DB_PORT": "5432"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            self.assertEqual(os.environ.get("DB_HOST"), "vault-host")
            self.assertEqual(os.environ.get("DB_PORT"), "5432")

    @patch("library.config_loader.AWSSSMBackend.load")
    def test_aws_values_injected_into_environ(self, mock_ssm_load):
        mock_ssm_load.return_value = {"DB_HOST": "ssm-host", "API_KEY": "ssm-key"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "aws"}, clear=False):
            load_config()
            self.assertEqual(os.environ.get("DB_HOST"), "ssm-host")
            self.assertEqual(os.environ.get("API_KEY"), "ssm-key")

    @patch("library.config_loader.load_dotenv")
    def test_env_backend_does_not_inject(self, mock_dotenv):
        """env backend should NOT inject into os.environ (values are already there)."""
        with patch.dict(os.environ, {"SECRETS_BACKEND": "env"}, clear=False):
            load_config()
            # No new keys injected (env backend reads os.environ directly)
            # The _injected_keys set should be empty
            from library.config_loader import _injected_keys
            self.assertEqual(len(_injected_keys), 0)

    @patch("library.config_loader.VaultBackend.load")
    def test_reset_removes_injected_keys(self, mock_vault_load):
        mock_vault_load.return_value = {"INJECTED_TEST_KEY": "test-value"}
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            self.assertEqual(os.environ.get("INJECTED_TEST_KEY"), "test-value")
            reset_config()
            self.assertIsNone(os.environ.get("INJECTED_TEST_KEY"))

    @patch("library.config_loader.VaultBackend.load")
    def test_injected_values_accessible_via_os_getenv(self, mock_vault_load):
        """Library modules using os.getenv() should see injected values."""
        mock_vault_load.return_value = {
            "POSTGRESQL_HOST": "vault-db.local",
            "POSTGRESQL_PORT": "5432",
        }
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            load_config()
            # Simulate what library modules do: os.getenv()
            self.assertEqual(os.getenv("POSTGRESQL_HOST"), "vault-db.local")
            self.assertEqual(os.getenv("POSTGRESQL_PORT"), "5432")


if __name__ == "__main__":
    unittest.main()
