"""Unit tests for [[Title]] Obsidian wikilink resolution in the reader.

GET /document/<id>/chapter/<pos> resolves [[Title]]/[[Title|Display]]/
[[Title#Heading]] links fresh on every call (chunk_review_routes.py's
_wiki_link_targets/_resolve_wiki_links) rather than writing them into
text_md once at import time -- a link to a note created or renamed after
the linking note was last imported must still resolve without requiring
the linking note itself to be re-touched/re-imported.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document  # noqa: E402


class TestWikiLinkTargets:
    def test_extracts_plain_target(self):
        assert cr._wiki_link_targets("tekst [[yq]] dalej") == {"yq"}

    def test_extracts_target_with_display_label(self):
        assert cr._wiki_link_targets("[[narzędzie Command Line Interface (cli)|CLI]]") == {
            "narzędzie command line interface (cli)",
        }

    def test_drops_heading_fragment(self):
        assert cr._wiki_link_targets("[[Linux#Instalacja]]") == {"linux"}

    def test_drops_heading_fragment_with_display_label(self):
        assert cr._wiki_link_targets("[[Linux#Instalacja|jak zainstalować]]") == {"linux"}

    def test_deduplicates_case_insensitively(self):
        assert cr._wiki_link_targets("[[Linux]] i jeszcze raz [[LINUX]]") == {"linux"}

    def test_no_links_returns_empty_set(self):
        assert cr._wiki_link_targets("zwykły tekst bez linków") == set()

    def test_ignores_a_lone_unclosed_bracket_pair(self):
        assert cr._wiki_link_targets("[niedomknięty] tekst") == set()


class TestResolveWikiLinks:
    def test_no_targets_skips_the_query_entirely(self):
        session = MagicMock()

        result = cr._resolve_wiki_links(session, "zwykły tekst, żadnych linków")

        assert result == {}
        session.query.assert_not_called()

    def test_single_match_resolves(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [(101, "yq")]

        assert cr._resolve_wiki_links(session, "[[yq]]") == {"yq": 101}

    def test_title_matching_is_case_insensitive(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [(101, "Linux")]

        assert cr._resolve_wiki_links(session, "[[linux]]") == {"linux": 101}

    def test_no_matching_document_is_left_unresolved(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []

        assert cr._resolve_wiki_links(session, "[[nieznana notatka]]") == {}

    def test_ambiguous_title_is_left_unresolved_not_guessed(self):
        """Two obsidian_note documents sharing a title -- same 0/1/N
        discipline as publisher_registry.py/search/name_resolution.py."""
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [(101, "yq"), (202, "yq")]

        assert cr._resolve_wiki_links(session, "[[yq]]") == {}

    def test_resolves_multiple_distinct_targets_independently(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [(101, "yq"), (202, "Linux")]

        result = cr._resolve_wiki_links(session, "[[yq]] i osobno [[Linux]]")

        assert result == {"yq": 101, "linux": 202}


NOTE_WITH_WIKI_LINK = (
    "## jq\n\n"
    "**Purpose:** Parse json output\n\n"
    "there is also a command for parsing yaml called [[yq]]\n\n"
    "[[narzędzie Command Line Interface (cli)]]"
)


def _make_note(doc_id=9922) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = doc_id
    doc.document_type = "obsidian_note"
    doc.text = None
    doc.text_md = NOTE_WITH_WIKI_LINK
    doc.text_raw = None
    doc.title = "jq"
    doc.url = "obsidian://02-wiedza/Informatyka/narzedzia_cli/jq.md"
    doc.tags = "wiedza-informatyka,linux"
    doc.quality = None
    doc.published_on = None
    doc.ingested_at = None
    doc.obsidian_note_paths = []
    return doc


class TestChapterEndpointWikiLinks:
    @pytest.fixture
    def client(self, monkeypatch):
        doc = _make_note()
        session = MagicMock()
        session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
        session.scalars.return_value.first.return_value = None
        # The only session.query(...).filter(...).all() call in this route is
        # the Document.id/Document.title wikilink lookup -- the
        # DocumentReference/DocumentImage queries route through
        # .order_by(...).all() instead, so they stay on MagicMock's
        # default-empty iteration and are unaffected by this override.
        session.query.return_value.filter.return_value.all.return_value = [(101, "yq")]
        monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
        monkeypatch.setattr(cr, "_latest_run_for_document", lambda _session, _doc_id: None)

        app = flask.Flask(__name__)
        app.register_blueprint(cr.bp)
        return app.test_client()

    def test_resolved_link_appears_in_response(self, client):
        resp = client.get("/document/9922/chapter/1")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["wiki_links"] == {"yq": 101}

    def test_unresolved_link_is_simply_absent(self, client):
        """"narzędzie Command Line Interface (cli)" has no matching document
        in this fixture -- it must not appear in wiki_links at all (the
        reader treats a missing key as "render as plain text")."""
        resp = client.get("/document/9922/chapter/1")
        data = resp.get_json()

        assert "narzędzie command line interface (cli)" not in data["wiki_links"]
