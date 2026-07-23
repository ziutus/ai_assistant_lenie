"""Unit tests for library/person_registry.py — person mention resolution pipeline."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, DocumentPerson, Person, PersonAlias  # noqa: E402
from library.person_registry import (  # noqa: E402
    CONFIDENCE_ALIAS,
    CONFIDENCE_MANUAL_CONFIRMED,
    CONFIDENCE_MANUAL_REVIEW,
    CONFIDENCE_WIKIDATA,
    approve_review_link,
    label_matches_mention,
    merge_review_link,
    reject_review_link,
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


class TestLabelMatchesMention:
    @pytest.mark.parametrize("mention,label", [
        ("Lepen", "Marine Le Pen"),
        ("Macrona", "Emmanuel Macron"),
        ("Trump", "Donald Trump"),
        ("Erdogan", "Recep Tayyip Erdoğan"),
        ("Donald Tusk", "Donald Tusk"),
    ])
    def test_accepts_name_consistent_picks(self, mention, label):
        assert label_matches_mention(mention, label) is True

    @pytest.mark.parametrize("mention,label", [
        # Realne błędne dopasowania z E2E 2026-07-10 (doc 9216)
        ("demokratas", "Žemaitė"),
        ("Talibanu", "Abdul Ghani Beradar"),
        ("Taliban", "Dadullah"),
    ])
    def test_rejects_unrelated_names(self, mention, label):
        assert label_matches_mention(mention, label) is False


def _review_link(link_id=100, doc_id=42, person_id=7, raw_mention="Jimmy Ruston"):
    link = MagicMock(spec=DocumentPerson)
    link.id = link_id
    link.document_id = doc_id
    link.person_id = person_id
    link.raw_mention = raw_mention
    link.confidence = CONFIDENCE_MANUAL_REVIEW
    return link


def _person(person_id=7, name="Jimmy Rushton", aliases=()):
    person = MagicMock(spec=Person)
    person.id = person_id
    person.canonical_name = name
    alias_rows = []
    for a in aliases:
        row = MagicMock(spec=PersonAlias)
        row.alias = a
        alias_rows.append(row)
    person.aliases = alias_rows
    return person


class TestApproveReviewLink:
    def test_sets_manual_confirmed(self):
        link = _review_link()
        result = approve_review_link(MagicMock(), link)

        assert link.confidence == CONFIDENCE_MANUAL_CONFIRMED
        assert result == {"action": "approve", "link_id": 100, "person_id": 7}


class TestRejectReviewLink:
    def test_deletes_link_and_orphaned_person(self):
        link = _review_link()
        person = _person()
        session = MagicMock()
        session.execute.return_value.scalar.return_value = 0  # no remaining links
        session.get.return_value = person

        result = reject_review_link(session, link)

        assert result["person_deleted"] is True
        deleted = [c.args[0] for c in session.delete.call_args_list]
        assert deleted == [link, person]

    def test_keeps_person_with_other_links(self):
        link = _review_link()
        session = MagicMock()
        session.execute.return_value.scalar.return_value = 2  # person still linked elsewhere

        result = reject_review_link(session, link)

        assert result["person_deleted"] is False
        deleted = [c.args[0] for c in session.delete.call_args_list]
        assert deleted == [link]


class TestMergeReviewLink:
    def test_repoints_link_and_adds_aliases(self):
        link = _review_link(raw_mention="Jimmy Ruston", person_id=7)
        source = _person(person_id=7, name="Jimmy Ruston (source)")
        target = _person(person_id=9, name="Jimmy Rushton")
        session = MagicMock()
        session.get.side_effect = lambda model, pid: {7: source}.get(pid)
        # duplicate-link check -> None, orphan check -> 0 remaining
        session.execute.return_value.scalars.return_value.first.return_value = None
        session.execute.return_value.scalar.return_value = 0

        with patch("library.person_registry._add_alias") as mock_alias:
            result = merge_review_link(session, link, target)

        assert link.person_id == 9
        assert link.confidence == CONFIDENCE_MANUAL_CONFIRMED
        assert result["person_deleted"] is True
        assert result["link_dropped_as_duplicate"] is False
        added_aliases = {c.args[2] for c in mock_alias.call_args_list}
        assert added_aliases == {"Jimmy Ruston", "Jimmy Ruston (source)"}

    def test_duplicate_target_link_drops_reviewed_link(self):
        link = _review_link(person_id=7)
        target = _person(person_id=9)
        existing = MagicMock(spec=DocumentPerson)
        session = MagicMock()
        session.get.side_effect = lambda model, pid: {7: _person(person_id=7)}.get(pid)
        session.execute.return_value.scalars.return_value.first.return_value = existing
        session.execute.return_value.scalar.return_value = 1  # source still linked elsewhere

        with patch("library.person_registry._add_alias"):
            result = merge_review_link(session, link, target)

        assert result["link_dropped_as_duplicate"] is True
        assert result["person_deleted"] is False
        assert link.person_id == 7  # untouched — the link itself was deleted
        deleted = [c.args[0] for c in session.delete.call_args_list]
        assert deleted == [link]

    def test_merge_into_same_person_rejected(self):
        link = _review_link(person_id=9)
        target = _person(person_id=9)

        with pytest.raises(ValueError):
            merge_review_link(MagicMock(), link, target)


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

    def test_bare_surname_uses_context_instead_of_ambiguous_alias(self):
        existing = _person(person_id=7, name="Donald Trump")
        existing.wikidata_qid = "Q22686"
        existing.description = "prezydent Stanów Zjednoczonych"
        candidates = [
            {"qid": "Q22686", "label": "Donald Trump", "description": "prezydent Stanów Zjednoczonych"},
            {"qid": "Q3713655", "label": "Donald Trump Jr.", "description": "amerykański przedsiębiorca"},
        ]
        session = _session([_entity("Trump")])
        qid_result = MagicMock()
        qid_result.scalars.return_value.first.return_value = existing
        link_result = MagicMock()
        link_result.scalars.return_value.first.return_value = None
        session.execute.side_effect = [qid_result, link_result]

        with patch("library.person_registry.find_by_alias") as mock_alias, \
                patch("library.person_registry._add_alias"), \
                patch("library.wikidata_client.search_persons", return_value=candidates), \
                patch("library.article_tagging.confirm_person_with_llm", return_value="Q22686") as mock_llm:
            result = resolve_document_persons(session, _doc(title="Trump przemawia jako prezydent"), "prezydent Trump")

        mock_alias.assert_not_called()
        mock_llm.assert_called_once()
        assert result["linked"] == [("Trump", "Donald Trump", CONFIDENCE_WIKIDATA)]

    def test_wikidata_pick_enriches_existing_local_person_without_qid(self):
        existing = _person(person_id=7, name="Donald Trump")
        existing.wikidata_qid = None
        existing.description = None
        candidates = [
            {"qid": "Q22686", "label": "Donald Trump", "description": "prezydent Stanów Zjednoczonych"},
        ]
        session = _session([_entity("Trump")])

        with patch("library.person_registry.find_by_alias", return_value=existing) as mock_alias, \
                patch("library.person_registry._add_alias"), \
                patch("library.wikidata_client.search_persons", return_value=candidates), \
                patch("library.article_tagging.confirm_person_with_llm", return_value="Q22686"):
            result = resolve_document_persons(session, _doc(), "prezydent Trump")

        mock_alias.assert_called_once_with(session, "Donald Trump")
        assert existing.wikidata_qid == "Q22686"
        assert existing.description == "prezydent Stanów Zjednoczonych"
        assert result["linked"] == [("Trump", "Donald Trump", CONFIDENCE_WIKIDATA)]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert created == []

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

    def test_name_mismatched_llm_pick_rejected(self):
        """LLM wybrał kandydata o niepasującej nazwie → odrzucony (jednowyrazowa wzmianka → skip)."""
        session = _session([_entity("demokratas")])
        candidates = [{"qid": "Q287069", "label": "Žemaitė", "description": "litewska pisarka"}]
        with patch("library.wikidata_client.search_persons", return_value=candidates):
            with patch("library.article_tagging.confirm_person_with_llm", return_value="Q287069"):
                result = resolve_document_persons(session, _doc(), "tekst")

        assert result["skipped"] == ["demokratas"]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert created == []

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
