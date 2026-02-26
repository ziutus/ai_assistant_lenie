import os
import unittest
from unittest.mock import patch

from library.config_loader import (
    Config,
    EnvBackend,
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

    def test_vault_not_implemented(self):
        with self.assertRaises(NotImplementedError) as ctx:
            _create_backend("vault")
        self.assertIn("Story 20.2", str(ctx.exception))

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

    def test_vault_backend_not_implemented(self):
        with patch.dict(os.environ, {"SECRETS_BACKEND": "vault"}, clear=False):
            with self.assertRaises(NotImplementedError):
                load_config()

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


if __name__ == "__main__":
    unittest.main()
