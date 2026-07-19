"""Unit tests for dynamodb_sync.py ORM migration (Story 29.1, Task 1).

Pre-mocks boto3 and related modules so that importing dynamodb_sync does
not fail when botocore/s3transfer are broken or unavailable.
"""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sa = pytest.importorskip("sqlalchemy")

# ---------------------------------------------------------------------------
# Pre-mock boto3 and its transitive dependencies so dynamodb_sync can be
# imported without a working botocore installation.
# ---------------------------------------------------------------------------
_boto3_mock = MagicMock()
_boto3_ddb_mock = MagicMock()
_boto3_ddb_cond_mock = MagicMock()
_boto3_ddb_cond_mock.Key = MagicMock()

_botocore_mock = MagicMock()
_botocore_exc_mock = MagicMock()
_botocore_exc_mock.ClientError = type("ClientError", (Exception,), {})

for _name, _mock in [
    ("boto3", _boto3_mock),
    ("boto3.dynamodb", _boto3_ddb_mock),
    ("boto3.dynamodb.conditions", _boto3_ddb_cond_mock),
    ("botocore", _botocore_mock),
    ("botocore.exceptions", _botocore_exc_mock),
]:
    if _name not in sys.modules:
        sys.modules[_name] = _mock

from library.models.stalker_document_status import StalkerDocumentStatus  # noqa: E402, F401


class TestIncrementalWatermark:
    def test_date_uses_midnight_in_configured_timezone(self):
        from imports.dynamodb_sync import parse_since

        result = parse_since("2026-07-20", ZoneInfo("Europe/Warsaw"))
        assert result == datetime(2026, 7, 19, 22, 0, 0, tzinfo=timezone.utc)

    def test_explicit_offset_wins_over_working_timezone(self):
        from imports.dynamodb_sync import parse_since

        result = parse_since("2026-07-20T01:02:03+02:00", ZoneInfo("UTC"))
        assert result == datetime(2026, 7, 19, 23, 2, 3, tzinfo=timezone.utc)

    def test_naive_timestamp_defaults_to_utc(self):
        from imports.dynamodb_sync import parse_since

        result = parse_since("2026-07-20T01:02:03", ZoneInfo("UTC"))
        assert result == datetime(2026, 7, 20, 1, 2, 3, tzinfo=timezone.utc)

    def test_last_successful_run_start_is_utc_to_seconds(self):
        from imports.dynamodb_sync import get_last_successful_sync_timestamp

        session = MagicMock()
        session.scalar.return_value = datetime(2026, 7, 20, 1, 2, 3, 987654)
        result = get_last_successful_sync_timestamp(session)
        assert result == datetime(2026, 7, 20, 1, 2, 3, tzinfo=timezone.utc)

    def test_dynamodb_items_are_filtered_by_exact_created_at(self, monkeypatch):
        from imports import dynamodb_sync

        table = MagicMock()
        table.query.return_value = {
            "Items": [
                {"id": "old", "created_at": "2026-07-20T01:02:02"},
                {"id": "edge", "created_at": "2026-07-20T01:02:03Z"},
                {"id": "new", "created_at": "2026-07-20T01:02:04+00:00"},
            ]
        }
        monkeypatch.setattr(dynamodb_sync.boto3, "resource", lambda *_args, **_kwargs: MagicMock(Table=lambda _n: table))
        monkeypatch.setattr(
            dynamodb_sync,
            "datetime",
            type("FixedDateTime", (datetime,), {"now": classmethod(lambda cls, tz=None: datetime(2026, 7, 20, 2, tzinfo=timezone.utc))}),
        )

        result = dynamodb_sync.get_dynamodb_items(
            "table", datetime(2026, 7, 20, 1, 2, 3, tzinfo=timezone.utc),
        )
        assert [item["id"] for item in result] == ["edge", "new"]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a mock SQLAlchemy Session."""
    session = MagicMock(spec=["add", "commit", "close", "scalars", "execute"])
    return session


def _dynamo_item(**overrides):
    """Return a minimal DynamoDB item dict."""
    base = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "language": "en",
        "source": "own",
        "type": "link",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests for sync_item_to_postgres
# ---------------------------------------------------------------------------


class TestSyncItemToPostgres:
    """Tests for sync_item_to_postgres using DocumentService.import_document()."""

    @patch("imports.dynamodb_sync.DocumentService")
    def test_new_document_added(self, MockDocService):
        """New document is created via DocumentService and committed."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 42
        mock_doc.title = "Test Article"
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert result == ("added", 42)
        MockDocService.return_value.import_document.assert_called_once()

    @patch("imports.dynamodb_sync.DocumentService")
    def test_duplicate_skipped(self, MockDocService):
        """Existing document is skipped (not inserted)."""
        session = _make_session()
        existing = MagicMock()
        existing.id = 99
        MockDocService.return_value.import_document.return_value = (existing, "skipped")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        assert result == ("skipped", None)

    @patch("imports.dynamodb_sync.DocumentService")
    def test_created_at_set_via_orm(self, MockDocService):
        """DynamoDB created_at maps to the ingested_at metadata kwarg."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 1
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item(created_at="2026-01-15T10:30:00")
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        call_kwargs = MockDocService.return_value.import_document.call_args
        assert call_kwargs[1]["ingested_at"] == "2026-01-15T10:30:00"

    @patch("imports.dynamodb_sync.DocumentService")
    def test_chapter_list_set_via_orm(self, MockDocService):
        """chapter_list is passed to DocumentService.import_document()."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 1
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item(chapter_list="ch1;ch2;ch3")
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        call_kwargs = MockDocService.return_value.import_document.call_args
        assert call_kwargs[1]["chapter_list"] == "ch1;ch2;ch3"

    @patch("imports.dynamodb_sync.DocumentService")
    def test_processing_status_with_s3_content(self, MockDocService):
        """processing_status is DOCUMENT_INTO_DATABASE when S3 content exists."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 1
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        sync_item_to_postgres(item, "some text", "<html>", dry_run=False, session=session)

        call_kwargs = MockDocService.return_value.import_document.call_args
        assert call_kwargs[1]["processing_status"] == "DOCUMENT_INTO_DATABASE"

    @patch("imports.dynamodb_sync.DocumentService")
    def test_processing_status_without_content(self, MockDocService):
        """processing_status is URL_ADDED when no S3 content."""
        session = _make_session()

        mock_doc = MagicMock()
        mock_doc.id = 1
        MockDocService.return_value.import_document.return_value = (mock_doc, "added")

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        sync_item_to_postgres(item, None, None, dry_run=False, session=session)

        call_kwargs = MockDocService.return_value.import_document.call_args
        assert call_kwargs[1]["processing_status"] == "URL_ADDED"

    @patch("imports.dynamodb_sync.DocumentService")
    def test_dry_run_no_db_writes(self, MockDocService):
        """dry_run mode does not write to DB."""
        session = _make_session()

        from imports.dynamodb_sync import sync_item_to_postgres

        item = _dynamo_item()
        result = sync_item_to_postgres(item, None, None, dry_run=True, session=session)

        assert result == ("added", None)
        MockDocService.return_value.import_document.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for check_markdown_deps_installed (preflight dependency check)
# ---------------------------------------------------------------------------


class TestCheckMarkdownDepsInstalled:
    """The 'markdown' optional dependency group (html2markdown) is needed to
    convert webpage HTML into markdown. Missing it should fail fast with an
    actionable message, not crash mid-run after AWS calls/DB writes.
    """

    def test_passes_when_dependency_importable(self):
        from imports.dynamodb_sync import check_markdown_deps_installed

        # html2markdown is installed in this environment — should not raise/exit.
        check_markdown_deps_installed()

    def test_exits_with_actionable_message_when_missing(self, monkeypatch, capsys):
        from imports.dynamodb_sync import check_markdown_deps_installed

        # A None entry in sys.modules makes `import html2markdown` raise ImportError,
        # simulating the missing-dependency case without uninstalling the package.
        monkeypatch.setitem(sys.modules, "html2markdown", None)

        with pytest.raises(SystemExit) as exc_info:
            check_markdown_deps_installed()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "html2markdown" in captured.out
        assert "uv sync --extra markdown" in captured.out


# ---------------------------------------------------------------------------
# Tests for process_article_content (text_extracted / text_md persistence)
# ---------------------------------------------------------------------------


class TestProcessArticleContent:
    """process_article_content persists text_extracted (pre-clean) and text_md
    (post clean_article_text) ONLY when LLM extraction succeeded — --skip-llm
    and failed extraction must leave both fields untouched.
    """

    def _run(self, monkeypatch, extract_result, skip_llm=False, commit_raises=False):
        """Run process_article_content with mocked pipeline; return (result, doc, session, cleaner_calls)."""
        from imports import dynamodb_sync

        doc = MagicMock()
        doc.url = "https://example.com/article"

        session = MagicMock(spec=["commit", "rollback"])
        if commit_raises:
            session.commit.side_effect = RuntimeError("db down")

        monkeypatch.setattr(dynamodb_sync.os.path, "isfile", lambda p: True)
        monkeypatch.setattr(
            dynamodb_sync, "Document",
            MagicMock(get_by_id=MagicMock(return_value=doc)),
        )
        monkeypatch.setattr(
            "library.article_pipeline.extract_article",
            lambda *args, **kwargs: extract_result,
        )

        cleaner_calls = []

        def fake_clean(text, url=""):
            cleaner_calls.append((text, url))
            return {"text": f"CLEANED::{text}", "links": [], "images": []}

        monkeypatch.setattr("library.article_cleaner.clean_article_text", fake_clean)

        result = dynamodb_sync.process_article_content(
            doc_id=42, cache_base_dir="/cache", session=session, skip_llm=skip_llm,
        )
        return result, doc, session, cleaner_calls

    def test_success_saves_text_extracted_and_text_md(self, monkeypatch):
        result, doc, session, cleaner_calls = self._run(
            monkeypatch, extract_result=("raw markdown", "extracted article"),
        )

        assert result == (True, True)
        assert doc.text_extracted == "extracted article"
        assert doc.text_md == "CLEANED::extracted article"
        assert cleaner_calls == [("extracted article", doc.url)]
        session.commit.assert_called_once()
        session.rollback.assert_not_called()

    def test_skip_llm_does_not_touch_text_fields(self, monkeypatch):
        result, doc, session, cleaner_calls = self._run(
            monkeypatch, extract_result=("raw markdown", None), skip_llm=True,
        )

        assert result == (True, False)
        assert not isinstance(doc.text_extracted, str)
        assert not isinstance(doc.text_md, str)
        assert cleaner_calls == []
        session.commit.assert_not_called()

    def test_failed_extraction_does_not_touch_text_fields(self, monkeypatch):
        result, doc, session, cleaner_calls = self._run(
            monkeypatch, extract_result=("raw markdown", None),
        )

        assert result == (True, False)
        assert not isinstance(doc.text_extracted, str)
        assert not isinstance(doc.text_md, str)
        assert cleaner_calls == []
        session.commit.assert_not_called()

    def test_markdown_failure_returns_false_false(self, monkeypatch):
        result, doc, session, cleaner_calls = self._run(
            monkeypatch, extract_result=(None, None),
        )

        assert result == (False, False)
        assert cleaner_calls == []
        session.commit.assert_not_called()

    def test_commit_failure_rolls_back_and_warns(self, monkeypatch, capsys):
        result, doc, session, cleaner_calls = self._run(
            monkeypatch, extract_result=("raw markdown", "extracted article"),
            commit_raises=True,
        )

        # Extraction itself succeeded — only persistence failed.
        assert result == (True, True)
        session.rollback.assert_called_once()
        captured = capsys.readouterr()
        assert "WARNING: failed to save text_extracted/text_md" in captured.out
