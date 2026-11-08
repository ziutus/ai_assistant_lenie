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
    find_document_person,
    is_surname_mention,
    matches_person_name,
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


class TestIsSurnameMention:
    def test_surname_of_multiword_label(self):
        assert is_surname_mention("Tusk", "Donald Tusk")
        assert is_surname_mention("Tuska", "Donald Tusk")
        assert is_surname_mention("Lepen", "Marine Le Pen")

    def test_given_name_or_single_word_label_rejected(self):
        assert not is_surname_mention("Ewa", "Ewa Kopacz")
        assert not is_surname_mention("Ewa", "Ewa")
        assert not is_surname_mention("Ew", "Donald Ew")


class TestMatchesPersonName:
    @pytest.mark.parametrize("mention,label", [
        ("Musk", "Elon Musk"),
        ("Muska", "Elon Musk"),
        ("Elon muskiem", "Elon Musk"),          # doc 11239: lemat z małą literą
        ("Elona Muska", "Elon Musk"),
        ("Zabdyr-Jamróz", "Michał Zabdyr-Jamróz"),
        ("Zabdyra-Jamroza", "Michał Zabdyr-Jamróz"),   # odmiana + bez polskich znaków
        ("Jamroza", "Michał Zabdyr-Jamróz"),
        ("Kowalskiego", "Jan Kowalski"),
    ])
    def test_accepts_forms_of_the_name(self, mention, label):
        assert matches_person_name(mention, label) is True

    @pytest.mark.parametrize("mention,label", [
        ("Ewa", "Ewa Kopacz"),                   # samo imię nikogo nie identyfikuje
        ("Elon", "Elon Musk"),
        ("Nowak", "Jan Nowakowski"),             # inne nazwisko, nie odmiana
        ("Ivanka Trump", "Donald Trump"),
        ("Donald Trump Jr.", "Donald Trump"),    # wzmianka dłuższa niż etykieta
        ("Ab", "Jan Ab"),
    ])
    def test_rejects_other_people(self, mention, label):
        assert matches_person_name(mention, label) is False


class TestFindDocumentPerson:
    def test_unique_match(self):
        musk = _person(person_id=1, name="Elon Musk")
        trump = _person(person_id=2, name="Donald Trump")
        assert find_document_person("Muska", [musk, trump]) is musk

    def test_ambiguous_surname_returns_none(self):
        donald = _person(person_id=2, name="Donald Trump")
        ivanka = _person(person_id=3, name="Ivanka Trump")
        assert find_document_person("Trump", [donald, ivanka]) is None

    def test_same_person_listed_twice_is_not_ambiguous(self):
        musk = _person(person_id=1, name="Elon Musk")
        assert find_document_person("Musk", [musk, musk]) is musk

    def test_no_match(self):
        assert find_document_person("Tusk", [_person(person_id=1, name="Elon Musk")]) is None


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
    @staticmethod
    def _with_document_people(session, people):
        """Osoby już powiązane z dokumentem (zapytanie session.query(Person).join(...).filter(...).all())."""
        session.query.return_value.join.return_value.filter.return_value.all.return_value = people

    def test_surname_resolves_to_person_already_linked_to_document(self):
        """Doc 11239: "Musk" ma trafić do Elona Muska z tego samego dokumentu, bez Wikidaty i LLM."""
        musk = _person(person_id=106, name="Elon Musk")
        session = _session([_entity("Musk")])
        self._with_document_people(session, [musk])

        with patch("library.wikidata_client.search_persons") as mock_wd, \
                patch("library.article_tagging.confirm_person_with_llm") as mock_llm:
            result = resolve_document_persons(session, _doc(), "tekst")

        mock_wd.assert_not_called()
        mock_llm.assert_not_called()
        assert result["linked"] == [("Musk", "Elon Musk", CONFIDENCE_ALIAS)]
        links = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentPerson)]
        assert [(link.person_id, link.raw_mention) for link in links] == [(106, "Musk")]

    def test_hyphenated_inflected_surname_resolves_to_full_name(self):
        zabdyr = _person(person_id=1354, name="Michał Zabdyr-Jamróz")
        session = _session([_entity("Zabdyra-Jamroza"), _entity("Zabdyr-Jamróz")])
        self._with_document_people(session, [zabdyr])

        with patch("library.wikidata_client.search_persons") as mock_wd:
            result = resolve_document_persons(session, _doc(), "tekst")

        mock_wd.assert_not_called()
        assert {r[1] for r in result["linked"]} == {"Michał Zabdyr-Jamróz"}
        assert len(result["linked"]) == 2

    def test_inflected_two_word_mention_resolves_to_known_person(self):
        """Lemat „Elon muskiem” (z małą literą) to ta sama osoba co „Elon Musk”."""
        musk = _person(person_id=106, name="Elon Musk")
        session = _session([_entity("Elon muskiem")])
        self._with_document_people(session, [musk])

        with patch("library.wikidata_client.search_persons") as mock_wd:
            result = resolve_document_persons(session, _doc(), "tekst")

        mock_wd.assert_not_called()
        assert result["linked"] == [("Elon muskiem", "Elon Musk", CONFIDENCE_ALIAS)]

    def test_ambiguous_surname_falls_back_to_wikidata(self):
        donald = _person(person_id=2, name="Donald Trump")
        ivanka = _person(person_id=3, name="Ivanka Trump")
        session = _session([_entity("Trump")])
        self._with_document_people(session, [donald, ivanka])

        with patch("library.wikidata_client.search_persons", return_value=[]) as mock_wd:
            result = resolve_document_persons(session, _doc(), "tekst")

        mock_wd.assert_called_once_with("Trump")
        assert result["skipped"] == ["Trump"]

    def test_full_names_are_resolved_before_bare_surnames(self):
        """Kolejność wzmianek w bazie nie ma znaczenia: „Musk” przed „Elon Musk” też się łączy."""
        session = _session([_entity("Musk"), _entity("Elon Musk")])
        self._with_document_people(session, [])
        candidates = [{"qid": "Q317521", "label": "Elon Musk", "description": "przedsiębiorca"}]

        with patch("library.wikidata_client.search_persons", return_value=candidates) as mock_wd, \
                patch("library.article_tagging.confirm_person_with_llm", return_value="Q317521") as mock_llm:
            result = resolve_document_persons(session, _doc(), "tekst")

        assert mock_wd.call_count == 1  # tylko pełne imię i nazwisko pyta Wikidatę
        mock_llm.assert_called_once()
        assert result["linked"] == [
            ("Elon Musk", "Elon Musk", CONFIDENCE_WIKIDATA),
            ("Musk", "Elon Musk", CONFIDENCE_ALIAS),
        ]
        created = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Person)]
        assert len(created) == 1

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

    def test_bare_given_name_is_skipped_even_with_wikidata_humans(self):
        """"Pani Ewa": Wikidata zwraca ludzi o imieniu Ewa, ale samo imię nikogo nie identyfikuje."""
        candidates = [
            {"qid": "Q1", "label": "Ewa", "description": "pierwsza kobieta"},
            {"qid": "Q2", "label": "Ewa Kopacz", "description": "polska polityk"},
        ]
        session = _session([_entity("Ewa")])
        with patch("library.wikidata_client.search_persons", return_value=candidates),                 patch("library.article_tagging.confirm_person_with_llm") as llm:
            result = resolve_document_persons(session, _doc(), "tekst")

        llm.assert_not_called()
        assert result["skipped"] == ["Ewa"]
        assert result["linked"] == []

    def test_lone_surname_still_goes_through_wikidata(self):
        session = _session([_entity("Tusk")])
        with patch("library.wikidata_client.search_persons", return_value=TUSK_CANDIDATES),                 patch("library.article_tagging.confirm_person_with_llm", return_value="Q946"):
            result = resolve_document_persons(session, _doc(), "tekst")

        assert result["skipped"] == []
        assert result["linked"][0][1] == "Donald Tusk"

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
