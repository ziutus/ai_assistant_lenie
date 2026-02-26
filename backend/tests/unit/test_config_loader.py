import os
import unittest
from unittest.mock import patch, MagicMock

from library.config_loader import (
    Config,
    EnvBackend,
    VaultBackend,
    _create_backend,
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

    def test_aws_not_implemented(self):
        with self.assertRaises(NotImplementedError) as ctx:
            _create_backend("aws")
        self.assertIn("Story 20.3", str(ctx.exception))

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

    def test_aws_backend_not_implemented(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "aws"}, clear=False):
            with self.assertRaises(NotImplementedError):
                load_config()

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
            "ENV_DATA": "dev",
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
            "ENV_DATA": "dev",
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
        self.assertEqual(result["ENV_DATA"], "dev")
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
            "ENV_DATA": "dev",
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
            "ENV_DATA": "dev",
        }, clear=True):
            with patch.dict("sys.modules", {"hvac": mock_hvac_module}):
                backend = VaultBackend()
                result = backend.load()

        # Vault value overrides bootstrap
        self.assertEqual(result["ENV_DATA"], "prod")


if __name__ == "__main__":
    unittest.main()
