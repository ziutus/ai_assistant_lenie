"""Unit tests for mcp_server.tools.lenie — lenie_unreviewed_articles and lenie_get_article tools."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")
pytest.importorskip("sqlalchemy")

from sqlalchemy.exc import OperationalError

from mcp import McpError
from mcp_server.errors import McpErrorCode
from mcp_server.tools.lenie import register_lenie_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CaptureMcp:
    """Minimal FastMCP stand-in that captures functions registered via @mcp.tool()."""

    def __init__(self):
        self._tools: dict = {}

    def tool(self):
        def decorator(func):
            self._tools[func.__name__] = func
            return func
        return decorator

    def get(self, name):
        return self._tools[name]


def _get_tool():
    """Register tools against a capture-mcp and return the lenie_unreviewed_articles function."""
    cap = _CaptureMcp()
    register_lenie_tools(cap)
    return cap.get("lenie_unreviewed_articles")


def _make_doc(
    id: int = 1,
    title: str = "Test article",
    url: str = "https://example.com/article",
    text: str = "x" * 2048,
    note: str | None = None,
    created_at: datetime.datetime | None = None,
    document_type: str = "webpage",
) -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.title = title
    doc.url = url
    doc.text = text
    doc.note = note
    doc.created_at = created_at or datetime.datetime(2026, 1, 15, 12, 0, 0)
    doc.document_type = document_type
    return doc


def _mock_session(docs: list, total: int):
    """Return a mock session whose execute() returns given docs for scalars and total for scalar."""
    session = MagicMock()

    count_result = MagicMock()
    count_result.scalar.return_value = total

    docs_result = MagicMock()
    docs_result.scalars.return_value.all.return_value = docs

    # First execute call → count, second → docs
    session.execute.side_effect = [count_result, docs_result]
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLenieUnreviewedArticles:

    def test_default_invocation_returns_correct_keys(self):
        """Default call returns articles list with all required keys (AC-2)."""
        doc = _make_doc(id=42, title="Hello", url="https://bbc.com/news", text="a" * 1024, note="my note")
        session = _mock_session([doc], total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool()

        assert "articles" in result
        assert "total_unreviewed" in result
        assert result["total_unreviewed"] == 1
        assert len(result["articles"]) == 1

        article = result["articles"][0]
        assert article["id"] == 42
        assert article["title"] == "Hello"
        assert article["source"] == "https://bbc.com/news"
        assert article["size_kb"] == 1  # 1024 bytes → 1 KB
        assert article["user_note"] == "my note"
        assert article["added_at"] == "2026-01-15T12:00:00"
        assert article["total_unreviewed"] == 1

    def test_default_limit_is_six(self):
        """Default invocation uses limit=6 — at most 6 articles returned (AC-2)."""
        docs = [_make_doc(id=i) for i in range(6)]
        session = _mock_session(docs, total=10)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool()

        assert len(result["articles"]) == 6

    def test_limit_parameter_respected(self):
        """limit=3 returns at most 3 articles (AC-3)."""
        docs = [_make_doc(id=i) for i in range(3)]
        session = _mock_session(docs, total=20)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(limit=3)

        assert len(result["articles"]) == 3

    def test_offset_parameter_applied_to_docs_statement(self):
        """offset=6 is applied via SQL OFFSET to the docs query (AC-6)."""
        docs = [_make_doc(id=7)]
        session = _mock_session(docs, total=10)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(offset=6)

        assert len(result["articles"]) == 1
        # Verify OFFSET clause is present in the docs statement (second execute call)
        docs_stmt_str = str(session.execute.call_args_list[1][0][0]).lower()
        assert "offset" in docs_stmt_str, "Expected OFFSET clause in docs statement"
        # COUNT query must NOT have OFFSET (would distort total_unreviewed)
        count_stmt_str = str(session.execute.call_args_list[0][0][0]).lower()
        assert "offset" not in count_stmt_str, "COUNT query must not include OFFSET"

    def test_source_filter_applies_ilike_to_statement(self):
        """source_filter adds ILIKE WHERE clause to both count and docs SQL statements (AC-4)."""
        docs = [_make_doc(url="https://bbc.com/article")]
        session = _mock_session(docs, total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(source_filter="bbc.com")

        assert len(result["articles"]) == 1
        assert "bbc.com" in result["articles"][0]["source"]
        # Verify ILIKE filter is present in the actual SQL statements passed to execute()
        count_stmt_str = str(session.execute.call_args_list[0][0][0]).lower()
        docs_stmt_str = str(session.execute.call_args_list[1][0][0]).lower()
        assert "ilike" in count_stmt_str or "like" in count_stmt_str, (
            "Expected ILIKE/LIKE filter in count statement"
        )
        assert "ilike" in docs_stmt_str or "like" in docs_stmt_str, (
            "Expected ILIKE/LIKE filter in docs statement"
        )

    def test_type_filter_applies_equality_to_statement(self):
        """type_filter adds document_type equality WHERE clause to both statements (AC-5)."""
        docs = [_make_doc(document_type="youtube")]
        session = _mock_session(docs, total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(type_filter="youtube")

        assert len(result["articles"]) == 1
        # Verify document_type filter is present in the actual SQL statements
        count_stmt_str = str(session.execute.call_args_list[0][0][0]).lower()
        docs_stmt_str = str(session.execute.call_args_list[1][0][0]).lower()
        assert "document_type" in count_stmt_str, (
            "Expected document_type filter in count statement"
        )
        assert "document_type" in docs_stmt_str, (
            "Expected document_type filter in docs statement"
        )

    def test_operational_error_raises_mcp_error(self):
        """OperationalError from DB raises McpError with DATABASE_UNAVAILABLE code (AC-7)."""
        session = MagicMock()
        session.execute.side_effect = OperationalError("connection refused", None, None)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            with pytest.raises(McpError) as exc_info:
                tool()

        assert exc_info.value.error.code == McpErrorCode.DATABASE_UNAVAILABLE

    def test_empty_result_returns_empty_list_with_zero_total(self):
        """No unreviewed articles → empty list and total_unreviewed=0 (AC-8)."""
        session = _mock_session([], total=0)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool()

        assert result["articles"] == []
        assert result["total_unreviewed"] == 0

    def test_session_closed_on_success(self):
        """Session.close() is always called after successful execution."""
        docs = [_make_doc()]
        session = _mock_session(docs, total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            tool()

        session.close.assert_called_once()

    def test_session_closed_on_error(self):
        """Session.close() is called even when OperationalError is raised."""
        session = MagicMock()
        session.execute.side_effect = OperationalError("down", None, None)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            with pytest.raises(McpError):
                tool()

        session.close.assert_called_once()

    def test_null_text_yields_zero_size_kb(self):
        """doc.text=None → size_kb=0 (AC-2)."""
        doc = _make_doc(text=None)
        session = _mock_session([doc], total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool()

        assert result["articles"][0]["size_kb"] == 0

    def test_null_created_at_yields_none_added_at(self):
        """doc.created_at=None → added_at=None (AC-2)."""
        doc = _make_doc(created_at=None)
        doc.created_at = None
        session = _mock_session([doc], total=1)

        tool = _get_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool()

        assert result["articles"][0]["added_at"] is None


# ---------------------------------------------------------------------------
# TestLenieGetArticle
# ---------------------------------------------------------------------------

def _get_get_article_tool():
    """Register tools and return the lenie_get_article function."""
    cap = _CaptureMcp()
    register_lenie_tools(cap)
    return cap.get("lenie_get_article")


def _mock_session_single(doc_or_none):
    """Return a mock session for single-document lookup via .scalars().first()."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = doc_or_none
    session.execute.return_value = result
    return session


def _make_full_doc(
    id: int = 10,
    title: str = "Full article",
    url: str = "https://example.com/full",
    text: str = "x" * 4096,
    note: str | None = "some note",
    language: str | None = "pl",
    document_type: str = "webpage",
    created_at: datetime.datetime | None = None,
    reviewed_at: datetime.datetime | None = None,
    obsidian_note_paths: list | None = None,
) -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.title = title
    doc.url = url
    doc.text = text
    doc.note = note
    doc.language = language
    doc.document_type = document_type
    doc.created_at = created_at or datetime.datetime(2026, 3, 10, 9, 0, 0)
    doc.reviewed_at = reviewed_at
    doc.obsidian_note_paths = obsidian_note_paths if obsidian_note_paths is not None else []
    return doc


class TestLenieGetArticle:

    def test_found_article_returns_all_required_keys(self):
        """Valid article_id returns dict with all 11 required fields (AC-2)."""
        doc = _make_full_doc(
            id=10,
            title="My Article",
            url="https://example.com/article",
            text="hello world " * 512,
            note="personal note",
            language="en",
            document_type="webpage",
            reviewed_at=datetime.datetime(2026, 4, 1, 12, 0, 0),
            obsidian_note_paths=["02-wiedza/Tech/article.md"],
        )
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(article_id=10)

        assert result["id"] == 10
        assert result["title"] == "My Article"
        assert result["source"] == "https://example.com/article"
        assert result["size_kb"] == len(("hello world " * 512).encode()) // 1024
        assert result["content"] == "hello world " * 512
        assert result["language"] == "en"
        assert result["user_note"] == "personal note"
        assert result["document_type"] == "webpage"
        assert result["added_at"] == "2026-03-10T09:00:00"
        assert result["reviewed_at"] == "2026-04-01T12:00:00"
        assert result["obsidian_note_paths"] == ["02-wiedza/Tech/article.md"]

    def test_null_text_yields_zero_size_kb_and_none_content(self):
        """doc.text=None → size_kb=0, content=None (AC-2)."""
        doc = _make_full_doc(text=None)
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(article_id=doc.id)

        assert result["size_kb"] == 0
        assert result["content"] is None

    def test_null_reviewed_at_yields_none(self):
        """doc.reviewed_at=None → reviewed_at=None in response (AC-2)."""
        doc = _make_full_doc(reviewed_at=None)
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(article_id=doc.id)

        assert result["reviewed_at"] is None

    def test_article_not_found_raises_mcp_error(self):
        """When article does not exist, McpError with ARTICLE_NOT_FOUND is raised (AC-3)."""
        session = _mock_session_single(None)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            with pytest.raises(McpError) as exc_info:
                tool(article_id=9999)

        assert exc_info.value.error.code == McpErrorCode.ARTICLE_NOT_FOUND

    def test_operational_error_raises_database_unavailable(self):
        """OperationalError from DB raises McpError with DATABASE_UNAVAILABLE (AC-4)."""
        session = MagicMock()
        session.execute.side_effect = OperationalError("connection refused", None, None)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            with pytest.raises(McpError) as exc_info:
                tool(article_id=1)

        assert exc_info.value.error.code == McpErrorCode.DATABASE_UNAVAILABLE

    def test_session_closed_on_success(self):
        """session.close() is called after successful retrieval (AC-7)."""
        doc = _make_full_doc()
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            tool(article_id=doc.id)

        session.close.assert_called_once()

    def test_session_closed_on_operational_error(self):
        """session.close() is called even when OperationalError occurs (AC-7)."""
        session = MagicMock()
        session.execute.side_effect = OperationalError("down", None, None)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            with pytest.raises(McpError):
                tool(article_id=1)

        session.close.assert_called_once()

    def test_null_created_at_yields_none_added_at(self):
        """doc.created_at=None → added_at=None in response (AC-2)."""
        doc = _make_full_doc()
        doc.created_at = None
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(article_id=doc.id)

        assert result["added_at"] is None

    def test_null_obsidian_note_paths_yields_empty_list(self):
        """doc.obsidian_note_paths=None (legacy record) → obsidian_note_paths=[] in response (AC-2)."""
        doc = _make_full_doc()
        doc.obsidian_note_paths = None
        session = _mock_session_single(doc)

        tool = _get_get_article_tool()
        with patch("mcp_server.tools.lenie.get_session", return_value=session):
            result = tool(article_id=doc.id)

        assert result["obsidian_note_paths"] == []
