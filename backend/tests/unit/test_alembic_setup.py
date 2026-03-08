"""Unit tests for Alembic configuration and Flask session teardown (Story 26.3)."""

import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Tests: Alembic directory structure and configuration
# ---------------------------------------------------------------------------


class TestAlembicFiles:
    """Verify that Alembic configuration files exist in expected locations."""

    def test_alembic_ini_exists(self):
        ini_path = os.path.join(BACKEND_DIR, "alembic.ini")
        assert os.path.isfile(ini_path), "alembic.ini must exist in backend/"

    def test_alembic_env_py_exists(self):
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        assert os.path.isfile(env_path), "alembic/env.py must exist"

    def test_alembic_versions_dir_exists(self):
        versions_path = os.path.join(BACKEND_DIR, "alembic", "versions")
        assert os.path.isdir(versions_path), "alembic/versions/ directory must exist"

    def test_alembic_script_mako_exists(self):
        mako_path = os.path.join(BACKEND_DIR, "alembic", "script.py.mako")
        assert os.path.isfile(mako_path), "alembic/script.py.mako must exist"


class TestAlembicIniConfig:
    """Verify alembic.ini has correct configuration."""

    def test_no_hardcoded_sqlalchemy_url(self):
        ini_path = os.path.join(BACKEND_DIR, "alembic.ini")
        with open(ini_path) as f:
            content = f.read()
        # There should be no uncommented sqlalchemy.url = ...
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("sqlalchemy.url") and "=" in stripped and not stripped.startswith("#"):
                pytest.fail(f"alembic.ini must NOT have hardcoded sqlalchemy.url, found: {stripped}")

    def test_script_location_is_alembic(self):
        ini_path = os.path.join(BACKEND_DIR, "alembic.ini")
        with open(ini_path) as f:
            content = f.read()
        assert "script_location" in content


# ---------------------------------------------------------------------------
# Tests: env.py metadata configuration
# ---------------------------------------------------------------------------


ENV_VARS = {
    "POSTGRESQL_HOST": "localhost",
    "POSTGRESQL_PORT": "5432",
    "POSTGRESQL_DATABASE": "testdb",
    "POSTGRESQL_USER": "testuser",
    "POSTGRESQL_PASSWORD": "testpass",
}


@pytest.fixture(autouse=True)
def _reset_engine():
    """Reset engine singletons between tests."""
    from library.db.engine import dispose_engine
    dispose_engine()
    yield
    dispose_engine()


class TestAlembicEnvMetadata:
    """Verify that env.py correctly configures target_metadata.

    Note: Tests prefixed with test_env_* are smoke checks that verify env.py
    source text contains required configuration. They cannot import env.py
    directly because it executes module-level Alembic context calls.
    Behavioral tests for include_object are in TestIncludeObjectFilter.
    """

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_target_metadata_is_base_metadata(self):
        env_module_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_module_path) as f:
            content = f.read()
        assert "target_metadata = Base.metadata" in content, \
            "env.py must set target_metadata = Base.metadata"

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_env_imports_models(self):
        """env.py must import library.db.models to register on Base.metadata."""
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "import library.db.models" in content, \
            "env.py must import library.db.models to register models on Base.metadata"

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_env_imports_get_engine(self):
        """env.py must import get_engine from library.db.engine."""
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "from library.db.engine import get_engine" in content

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_env_has_compare_type(self):
        """env.py must use compare_type=True in context.configure()."""
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "compare_type=True" in content

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_env_has_include_object_filter(self):
        """env.py must have include_object filter to exclude indexes."""
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()
        assert "include_object" in content

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_base_metadata_has_web_documents_table(self):
        """Base.metadata should have web_documents table after models are imported."""
        import library.db.models  # noqa: F401
        from library.db.engine import Base

        assert "web_documents" in Base.metadata.tables, \
            "Base.metadata must contain web_documents table"

    @patch.dict("os.environ", ENV_VARS, clear=False)
    def test_base_metadata_has_websites_embeddings_table(self):
        """Base.metadata should have websites_embeddings table after models are imported."""
        import library.db.models  # noqa: F401
        from library.db.engine import Base

        assert "websites_embeddings" in Base.metadata.tables, \
            "Base.metadata must contain websites_embeddings table"


# ---------------------------------------------------------------------------
# Tests: include_object filter behavior
# ---------------------------------------------------------------------------


class TestIncludeObjectFilter:
    """Behavioral tests for the include_object filter in env.py.

    Since env.py cannot be imported directly (module-level Alembic context
    calls), we extract the function source and exec it in an isolated namespace.
    """

    @staticmethod
    def _load_include_object():
        """Load include_object from env.py without executing module-level code."""
        env_path = os.path.join(BACKEND_DIR, "alembic", "env.py")
        with open(env_path) as f:
            source = f.read()
        match = re.search(
            r"(def include_object\(.*?\n(?:[ \t]+.*\n|\n)*)",
            source,
        )
        assert match, "include_object function not found in env.py"
        ns = {}
        exec(match.group(1), ns)
        return ns["include_object"]

    def test_excludes_indexes(self):
        fn = self._load_include_object()
        assert fn(MagicMock(), "ix_web_documents_url", "index", True, None) is False

    def test_excludes_document_state_error_in_web_documents(self):
        fn = self._load_include_object()
        col = MagicMock()
        col.table.name = "web_documents"
        assert fn(col, "document_state_error", "column", True, None) is False

    def test_includes_document_state_error_in_other_table(self):
        fn = self._load_include_object()
        col = MagicMock()
        col.table.name = "other_table"
        assert fn(col, "document_state_error", "column", True, None) is True

    def test_includes_regular_columns(self):
        fn = self._load_include_object()
        col = MagicMock()
        col.table.name = "web_documents"
        assert fn(col, "title", "column", True, None) is True

    def test_includes_tables(self):
        fn = self._load_include_object()
        assert fn(MagicMock(), "web_documents", "table", True, None) is True


# ---------------------------------------------------------------------------
# Tests: Flask teardown handler
# ---------------------------------------------------------------------------


class TestFlaskTeardown:
    """Verify Flask session teardown is correctly configured."""

    @patch.dict("os.environ", {
        **ENV_VARS,
        "ENV_DATA": "2026.01.01",
        "LLM_PROVIDER": "openai",
        "OPENAI_ORGANIZATION": "test-org",
        "OPENAI_API_KEY": "test-key",
        "AI_MODEL_SUMMARY": "gpt-4o-mini",
        "BACKEND_TYPE": "postgresql",
        "EMBEDDING_MODEL": "text-embedding-ada-002",
        "PORT": "5000",
        "STALKER_API_KEY": "test-api-key",
        "SECRETS_BACKEND": "env",
    })
    @patch("library.stalker_web_documents_db_postgresql.WebsitesDBPostgreSQL")
    def test_teardown_handler_registered(self, mock_db_class):
        """Flask app must have a teardown_appcontext handler."""
        mock_db = MagicMock()
        mock_db.get_count.return_value = 0
        mock_db_class.return_value = mock_db

        # Force reload of server module to register handlers with mocked DB
        if "server" in sys.modules:
            del sys.modules["server"]

        import server  # noqa: F811

        # Flask stores teardown functions in teardown_appcontext_funcs
        teardown_funcs = server.app.teardown_appcontext_funcs
        if isinstance(teardown_funcs, dict):
            teardown_funcs = teardown_funcs.get(None, [])
        func_names = [f.__name__ for f in teardown_funcs]
        assert "shutdown_session" in func_names, \
            "shutdown_session must be registered as teardown_appcontext handler"

    @patch.dict("os.environ", {
        **ENV_VARS,
        "ENV_DATA": "2026.01.01",
        "LLM_PROVIDER": "openai",
        "OPENAI_ORGANIZATION": "test-org",
        "OPENAI_API_KEY": "test-key",
        "AI_MODEL_SUMMARY": "gpt-4o-mini",
        "BACKEND_TYPE": "postgresql",
        "EMBEDDING_MODEL": "text-embedding-ada-002",
        "PORT": "5000",
        "STALKER_API_KEY": "test-api-key",
        "SECRETS_BACKEND": "env",
    })
    @patch("library.stalker_web_documents_db_postgresql.WebsitesDBPostgreSQL")
    def test_teardown_calls_scoped_session_remove(self, mock_db_class):
        """Teardown handler must call get_scoped_session().remove()."""
        mock_db = MagicMock()
        mock_db.get_count.return_value = 0
        mock_db_class.return_value = mock_db

        if "server" in sys.modules:
            del sys.modules["server"]

        import server  # noqa: F811

        with patch("library.db.engine.get_scoped_session") as mock_get_scoped:
            mock_session = MagicMock()
            mock_get_scoped.return_value = mock_session

            # Simulate teardown by calling the handler directly
            teardown_funcs = server.app.teardown_appcontext_funcs
            if isinstance(teardown_funcs, dict):
                teardown_funcs = teardown_funcs.get(None, [])
            shutdown_func = None
            for f in teardown_funcs:
                if f.__name__ == "shutdown_session":
                    shutdown_func = f
                    break

            assert shutdown_func is not None, "shutdown_session handler not found"
            shutdown_func(None)

            mock_get_scoped.assert_called_once()
            mock_session.remove.assert_called_once()
