"""Unit tests for library/person_registry.py — person mention resolution pipeline."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, Person  # noqa: E402
from library.person_registry import (  # noqa: E402
    CONFIDENCE_ALIAS,
    CONFIDENCE_MANUAL_REVIEW,
    CONFIDENCE_WIKIDATA,
    resolve_document_persons,
)


TUSK_CANDIDATES = [
    {"qid": "Q946", "label": "Donald Tusk", "description": "polski polityk, premier"},
    {"qid": "Q17278182", "label": "Donald Tusk", "description": "ojciec Donalda Tuska"},
]


def _entity(text):
    ent = MagicMock(spec=DocumentEntity)
    ent.entity_text = text
    ent.entity_type = "persName"
    return ent


def _doc(doc_id=42, title="Tytuł"):
    doc = MagicMock()
    doc.id = doc_id
    doc.title = title
    return doc


def _session(entities):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = entities
    # SELECTy (alias/fuzzy/qid/link) domyślnie nic nie znajdują
    session.execute.return_value.scalars.return_value.first.return_value = None
    return session


class TestResolveDocumentPersons:
    def test_wikidata_match_creates_person_and_link(self):
        session = _session([_entity("Donald Tusk")])
        with patch("library.wikidata_client.search_persons", return_value=TUSK_CANDIDATES):
            with patch("library.article_tagging.confirm_person_with_llm", return_value="Q946") as mock_llm:
                result = resolve_document_persons(session, _doc(), "artykuł o premierze")

        assert result["linked"] == [("Donald Tusk", "Donald Tusk", CONFIDENCE_WIKIDATA)]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert len(created) == 1
        assert created[0].wikidata_qid == "Q946"
        assert created[0].description == "polski polityk, premier"
        mock_llm.assert_called_once()

    def test_existing_alias_short_circuits_wikidata(self):
        person = MagicMock(spec=Person)
        person.id = 7
        person.canonical_name = "Donald Tusk"
        person.aliases = []
        session = _session([_entity("Donald Tusk")])
        # 1. wywołanie execute: dopasowanie canonical_name; kolejne (link-check) -> None
        first = MagicMock()
        first.scalars.return_value.first.return_value = person
        rest = MagicMock()
        rest.scalars.return_value.first.return_value = None
        session.execute.side_effect = [first, rest]

        with patch("library.wikidata_client.search_persons") as mock_wd:
            result = resolve_document_persons(session, _doc(), "tekst")

        mock_wd.assert_not_called()
        assert result["linked"] == [("Donald Tusk", "Donald Tusk", CONFIDENCE_ALIAS)]

    def test_single_word_without_wikidata_human_is_skipped(self):
        session = _session([_entity("Starlinek")])
        with patch("library.wikidata_client.search_persons", return_value=[]):
            result = resolve_document_persons(session, _doc(), "tekst")

        assert result["skipped"] == ["Starlinek"]
        assert result["linked"] == []
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert created == []

    def test_llm_rejects_all_candidates_falls_through(self):
        """LLM mówi NONE → nazwa dwuczłonowa trafia do rejestru jako manual_review."""
        session = _session([_entity("Donald Tusk")])
        with patch("library.wikidata_client.search_persons", return_value=TUSK_CANDIDATES):
            with patch("library.article_tagging.confirm_person_with_llm", return_value=None):
                result = resolve_document_persons(session, _doc(), "tekst")

        assert result["linked"] == [("Donald Tusk", "Donald Tusk", CONFIDENCE_MANUAL_REVIEW)]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert len(created) == 1
        assert created[0].wikidata_qid is None

    def test_multiword_unknown_person_gets_manual_review_row(self):
        session = _session([_entity("Jimmy Rushton")])
        with patch("library.wikidata_client.search_persons", return_value=[]):
            result = resolve_document_persons(session, _doc(), "tekst")

        assert result["linked"] == [("Jimmy Rushton", "Jimmy Rushton", CONFIDENCE_MANUAL_REVIEW)]

    def test_fuzzy_registry_match_queued_for_review(self):
        person = MagicMock(spec=Person)
        person.id = 9
        person.canonical_name = "Jimmy Rushton"
        person.aliases = []
        session = _session([_entity("Jimmy Ruston")])
        # execute: alias(canonical)=None, alias(alias)=None, fuzzy(canonical)=person, link-check=None
        results = []
        for value in [None, None, person, None]:
            r = MagicMock()
            r.scalars.return_value.first.return_value = value
            results.append(r)
        session.execute.side_effect = results

        with patch("library.wikidata_client.search_persons", return_value=[]):
            result = resolve_document_persons(session, _doc(), "tekst")

        assert result["linked"] == [("Jimmy Ruston", "Jimmy Rushton", CONFIDENCE_MANUAL_REVIEW)]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert created == []  # dopasowany do istniejącego, nie tworzy nowego
