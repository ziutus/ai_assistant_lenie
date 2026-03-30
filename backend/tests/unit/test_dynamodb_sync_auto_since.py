"""Unit tests for dynamodb_sync.py auto-detection of --since from import_logs."""

import datetime
import sys
from unittest.mock import MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")


# ---------------------------------------------------------------------------
# We need to mock heavy dependencies (boto3) before importing the module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_boto3(monkeypatch):
    """Prevent boto3 import from failing in test environment."""
    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())
    monkeypatch.setitem(sys.modules, "botocore", MagicMock())
    monkeypatch.setitem(sys.modules, "botocore.exceptions", MagicMock())


@pytest.fixture()
def _mock_config(monkeypatch):
    """Mock config_loader to avoid .env dependency."""
    mock_cfg = MagicMock()
    mock_cfg.get.return_value = "tmp"
    mock_cfg.require.return_value = "us-east-1"
    mock_loader = MagicMock(return_value=mock_cfg)
    monkeypatch.setitem(sys.modules, "library.config_loader", MagicMock(load_config=mock_loader))


def _import_module():
    """Import dynamodb_sync with heavy deps already mocked."""
    import importlib
    if "imports.dynamodb_sync" in sys.modules:
        return importlib.reload(sys.modules["imports.dynamodb_sync"])
    return importlib.import_module("imports.dynamodb_sync")


# ---------------------------------------------------------------------------
# get_last_successful_sync_date tests
# ---------------------------------------------------------------------------


class TestGetLastSuccessfulSyncDate:
    """Tests for get_last_successful_sync_date()."""

    def test_returns_date_when_successful_run_exists(self):
        """6.1 — returns date when successful run exists."""
        mod = _import_module()

        session = MagicMock()
        expected_date = datetime.date(2026, 3, 25)
        session.scalar.return_value = expected_date

        result = mod.get_last_successful_sync_date(session)

        assert result == expected_date
        session.scalar.assert_called_once()

    def test_returns_none_when_no_runs_exist(self):
        """6.2 — returns None when no runs exist."""
        mod = _import_module()

        session = MagicMock()
        session.scalar.return_value = None

        result = mod.get_last_successful_sync_date(session)

        assert result is None

    def test_ignores_failed_runs(self):
        """6.3 — the query filters by status='success', so failed runs are ignored.

        Verify the SQL query contains WHERE clauses for script_name and status='success'.
        """
        mod = _import_module()

        session = MagicMock()
        session.scalar.return_value = None

        mod.get_last_successful_sync_date(session)

        session.scalar.assert_called_once()
        # Extract the compiled query and verify it filters by status='success'
        query = session.scalar.call_args[0][0]
        query_str = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "status" in query_str, "Query must filter by status"
        assert "'success'" in query_str, "Query must filter by status='success'"
        assert "dynamodb_sync" in query_str, "Query must filter by script_name='dynamodb_sync'"


# ---------------------------------------------------------------------------
# main() auto-detection integration tests
# ---------------------------------------------------------------------------


class TestMainAutoDetection:
    """Tests for --since auto-detection integration in main()."""

    def test_auto_detect_when_since_omitted_and_previous_run_exists(self, capsys):
        """6.4 — --since omitted, previous run exists: auto-detects date."""
        mod = _import_module()

        mock_session = MagicMock()
        mock_session.scalar.return_value = datetime.date(2026, 3, 25)

        test_args = ["dynamodb_sync.py", "--dry-run", "-y"]
        with patch.object(sys, "argv", test_args), \
             patch.object(mod, "get_session", return_value=mock_session), \
             patch.object(mod, "cfg") as mock_cfg, \
             patch.object(mod, "resolve_resource_names", return_value=("test-table", None)), \
             patch.object(mod, "get_dynamodb_items", return_value=[]):
            mock_cfg.get.return_value = "tmp"
            mock_cfg.require.return_value = "us-east-1"

            mod.main()

        captured = capsys.readouterr()
        assert "Auto-detected --since 2026-03-25 from last successful sync" in captured.out

    def test_error_when_since_omitted_and_no_previous_run(self, capsys):
        """6.5 — --since omitted, no previous run: prints error and exits."""
        mod = _import_module()

        mock_session = MagicMock()
        mock_session.scalar.return_value = None

        test_args = ["dynamodb_sync.py", "--dry-run", "-y"]
        with patch.object(sys, "argv", test_args), \
             patch.object(mod, "get_session", return_value=mock_session), \
             patch.object(mod, "cfg") as mock_cfg, \
             pytest.raises(SystemExit) as exc_info:
            mock_cfg.get.return_value = "tmp"
            mod.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No previous sync found" in captured.out

    def test_explicit_since_overrides_auto_detection(self, capsys):
        """6.6 — explicit --since shows override message."""
        mod = _import_module()

        mock_session = MagicMock()
        mock_session.scalar.return_value = datetime.date(2026, 3, 25)

        test_args = ["dynamodb_sync.py", "--since", "2026-03-20", "--dry-run", "-y"]
        with patch.object(sys, "argv", test_args), \
             patch.object(mod, "get_session", return_value=mock_session), \
             patch.object(mod, "cfg") as mock_cfg, \
             patch.object(mod, "resolve_resource_names", return_value=("test-table", None)), \
             patch.object(mod, "get_dynamodb_items", return_value=[]):
            mock_cfg.get.return_value = "tmp"
            mock_cfg.require.return_value = "us-east-1"

            mod.main()

        captured = capsys.readouterr()
        assert "Using explicit --since 2026-03-20 (overriding auto-detected 2026-03-25)" in captured.out

    def test_explicit_since_no_previous_run(self, capsys):
        """Explicit --since with no previous run shows simple message."""
        mod = _import_module()

        mock_session = MagicMock()
        mock_session.scalar.return_value = None

        test_args = ["dynamodb_sync.py", "--since", "2026-03-20", "--dry-run", "-y"]
        with patch.object(sys, "argv", test_args), \
             patch.object(mod, "get_session", return_value=mock_session), \
             patch.object(mod, "cfg") as mock_cfg, \
             patch.object(mod, "resolve_resource_names", return_value=("test-table", None)), \
             patch.object(mod, "get_dynamodb_items", return_value=[]):
            mock_cfg.get.return_value = "tmp"
            mock_cfg.require.return_value = "us-east-1"

            mod.main()

        captured = capsys.readouterr()
        assert "Using explicit --since 2026-03-20" in captured.out
        assert "overriding" not in captured.out
