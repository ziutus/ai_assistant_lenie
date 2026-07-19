"""Unit tests for library/author_service.py — structured document authorship."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

import library.author_service as auth_svc  # noqa: E402
from library.author_service import split_author_names, set_document_authors  # noqa: E402
from library.db.models import DocumentPerson, Person  # noqa: E402


class TestSplitAuthorNames:
    def test_single_author(self):
        assert split_author_names("Michał Rogalski") == ["Michał Rogalski"]

    @pytest.mark.parametrize("raw", [
        "Michał Rogalski, Piotr Gruszka",
        "Michał Rogalski i Piotr Gruszka",
        "Michał Rogalski oraz Piotr Gruszka",
        "Michał Rogalski; Piotr Gruszka",
        "Michał Rogalski / Piotr Gruszka",
        "Michał Rogalski\nPiotr Gruszka",
    ])
    def test_separators(self, raw):
        assert split_author_names(raw) == ["Michał Rogalski", "Piotr Gruszka"]

    def test_portal_paste_with_duplicates_and_junk(self):
        # Copy-paste from a portal duplicates each name (avatar alt + link
        # text) and drags UI junk like the "Obserwuj" button label along
        raw = "Michał Rogalski\nMichał Rogalski\n\nObserwuj\nPiotr Gruszka\nPiotr Gruszka\n\nObserwuj"
        assert split_author_names(raw) == ["Michał Rogalski", "Piotr Gruszka"]

    def test_dedup_is_case_insensitive(self):
        assert split_author_names("Jan Kowalski, jan kowalski") == ["Jan Kowalski"]

    def test_empty_input(self):
        assert split_author_names("") == []
        assert split_author_names("  ,  ") == []

    def test_conjunction_inside_name_is_not_split(self):
        # "i"/"oraz" only split as standalone words
        assert split_author_names("Iga Nowak") == ["Iga Nowak"]


def _doc(doc_id=421):
    doc = MagicMock()
    doc.id = doc_id
    return doc


def _session(existing_author_links=()):
    """MagicMock session: first execute -> existing author links, later
    executes (per-name link lookup) -> no link found."""
    session = MagicMock()
    author_links_result = MagicMock()
    author_links_result.scalars.return_value.all.return_value = list(existing_author_links)
    no_link_result = MagicMock()
    no_link_result.scalars.return_value.first.return_value = None
    session.execute.side_effect = [author_links_result] + [no_link_result] * 20
    return session


class TestSetDocumentAuthors:
    def test_manual_entry_creates_persons_and_author_links(self):
        doc = _doc()
        session = _session()

        with patch.object(auth_svc, "find_by_alias", return_value=None), \
                patch.object(auth_svc, "get_document_authors", return_value=[]):
            set_document_authors(session, doc, ["Michał Rogalski", "Piotr Gruszka"], method="manual")

        assert doc.byline == "Michał Rogalski, Piotr Gruszka"
        assert doc.byline_method == "manual"
        added = [c.args[0] for c in session.add.call_args_list]
        persons = [a for a in added if isinstance(a, Person)]
        links = [a for a in added if isinstance(a, DocumentPerson)]
        assert [p.canonical_name for p in persons] == ["Michał Rogalski", "Piotr Gruszka"]
        assert all(link.role == "author" for link in links)
        assert all(link.confidence == "manual_confirmed" for link in links)

    def test_llm_new_person_is_queued_for_review(self):
        doc = _doc()
        session = _session()

        with patch.object(auth_svc, "find_by_alias", return_value=None), \
                patch.object(auth_svc, "get_document_authors", return_value=[]):
            set_document_authors(session, doc, ["Weronika Jaworska"], method="llm")

        assert doc.byline_method == "llm"
        links = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentPerson)]
        assert len(links) == 1
        assert links[0].confidence == "manual_review"

    def test_llm_known_person_links_as_alias_matched(self):
        doc = _doc()
        session = _session()
        known = MagicMock(spec=Person)
        known.id = 7

        with patch.object(auth_svc, "find_by_alias", return_value=known), \
                patch.object(auth_svc, "get_document_authors", return_value=[]):
            set_document_authors(session, doc, ["Jacek Losik"], method="llm")

        links = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentPerson)]
        assert len(links) == 1
        assert links[0].person_id == 7
        assert links[0].confidence == "alias_matched"

    def test_stale_author_link_is_deleted_and_orphan_cleaned(self):
        doc = _doc()
        stale = MagicMock(spec=DocumentPerson)
        stale.person_id = 99
        session = _session(existing_author_links=[stale])

        with patch.object(auth_svc, "find_by_alias", return_value=None), \
                patch.object(auth_svc, "get_document_authors", return_value=[]), \
                patch.object(auth_svc, "_delete_person_if_orphaned") as orphan:
            set_document_authors(session, doc, ["Nowy Autor"], method="manual")

        session.delete.assert_called_once_with(stale)
        orphan.assert_called_once_with(session, 99)

    def test_existing_mentioned_link_is_promoted_to_author(self):
        doc = _doc()
        known = MagicMock(spec=Person)
        known.id = 7
        mentioned_link = MagicMock(spec=DocumentPerson)
        mentioned_link.person_id = 7
        mentioned_link.role = "mentioned"
        mentioned_link.confidence = "wikidata_matched"

        session = MagicMock()
        author_links_result = MagicMock()
        author_links_result.scalars.return_value.all.return_value = []
        link_result = MagicMock()
        link_result.scalars.return_value.first.return_value = mentioned_link
        session.execute.side_effect = [author_links_result, link_result]

        with patch.object(auth_svc, "find_by_alias", return_value=known), \
                patch.object(auth_svc, "get_document_authors", return_value=[]):
            set_document_authors(session, doc, ["Donald Tusk"], method="llm")

        assert mentioned_link.role == "author"
        # LLM extraction must not downgrade an existing confidence
        assert mentioned_link.confidence == "wikidata_matched"
        session.add.assert_not_called()

    def test_empty_names_clear_author(self):
        doc = _doc()
        stale = MagicMock(spec=DocumentPerson)
        stale.person_id = 99
        session = _session(existing_author_links=[stale])

        with patch.object(auth_svc, "get_document_authors", return_value=[]), \
                patch.object(auth_svc, "_delete_person_if_orphaned"):
            set_document_authors(session, doc, [], method="manual")

        assert doc.byline is None
        assert doc.byline_method is None
        session.delete.assert_called_once_with(stale)


class TestExtractAuthorInfoParsing:
    def _extract(self, monkeypatch, response):
        import library.chunk_llm_analysis as llm
        monkeypatch.setattr(llm, "call_model", lambda *a, **kw: (response, 10))
        return llm.extract_author_info("tekst artykułu", "m")

    def test_multiple_authors(self, monkeypatch):
        result = self._extract(monkeypatch, '{"authors": ["Michał Rogalski", "Piotr Gruszka"]}')
        assert result == ["Michał Rogalski", "Piotr Gruszka"]

    def test_single_author_list(self, monkeypatch):
        assert self._extract(monkeypatch, '{"authors": ["Jan Kowalski"]}') == ["Jan Kowalski"]

    def test_legacy_single_author_shape(self, monkeypatch):
        assert self._extract(monkeypatch, '{"author": "Jan Kowalski"}') == ["Jan Kowalski"]

    def test_null_authors(self, monkeypatch):
        assert self._extract(monkeypatch, '{"authors": null}') is None

    def test_garbage_response(self, monkeypatch):
        assert self._extract(monkeypatch, "nie wiem") is None

    def test_empty_strings_filtered(self, monkeypatch):
        assert self._extract(monkeypatch, '{"authors": ["", "  "]}') is None
