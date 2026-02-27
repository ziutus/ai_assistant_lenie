"""Unit tests for env_to_vault.py — YAML-driven commands.

Run: cd scripts && PYTHONPATH=. uvx --with ruamel.yaml pytest tests/test_env_to_vault.py -v
"""

import os
import sys
import tempfile
import textwrap
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scripts/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import env_to_vault

MINIMAL_YAML = textwrap.dedent("""\
    metadata:
      project_code: lenie
      version: "1.0"

    backends:
      test-vault:
        type: vault_kv2
        mount: secret
        path_pattern: "{project_code}/{env}"
      test-ssm:
        type: aws_ssm
        path_pattern: "/{project_code}/{env}/{key}"
        region: eu-central-1
        profile: default

    environments:
      dev:
        backends: [test-vault, test-ssm]
      prod:
        backends: [test-ssm]

    groups:
      bootstrap:
        variables:
          SECRETS_BACKEND:
            description: "Secret backend"
            type: config
            required: true
            default: "env"
            example: "env"
          SECRETS_ENV:
            description: "Environment name"
            type: config
            required: true
            default: "dev"
            example: "dev"
          VAULT_ADDR:
            description: "Vault URL"
            type: config
            required: false
          VAULT_TOKEN:
            description: "Vault token"
            type: secret
            required: false
          VAULT_ENV:
            description: "Deprecated"
            type: config
            required: false
            status: deprecated
      database:
        # Test comment that should be preserved
        variables:
          POSTGRESQL_HOST:
            description: "Database host"
            type: config
            required: true
            example: "localhost"
          POSTGRESQL_PASSWORD:
            description: "Database password"
            type: secret
            required: true
      llm:
        variables:
          OPENAI_API_KEY:
            description: "OpenAI key"
            type: secret
            required: false
          LLM_PROVIDER:
            description: "LLM provider"
            type: config
            required: true
            example: "openai"
""")


def _write_yaml(content: str) -> str:
    """Write YAML to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _write_env(content: str) -> str:
    """Write .env content to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _load_yaml_directly(path: str) -> dict:
    """Load YAML file directly for test setup (bypasses load_classification cache)."""
    from ruamel.yaml import YAML
    yaml = YAML(typ="rt")
    with open(path, encoding="utf-8") as f:
        return yaml.load(f)


def _clear_caches():
    """Reset module-level caches between tests."""
    env_to_vault._classification_cache = None
    env_to_vault._client_cache.clear()


# ============================================================================
# TestLoadClassification — tests real load_classification (needs ruamel.yaml)
# ============================================================================


class TestLoadClassification(unittest.TestCase):
    def setUp(self):
        _clear_caches()

    def tearDown(self):
        _clear_caches()

    def test_load_valid_yaml(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data = env_to_vault.load_classification(path)
            self.assertEqual(data["metadata"]["project_code"], "lenie")
            self.assertIn("backends", data)
            self.assertIn("environments", data)
            self.assertIn("groups", data)
        finally:
            os.unlink(path)

    def test_caching(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data1 = env_to_vault.load_classification(path)
            data2 = env_to_vault.load_classification(path)
            self.assertIs(data1, data2)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        with self.assertRaises(SystemExit):
            env_to_vault.load_classification("/nonexistent/path.yaml")

    def test_malformed_yaml(self):
        path = _write_yaml("{ invalid yaml: [[[")
        try:
            with self.assertRaises(SystemExit):
                env_to_vault.load_classification(path)
        finally:
            os.unlink(path)

    def test_get_backends_for_env(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data = env_to_vault.load_classification(path)
            backends = env_to_vault.get_backends_for_env(data, "dev")
            self.assertEqual(len(backends), 2)
            names = [name for name, _ in backends]
            self.assertEqual(names, ["test-vault", "test-ssm"])
        finally:
            os.unlink(path)

    def test_unknown_environment(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data = env_to_vault.load_classification(path)
            with self.assertRaises(SystemExit):
                env_to_vault.get_backends_for_env(data, "staging")
        finally:
            os.unlink(path)

    def test_get_all_variables(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data = env_to_vault.load_classification(path)
            all_vars = env_to_vault.get_all_variables(data)
            self.assertIn("SECRETS_BACKEND", all_vars)
            self.assertIn("POSTGRESQL_HOST", all_vars)
            self.assertIn("OPENAI_API_KEY", all_vars)
            self.assertEqual(all_vars["SECRETS_BACKEND"]["group"], "bootstrap")
            self.assertEqual(all_vars["POSTGRESQL_HOST"]["group"], "database")
            self.assertGreaterEqual(len(all_vars), 9)
        finally:
            os.unlink(path)

    def test_get_bootstrap_variables(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            data = env_to_vault.load_classification(path)
            bootstrap = env_to_vault.get_bootstrap_variables(data)
            self.assertIn("SECRETS_BACKEND", bootstrap)
            self.assertIn("VAULT_ADDR", bootstrap)
            self.assertNotIn("POSTGRESQL_HOST", bootstrap)
        finally:
            os.unlink(path)

    def test_derived_ssm_type_secret(self):
        self.assertEqual(env_to_vault.get_derived_ssm_type({"type": "secret"}), "SecureString")

    def test_derived_ssm_type_config(self):
        self.assertEqual(env_to_vault.get_derived_ssm_type({"type": "config"}), "String")

    def test_derived_ssm_type_explicit_override(self):
        self.assertEqual(
            env_to_vault.get_derived_ssm_type({"type": "config", "ssm_type": "SecureString"}),
            "SecureString",
        )

    def test_unsupported_backend_type(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            env_to_vault.load_classification(path)
            with self.assertRaises(SystemExit):
                args = MagicMock()
                args.env_file = ".env"
                env_to_vault.resolve_backend_client({"type": "aws_secrets_manager"}, "bad-backend", args)
        finally:
            os.unlink(path)


# ============================================================================
# TestCompare
# ============================================================================


class TestCompare(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)
        # Create a real temp .env file so Path(env_file).exists() passes
        self.env_path = _write_env("DUMMY=1\n")

    def tearDown(self):
        _clear_caches()
        os.unlink(self.yaml_path)
        if os.path.exists(self.env_path):
            os.unlink(self.env_path)

    def _make_args(self, source="env", target="test-vault", env="dev", show_values=False):
        args = MagicMock()
        args.source = source
        args.target = target
        args.env = env
        args.show_values = show_values
        args.env_file = self.env_path
        args.region = None
        args.profile = None
        return args

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("env_to_vault.parse_env_file")
    def test_identical_sources(self, mock_parse, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        data = {"KEY1": "val1", "KEY2": "val2"}
        mock_parse.return_value = data
        mock_read.return_value = data
        mock_resolve.return_value = MagicMock()

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_compare(self._make_args())
        self.assertIn("identical", captured.getvalue())

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("env_to_vault.parse_env_file")
    def test_diff_output(self, mock_parse, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        mock_parse.return_value = {"KEY1": "val1", "KEY2": "changed", "KEY3": "new"}
        mock_read.return_value = {"KEY1": "val1", "KEY2": "original", "KEY4": "orphan"}
        mock_resolve.return_value = MagicMock()

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_compare(self._make_args())

        output = captured.getvalue()
        self.assertIn("KEY3", output)  # only in source
        self.assertIn("KEY4", output)  # only in target
        self.assertIn("KEY2", output)  # different
        self.assertIn("In sync: 1", output)

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("env_to_vault.parse_env_file")
    def test_show_values_flag(self, mock_parse, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        mock_parse.return_value = {"KEY1": "secretvalue123"}
        mock_read.return_value = {}
        mock_resolve.return_value = MagicMock()

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_compare(self._make_args(show_values=True))

        output = captured.getvalue()
        self.assertIn("WARNING: Showing unmasked values", output)
        self.assertIn("secretvalue123", output)

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("env_to_vault.parse_env_file")
    def test_masked_by_default(self, mock_parse, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        mock_parse.return_value = {"KEY1": "secretvalue123"}
        mock_read.return_value = {}
        mock_resolve.return_value = MagicMock()

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_compare(self._make_args(show_values=False))

        output = captured.getvalue()
        self.assertNotIn("secretvalue123", output)
        self.assertIn("sec***", output)

    @patch("env_to_vault.load_classification")
    def test_unknown_backend(self, mock_load):
        mock_load.return_value = self.yaml_data

        with self.assertRaises(SystemExit):
            env_to_vault.cmd_compare(self._make_args(source="nonexistent-backend"))


# ============================================================================
# TestGenerateEnvExample
# ============================================================================


class TestGenerateEnvExample(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)

    def tearDown(self):
        _clear_caches()
        os.unlink(self.yaml_path)

    def _make_args(self, backend_type="vault", output=None):
        args = MagicMock()
        args.backend_type = backend_type
        args.output = output
        return args

    @patch("env_to_vault.load_classification")
    def test_vault_backend_only_bootstrap(self, mock_load):
        mock_load.return_value = self.yaml_data

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_generate(self._make_args("vault"))

        output = captured.getvalue()
        self.assertIn("SECRETS_BACKEND", output)
        self.assertIn("VAULT_ADDR", output)
        self.assertNotIn("POSTGRESQL_HOST", output)
        self.assertNotIn("OPENAI_API_KEY", output)

    @patch("env_to_vault.load_classification")
    def test_aws_backend_no_vault_vars(self, mock_load):
        mock_load.return_value = self.yaml_data

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_generate(self._make_args("aws"))

        output = captured.getvalue()
        self.assertIn("SECRETS_BACKEND", output)
        self.assertNotIn("VAULT_ADDR", output)
        self.assertNotIn("VAULT_TOKEN", output)
        self.assertNotIn("VAULT_ENV", output)

    @patch("env_to_vault.load_classification")
    def test_env_backend_all_variables(self, mock_load):
        mock_load.return_value = self.yaml_data

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_generate(self._make_args("env"))

        output = captured.getvalue()
        self.assertIn("SECRETS_BACKEND", output)
        self.assertIn("POSTGRESQL_HOST", output)
        self.assertIn("OPENAI_API_KEY", output)
        self.assertIn("LLM_PROVIDER", output)

    @patch("env_to_vault.load_classification")
    def test_example_value_precedence(self, mock_load):
        mock_load.return_value = self.yaml_data

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_generate(self._make_args("vault"))

        output = captured.getvalue()
        self.assertIn('SECRETS_BACKEND="env"', output)
        self.assertIn('SECRETS_ENV="dev"', output)


# ============================================================================
# TestValidateEnvFile
# ============================================================================


class TestValidateEnvFile(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)

    def tearDown(self):
        _clear_caches()
        os.unlink(self.yaml_path)

    def _make_args(self, backend_type="vault", env_content=""):
        env_path = _write_env(env_content)
        args = MagicMock()
        args.backend_type = backend_type
        args.env_file = env_path
        return args, env_path

    @patch("env_to_vault.load_classification")
    def test_clean_vault_env(self, mock_load):
        mock_load.return_value = self.yaml_data

        env_content = "SECRETS_BACKEND=vault\nSECRETS_ENV=dev\nVAULT_ADDR=http://v:8200\nVAULT_TOKEN=tok\nVAULT_ENV=dev\n"
        args, env_path = self._make_args("vault", env_content)
        try:
            with self.assertRaises(SystemExit) as cm:
                env_to_vault.cmd_validate(args)
            self.assertEqual(cm.exception.code, 0)
        finally:
            os.unlink(env_path)

    @patch("env_to_vault.load_classification")
    def test_missing_bootstrap_vars(self, mock_load):
        mock_load.return_value = self.yaml_data

        env_content = "SECRETS_BACKEND=vault\n"
        args, env_path = self._make_args("vault", env_content)
        try:
            captured = StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    env_to_vault.cmd_validate(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Missing", captured.getvalue())
        finally:
            os.unlink(env_path)

    @patch("env_to_vault.load_classification")
    def test_excess_variables_detected(self, mock_load):
        mock_load.return_value = self.yaml_data

        env_content = "SECRETS_BACKEND=vault\nSECRETS_ENV=dev\nVAULT_ADDR=x\nVAULT_TOKEN=x\nVAULT_ENV=x\nPOSTGRESQL_HOST=db\nOPENAI_API_KEY=sk-123\n"
        args, env_path = self._make_args("vault", env_content)
        try:
            captured = StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    env_to_vault.cmd_validate(args)
            self.assertEqual(cm.exception.code, 1)
            output = captured.getvalue()
            self.assertIn("Non-bootstrap", output)
            self.assertIn("POSTGRESQL_HOST", output)
            self.assertIn("OPENAI_API_KEY", output)
        finally:
            os.unlink(env_path)

    @patch("env_to_vault.load_classification")
    def test_unknown_variables_detected(self, mock_load):
        mock_load.return_value = self.yaml_data

        env_content = "SECRETS_BACKEND=vault\nSECRETS_ENV=dev\nVAULT_ADDR=x\nVAULT_TOKEN=x\nVAULT_ENV=x\nUNKNOWN_VAR=something\n"
        args, env_path = self._make_args("vault", env_content)
        try:
            captured = StringIO()
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as cm:
                    env_to_vault.cmd_validate(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Unknown", captured.getvalue())
            self.assertIn("UNKNOWN_VAR", captured.getvalue())
        finally:
            os.unlink(env_path)


# ============================================================================
# TestRemove
# ============================================================================


class TestRemove(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)

    def tearDown(self):
        _clear_caches()
        if os.path.exists(self.yaml_path):
            os.unlink(self.yaml_path)

    def _make_args(self, keys, env="dev", write=False):
        args = MagicMock()
        args.keys = keys
        args.env = env
        args.write = write
        args.env_file = ".env"
        args.region = None
        args.profile = None
        return args

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    def test_dry_run_no_changes(self, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"POSTGRESQL_HOST": "localhost"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_remove(self._make_args(["POSTGRESQL_HOST"]))

        output = captured.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("POSTGRESQL_HOST", output)

    @patch("env_to_vault.save_classification")
    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.vault_read_all")
    @patch("env_to_vault.ssm_delete_parameter")
    def test_write_removes_from_backends(self, mock_ssm_del, mock_vault_read, mock_resolve, mock_load, mock_save):
        mock_load.return_value = self.yaml_data

        vault_client = MagicMock()
        ssm_client = MagicMock()

        def side_resolve(bdef, bname, args):
            if bdef.get("type") == "vault_kv2":
                return vault_client
            return ssm_client

        mock_resolve.side_effect = side_resolve
        mock_vault_read.return_value = {"POSTGRESQL_HOST": "localhost", "OTHER": "val"}

        args = self._make_args(["POSTGRESQL_HOST"], write=True)
        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_remove(args)

        # Vault: read-modify-write
        vault_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
        call_kwargs = vault_client.secrets.kv.v2.create_or_update_secret.call_args
        secret_data = call_kwargs[1].get("secret", call_kwargs.kwargs.get("secret"))
        self.assertNotIn("POSTGRESQL_HOST", secret_data)

        # SSM: direct delete
        mock_ssm_del.assert_called_once()

        # YAML: save called
        mock_save.assert_called_once()

    @patch("env_to_vault.save_classification")
    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.vault_read_all")
    @patch("env_to_vault.ssm_delete_parameter")
    def test_key_not_found_graceful(self, mock_ssm_del, mock_vault_read, mock_resolve, mock_load, mock_save):
        mock_load.return_value = self.yaml_data

        mock_resolve.return_value = MagicMock()
        mock_vault_read.return_value = {}  # Key not in Vault
        mock_ssm_del.side_effect = Exception("ParameterNotFound")

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_remove(self._make_args(["NONEXISTENT_KEY"], write=True))

        output = captured.getvalue()
        self.assertIn("not found", output)
        mock_save.assert_called_once()

    @patch("env_to_vault.load_classification")
    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    def test_key_not_in_yaml(self, mock_read, mock_resolve, mock_load):
        mock_load.return_value = self.yaml_data

        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"UNKNOWN_VAR": "val"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_remove(self._make_args(["UNKNOWN_VAR"]))

        output = captured.getvalue()
        self.assertIn("vars-classification.yaml: not found", output)

    def test_yaml_roundtrip_preserves_comments(self):
        from ruamel.yaml import YAML
        yaml = YAML(typ="rt")
        with open(self.yaml_path, encoding="utf-8") as f:
            data = yaml.load(f)

        # Modify: remove a variable
        del data["groups"]["database"]["variables"]["POSTGRESQL_HOST"]

        # Save using our function
        env_to_vault.save_classification(data, self.yaml_path)

        # Read back raw text
        content = Path(self.yaml_path).read_text(encoding="utf-8")
        self.assertIn("Test comment", content)
        self.assertNotIn("POSTGRESQL_HOST", content)
        self.assertIn("POSTGRESQL_PASSWORD", content)


# ============================================================================
# TestReviewDisplay
# ============================================================================


class TestReviewDisplay(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)

    def tearDown(self):
        _clear_caches()
        os.unlink(self.yaml_path)

    def _make_args(self, env="dev"):
        args = MagicMock()
        args.env = env
        args.env_file = ".env"
        args.region = None
        args.profile = None
        return args

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    def test_build_review_data_structure(self, mock_read, mock_resolve):
        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"SECRETS_BACKEND": "env", "POSTGRESQL_HOST": "db", "ORPHAN_KEY": "val"}

        review = env_to_vault.build_review_data(self.yaml_data, "dev", self._make_args())

        self.assertIn("var_status", review)
        self.assertIn("orphans", review)
        self.assertIn("backends", review)
        self.assertIn("SECRETS_BACKEND", review["var_status"])
        self.assertIn("ORPHAN_KEY", review["orphans"])

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    def test_display_review_output(self, mock_read, mock_resolve):
        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"SECRETS_BACKEND": "env", "POSTGRESQL_HOST": "db"}

        review = env_to_vault.build_review_data(self.yaml_data, "dev", self._make_args())

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.display_review(review)

        output = captured.getvalue()
        self.assertIn("GROUP: bootstrap", output)
        self.assertIn("GROUP: database", output)
        self.assertIn("Summary:", output)

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    def test_unavailable_backend(self, mock_read, mock_resolve):
        call_count = [0]

        def side_resolve(bdef, bname, args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Vault sealed")
            return MagicMock()

        mock_resolve.side_effect = side_resolve
        mock_read.return_value = {"SECRETS_BACKEND": "env"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            review = env_to_vault.build_review_data(self.yaml_data, "dev", self._make_args())

        output = captured.getvalue()
        self.assertIn("unavailable", output.lower())
        self.assertIn("test-vault", review["unavailable"])


# ============================================================================
# TestReviewInteractive
# ============================================================================


class TestReviewInteractive(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.yaml_path = _write_yaml(MINIMAL_YAML)
        self.yaml_data = _load_yaml_directly(self.yaml_path)

    def tearDown(self):
        _clear_caches()
        if os.path.exists(self.yaml_path):
            os.unlink(self.yaml_path)

    def _make_args(self, env="dev"):
        args = MagicMock()
        args.env = env
        args.env_file = ".env"
        args.region = None
        args.profile = None
        return args

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("builtins.input", side_effect=["q"])
    @patch("env_to_vault.load_classification")
    def test_quit_action(self, mock_load, mock_input, mock_read, mock_resolve):
        mock_load.return_value = self.yaml_data
        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"SECRETS_BACKEND": "env"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_review(self._make_args())

        output = captured.getvalue()
        self.assertIn("review", output.lower())

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("builtins.input", side_effect=["d", "POSTGRESQL_HOST", "n", "q"])
    @patch("env_to_vault.load_classification")
    def test_delete_cancelled(self, mock_load, mock_input, mock_read, mock_resolve):
        mock_load.return_value = self.yaml_data
        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"SECRETS_BACKEND": "env"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_review(self._make_args())

        self.assertIn("Cancelled", captured.getvalue())

    @patch("env_to_vault.resolve_backend_client")
    @patch("env_to_vault.read_backend_data")
    @patch("env_to_vault.save_classification")
    @patch("builtins.input", side_effect=["a", "ORPHAN_KEY", "database", "config", "An orphan var", "q"])
    @patch("env_to_vault.load_classification")
    def test_add_orphan(self, mock_load, mock_input, mock_save, mock_read, mock_resolve):
        mock_load.return_value = self.yaml_data
        mock_resolve.return_value = MagicMock()
        mock_read.return_value = {"SECRETS_BACKEND": "env", "ORPHAN_KEY": "val"}

        captured = StringIO()
        with patch("sys.stdout", captured):
            env_to_vault.cmd_review(self._make_args())

        output = captured.getvalue()
        self.assertIn("Added", output)
        mock_save.assert_called()


if __name__ == "__main__":
    unittest.main()
