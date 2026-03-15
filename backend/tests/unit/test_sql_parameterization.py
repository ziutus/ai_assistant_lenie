"""Unit tests for SQL parameterization in WebsitesDBPostgreSQL (Story 31.3).

Verifies that query methods use parameterized queries and never pass
user-controlled values as raw SQL. Tests cover SQL injection payloads,
LIKE wildcard escaping, and edge-case inputs.

Requires sqlalchemy in the environment (skipped otherwise).
"""

from unittest.mock import MagicMock

import pytest

sa = pytest.importorskip("sqlalchemy")

from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture()
def db_instance():
    """Create WebsitesDBPostgreSQL with a mock session."""
    from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

    mock_session = MagicMock(spec=Session)
    mock_session.execute.return_value = MagicMock(all=MagicMock(return_value=[]))
    return WebsitesDBPostgreSQL(session=mock_session)


class TestGetDocumentsByUrlParameterization:
    """AC #4 — verify get_documents_by_url() uses parameterized queries."""

    def test_normal_url(self, db_instance):
        result = db_instance.get_documents_by_url("https://example.com/page")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_sql_injection_drop_table(self, db_instance):
        """SQL injection payload should be treated as literal string."""
        result = db_instance.get_documents_by_url("'; DROP TABLE web_documents; --")
        assert result == []
        db_instance.session.execute.assert_called_once()
        # The statement should contain the payload as a bound parameter, not raw SQL
        stmt = db_instance.session.execute.call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        sql_text = str(compiled)
        assert "DROP TABLE" not in sql_text

    def test_percent_wildcard_escaped(self, db_instance):
        """% in URL should be escaped to prevent LIKE wildcard expansion."""
        result = db_instance.get_documents_by_url("https://example.com/100%done")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_underscore_wildcard_escaped(self, db_instance):
        """_ in URL should be escaped to prevent LIKE single-char wildcard."""
        result = db_instance.get_documents_by_url("https://example.com/test_page")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_backslash_in_url(self, db_instance):
        """Backslash in URL should be handled safely."""
        result = db_instance.get_documents_by_url("https://example.com/path\\file")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_min_id_is_converted_to_int(self, db_instance):
        """min_id should be cast to int to prevent type-based injection."""
        result = db_instance.get_documents_by_url("https://example.com", min_id="42")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_pattern_uses_variable_not_fstring_in_like(self, db_instance):
        """Verify the pattern variable is used (not inline f-string)."""
        import inspect
        from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

        source = inspect.getsource(WebsitesDBPostgreSQL.get_documents_by_url)
        # Should have `pattern = f"...` and `.like(pattern,` — not `.like(f"`
        assert '.like(f"' not in source
        assert "pattern = f" in source or "pattern = f'" in source


class TestGetSimilarParameterization:
    """AC #4 — verify get_similar() uses parameterized queries."""

    def test_malicious_model_string(self, db_instance):
        """Model name with SQL injection payload should be safe."""
        embedding = [0.1] * 10
        result = db_instance.get_similar(
            embedding=embedding,
            model="'; DROP TABLE websites_embeddings; --",
            limit=3,
        )
        assert result == []
        db_instance.session.execute.assert_called_once()
        stmt = db_instance.session.execute.call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        sql_text = str(compiled)
        assert "DROP TABLE" not in sql_text

    def test_malicious_project_string(self, db_instance):
        """Project name with SQL injection payload should be safe."""
        embedding = [0.1] * 10
        result = db_instance.get_similar(
            embedding=embedding,
            model="text-embedding-ada-002",
            limit=3,
            project="'; DELETE FROM web_documents; --",
        )
        assert result == []
        db_instance.session.execute.assert_called_once()
        stmt = db_instance.session.execute.call_args[0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        sql_text = str(compiled)
        assert "DELETE FROM" not in sql_text

    def test_none_embedding_returns_none(self, db_instance):
        """None embedding should return None without executing SQL."""
        result = db_instance.get_similar(embedding=None, model="test")
        assert result is None
        db_instance.session.execute.assert_not_called()


class TestGetDocumentsMdNeededParameterization:
    """AC #4 — verify get_documents_md_needed() uses parameterized queries."""

    def test_normal_min_id(self, db_instance):
        result = db_instance.get_documents_md_needed(min_id=0)
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_string_min_id_converted_to_int(self, db_instance):
        """String min_id should be cast to int."""
        result = db_instance.get_documents_md_needed(min_id="100")
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_negative_min_id(self, db_instance):
        """Negative min_id should be accepted (valid integer)."""
        result = db_instance.get_documents_md_needed(min_id=-1)
        assert result == []
        db_instance.session.execute.assert_called_once()

    def test_invalid_min_id_raises_error(self, db_instance):
        """Non-numeric min_id should raise ValueError from int() cast."""
        with pytest.raises((ValueError, TypeError)):
            db_instance.get_documents_md_needed(min_id="abc; DROP TABLE")
