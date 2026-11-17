"""Namesakes and mangled names resolved through the document's countries (person_territory_match)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("unidecode")

from library.db.models import DocumentEntity, DocumentPerson, Person  # noqa: E402
from library.person_registry import (  # noqa: E402
    CONFIDENCE_ALIAS,
    CONFIDENCE_MANUAL_REVIEW,
    CONFIDENCE_WIKIDATA,
    resolve_document_persons,
)
from library.person_territory_match import (  # noqa: E402
    find_mangled_territory_person,
    find_territory_person,
    pick_wikidata_by_territory,
)

HADI = {"id": 311, "canonical_name": "Abd Rabu Mansur Hadi", "aliases": [], "wikidata_qid": "Q311"}
NUZAILI = {"id": 1469, "canonical_name": "Madżed Abdullah al-Nuzajli", "aliases": ["Nuzaili"], "wikidata_qid": None}
MALIKI = {"id": 1468, "canonical_name": "Turki Al-Maliki", "aliases": [], "wikidata_qid": "Q54054783"}
PEOPLE = [HADI, NUZAILI, MALIKI]


class TestPickWikidataByTerritory:
    def test_unique_known_namesake_wins(self):
        candidates = [{"qid": "Q1"}, {"qid": "Q54054783"}, {"qid": "Q3"}]
        assert pick_wikidata_by_territory(candidates, PEOPLE) == "Q54054783"

    def test_none_or_several_known_means_no_pick(self):
        assert pick_wikidata_by_territory([{"qid": "Q1"}], PEOPLE) is None
        assert pick_wikidata_by_territory([{"qid": "Q311"}, {"qid": "Q54054783"}], PEOPLE) is None


class TestFindTerritoryPerson:
    def test_surname_and_inflection(self):
        assert find_territory_person("Hadi", PEOPLE)["id"] == 311
        assert find_territory_person("Hadiego", PEOPLE)["id"] == 311

    def test_alias_and_unknown(self):
        assert find_territory_person("Nuzaili", PEOPLE)["id"] == 1469
        assert find_territory_person("Smith", PEOPLE) is None

    def test_two_people_with_the_same_surname_are_ambiguous(self):
        twin = {"id": 9, "canonical_name": "Ahmed Hadi", "aliases": []}
        assert find_territory_person("Hadi", [HADI, twin]) is None


class TestFindMangledTerritoryPerson:
    def test_sound_alike_surname(self):
        assert find_mangled_territory_person("Nuzajli", [HADI, MALIKI, {**NUZAILI, "aliases": []}])["id"] == 1469

    def test_sound_alike_full_name(self):
        assert find_mangled_territory_person("Turki Almaliki", PEOPLE)["id"] == 1468

    def test_unrelated_and_short_words_are_left_alone(self):
        assert find_mangled_territory_person("Kowalski", PEOPLE) is None
        assert find_mangled_territory_person("Hadi", [{**HADI, "canonical_name": "Hadu"}]) is None

    def test_two_equally_close_people_are_ambiguous(self):
        twins = [{"id": 1, "canonical_name": "Omar Nuzajlie", "aliases": []},
                 {"id": 2, "canonical_name": "Omar Nuzajlia", "aliases": []}]
        assert find_mangled_territory_person("Nuzajli", twins) is None


def _entity(text):
    ent = MagicMock(spec=DocumentEntity)
    ent.entity_text = text
    ent.entity_type = "persName"
    return ent


def _session(entities, persons):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = entities
    session.query.return_value.join.return_value.filter.return_value.all.return_value = []
    session.execute.return_value.scalars.return_value.first.return_value = None
    by_id = {p.id: p for p in persons}
    session.get.side_effect = lambda _model, pk: by_id.get(pk)
    return session


def _doc():
    doc = MagicMock()
    doc.id = 11263
    doc.title = "Jemen"
    doc.tags = ["kraj-jemen"]
    return doc


def _person(person_id, name):
    person = MagicMock(spec=Person)
    person.id = person_id
    person.canonical_name = name
    person.aliases = []
    return person


class TestResolveWithTerritory:
    def test_surname_resolves_without_network(self):
        hadi = _person(311, HADI["canonical_name"])
        session = _session([_entity("Hadi")], [hadi])
        with patch("library.person_registry._territory_people", return_value=PEOPLE), \
                patch("library.person_registry._add_alias"), \
                patch("library.wikidata_client.search_persons") as wd:
            result = resolve_document_persons(session, _doc(), "tekst")
        wd.assert_not_called()
        assert result["linked"] == [("Hadi", HADI["canonical_name"], CONFIDENCE_ALIAS)]

    def test_namesake_picked_without_llm(self):
        maliki = _person(1468, MALIKI["canonical_name"])
        session = _session([_entity("Turki Al-Malikiego")], [maliki])
        candidates = [{"qid": "Q1", "label": "Turki Al-Maliki", "description": "inny"},
                      {"qid": "Q54054783", "label": "Turki Al-Maliki", "description": "rzecznik"}]
        with patch("library.person_registry._territory_people", return_value=[
                {**MALIKI, "canonical_name": "Nikt Inny"}, {"id": 5, "canonical_name": "X Y", "aliases": [],
                                                           "wikidata_qid": "Q54054783"}]), \
                patch("library.person_registry._add_alias"), \
                patch("library.wikidata_client.search_persons", return_value=candidates), \
                patch("library.article_tagging.confirm_person_with_llm") as llm:
            result = resolve_document_persons(session, _doc(), "tekst")
        llm.assert_not_called()
        assert result["linked"][0][2] == CONFIDENCE_WIKIDATA

    def test_mangled_name_goes_to_review(self):
        nuzaili = _person(1469, NUZAILI["canonical_name"])
        session = _session([_entity("Nuzajlego")], [nuzaili])
        people = [{**NUZAILI, "aliases": []}, HADI]
        with patch("library.person_registry._territory_people", return_value=people), \
                patch("library.wikidata_client.search_persons", return_value=[]):
            result = resolve_document_persons(session, _doc(), "tekst")
        assert result["linked"] == [("Nuzajlego", NUZAILI["canonical_name"], CONFIDENCE_MANUAL_REVIEW)]
        links = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentPerson)]
        assert [link.person_id for link in links] == [1469]

    def test_no_territory_tags_changes_nothing(self):
        session = _session([_entity("Hadi")], [])
        doc = _doc()
        doc.tags = ["polityka"]
        with patch("library.wikidata_client.search_persons", return_value=[]) as wd:
            result = resolve_document_persons(session, doc, "tekst")
        wd.assert_called_once_with("Hadi")
        assert result["skipped"] == ["Hadi"]
