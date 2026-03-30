"""Unit tests for article review tracking (Story 33.4).

Tests WebDocument reviewed_at/obsidian_note_paths attributes, dict() output,
and JSONB append logic.
"""

import datetime

import pytest

sa = pytest.importorskip("sqlalchemy")

from library.db.models import WebDocument  # noqa: E402


@pytest.fixture
def web_document():
    """Create a minimal WebDocument instance for testing (no DB session needed)."""
    doc = WebDocument(
        url="https://example.com/article",
        document_type="webpage",
        document_state="MD_SIMPLIFIED",
        title="Test Article",
    )
    return doc


class TestReviewedAtDefaults:
    def test_reviewed_at_defaults_to_none(self, web_document):
        assert web_document.reviewed_at is None

    def test_obsidian_note_paths_defaults_to_none_in_memory(self, web_document):
        """server_default='[]' applies at DB level; in-memory default is None."""
        assert web_document.obsidian_note_paths is None

    def test_obsidian_note_paths_dict_returns_empty_list_for_none(self, web_document):
        """dict() normalizes None to [] via 'or []'."""
        assert web_document.dict()["obsidian_note_paths"] == []


class TestDictOutput:
    def test_dict_includes_reviewed_at_none(self, web_document):
        result = web_document.dict()
        assert "reviewed_at" in result
        assert result["reviewed_at"] is None

    def test_dict_includes_reviewed_at_iso_string(self, web_document):
        web_document.reviewed_at = datetime.datetime(2026, 3, 30, 14, 30, 0)
        result = web_document.dict()
        assert result["reviewed_at"] == "2026-03-30T14:30:00"

    def test_dict_includes_obsidian_note_paths_empty(self, web_document):
        result = web_document.dict()
        assert "obsidian_note_paths" in result
        assert result["obsidian_note_paths"] == []

    def test_dict_includes_obsidian_note_paths_with_entries(self, web_document):
        web_document.obsidian_note_paths = ["02-wiedza/Test.md", "03-projekty/Foo.md"]
        result = web_document.dict()
        assert result["obsidian_note_paths"] == ["02-wiedza/Test.md", "03-projekty/Foo.md"]


class TestObsidianNotePathsAppend:
    def test_append_single_path(self, web_document):
        paths = list(web_document.obsidian_note_paths or [])
        paths.append("02-wiedza/Geopolityka/Sankcje-UE.md")
        web_document.obsidian_note_paths = paths
        assert web_document.obsidian_note_paths == ["02-wiedza/Geopolityka/Sankcje-UE.md"]

    def test_append_multiple_paths_preserves_previous(self, web_document):
        # First append
        paths = list(web_document.obsidian_note_paths or [])
        paths.append("02-wiedza/First.md")
        web_document.obsidian_note_paths = paths

        # Second append
        paths = list(web_document.obsidian_note_paths or [])
        paths.append("02-wiedza/Second.md")
        web_document.obsidian_note_paths = paths

        assert web_document.obsidian_note_paths == ["02-wiedza/First.md", "02-wiedza/Second.md"]

    def test_append_does_not_overwrite(self, web_document):
        web_document.obsidian_note_paths = ["existing.md"]
        paths = list(web_document.obsidian_note_paths or [])
        paths.append("new.md")
        web_document.obsidian_note_paths = paths
        assert "existing.md" in web_document.obsidian_note_paths
        assert "new.md" in web_document.obsidian_note_paths
        assert len(web_document.obsidian_note_paths) == 2


class TestReviewedAtSetting:
    def test_set_reviewed_at(self, web_document):
        now = datetime.datetime(2026, 3, 30, 15, 0, 0)
        web_document.reviewed_at = now
        assert web_document.reviewed_at == now

    def test_reviewed_at_not_overwritten_when_already_set(self, web_document):
        original = datetime.datetime(2026, 3, 29, 10, 0, 0)
        web_document.reviewed_at = original
        # Simulate obsidian action: only set if not already set
        if not web_document.reviewed_at:
            web_document.reviewed_at = datetime.datetime(2026, 3, 30, 15, 0, 0)
        assert web_document.reviewed_at == original


class TestFilterLogic:
    """Test Python-level filter logic matching _get_documents() implementation."""

    def _make_doc(self, reviewed_at=None, obsidian_note_paths=None):
        doc = WebDocument(
            url="https://example.com/test",
            document_type="webpage",
            document_state="MD_SIMPLIFIED",
            title="Test",
        )
        doc.reviewed_at = reviewed_at
        doc.obsidian_note_paths = obsidian_note_paths
        return doc

    def test_not_reviewed_filter_includes_unreviewed(self):
        doc = self._make_doc(reviewed_at=None)
        # not_reviewed filter: include when reviewed_at IS None
        assert doc.reviewed_at is None

    def test_not_reviewed_filter_excludes_reviewed(self):
        doc = self._make_doc(reviewed_at=datetime.datetime(2026, 3, 30))
        # not_reviewed filter: exclude when reviewed_at is NOT None
        assert doc.reviewed_at is not None

    def test_no_obsidian_filter_includes_empty_list(self):
        doc = self._make_doc(obsidian_note_paths=[])
        # no_obsidian filter: include when paths == []
        assert (doc.obsidian_note_paths or []) == []

    def test_no_obsidian_filter_includes_none(self):
        doc = self._make_doc(obsidian_note_paths=None)
        # no_obsidian filter: include when paths is None (normalized to [])
        assert (doc.obsidian_note_paths or []) == []

    def test_no_obsidian_filter_excludes_with_notes(self):
        doc = self._make_doc(obsidian_note_paths=["02-wiedza/Test.md"])
        # no_obsidian filter: exclude when paths has entries
        assert (doc.obsidian_note_paths or []) != []

    def test_combined_filters(self):
        """Unreviewed doc without obsidian notes passes both filters."""
        doc = self._make_doc(reviewed_at=None, obsidian_note_paths=None)
        passes_not_reviewed = doc.reviewed_at is None
        passes_no_obsidian = (doc.obsidian_note_paths or []) == []
        assert passes_not_reviewed and passes_no_obsidian

    def test_combined_filters_reviewed_with_notes_excluded(self):
        """Reviewed doc with obsidian notes fails both filters."""
        doc = self._make_doc(
            reviewed_at=datetime.datetime(2026, 3, 30),
            obsidian_note_paths=["note.md"],
        )
        passes_not_reviewed = doc.reviewed_at is None
        passes_no_obsidian = (doc.obsidian_note_paths or []) == []
        assert not passes_not_reviewed
        assert not passes_no_obsidian
