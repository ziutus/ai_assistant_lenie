"""Unit tests for library/entity_service.py — document_entities persistence layer."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, NerExclusion  # noqa: E402
from library.entity_service import (  # noqa: E402
    _add_place_mentions,
    _temporal_candidate_rows,
    filter_entities_to_text,
    get_document_entities,
    is_excluded,
    merge_document_entities,
    refresh_document_entities,
)


RAW = [
    {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
    {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
    {"text": "Kotlinie Kłodzkiej", "label": "geogName", "lemma": "kotlina kłodzki"},
]


def _session_with_exclusions(exclusions):
    session = MagicMock()
    # refresh_document_entities issues several SELECTs.  Only the
    # ner_exclusions query should return the supplied exclusion rows; derived
    # entity/organization queries are empty in these unit tests.
    def execute(statement, *_args, **_kwargs):
        result = MagicMock()
        rows = exclusions if "ner_exclusions" in str(statement) else []
        result.scalars.return_value.all.return_value = rows
        return result
    session.execute.side_effect = execute
    session.get.return_value = MagicMock(byline=None)
    return session


class TestRegistryNameExtensions:
    @pytest.mark.parametrize("protected", [None, "manual", "excluded"])
    def test_refresh_detects_events_and_honors_existing_protections(self, protected):
        exclusion = MagicMock(entity_text="afera Watergate", entity_type="eventName", scope="global")
        session = _session_with_exclusions([exclusion] if protected == "excluded" else [])
        session.query.return_value.filter.return_value.all.return_value = (
            [MagicMock(entity_type="eventName", entity_text="afera Watergate", variants=[])]
            if protected == "manual" else []
        )
        with patch("library.entity_service.extract_entities", return_value=[
            {"text": "Watergate", "lemma": "Watergate", "label": "placeName"},
        ]):
            rows = refresh_document_entities(session, 42, "aferą Watergate")
        events = [row for row in rows if row.entity_type == "eventName"]
        assert len(events) == (0 if protected else 1)
        if events:
            assert events[0].entity_text == "afera Watergate"
            assert events[0].variants == ["aferą Watergate"]

    def test_unmatched_registry_phrase_leaves_groups_unchanged(self):
        from copy import deepcopy

        from library.entity_service import _extend_places_to_registry_names

        groups = {("placeName", "Cambridge"): {"count": 1, "variants": [], "raw_lemmas": []}}
        before = deepcopy(groups)
        with patch("library.organization_registry.find_organization_by_phrase", return_value=None):
            _extend_places_to_registry_names(MagicMock(), groups, "Cambridge Unknown", [
                {"text": "Cambridge", "label": "placeName", "start": 0, "end": 9},
            ])
        assert groups == before

    @pytest.mark.parametrize("suffix,canonical", [
        ("Analitica", "Cambridge Analytica"), ("University", "Cambridge University"),
    ])
    @pytest.mark.parametrize("count", [1, 3])
    def test_place_extension(self, suffix, canonical, count):
        from library.entity_service import _extend_places_to_registry_names

        text = f"(afera Cambridge {suffix})"
        start = text.index("Cambridge")
        groups = {("placeName", "cambridge"): {"count": count, "variants": ["Cambridge"], "raw_lemmas": []}}
        raw = [{"text": "Cambridge", "lemma": "cambridge", "label": "placeName",
                "start": start, "end": start + len("Cambridge")}]
        with patch("library.organization_registry.find_organization_by_phrase",
                   return_value=MagicMock(canonical_name=canonical)) as lookup:
            _extend_places_to_registry_names(MagicMock(), groups, text, raw)
        lookup.assert_called_once()
        assert groups[("orgName", canonical)] == {
            "count": 1, "variants": [f"Cambridge {suffix}"] if suffix == "Analitica" else [],
            "raw_lemmas": [canonical],
        }
        if count == 1:
            assert ("placeName", "cambridge") not in groups
        else:
            assert groups[("placeName", "cambridge")]["count"] == 2

    @pytest.mark.parametrize("text", ["w Cambridge w Anglii", "Cambridge. University", "Cambridge  University"])
    def test_no_extension_across_lowercase_punctuation_or_extra_space(self, text):
        from copy import deepcopy

        from library.entity_service import _extend_places_to_registry_names

        groups = {("placeName", "Cambridge"): {"count": 1, "variants": [], "raw_lemmas": []}}
        before = deepcopy(groups)
        start = text.index("Cambridge")
        with patch("library.organization_registry.find_organization_by_phrase") as lookup:
            _extend_places_to_registry_names(MagicMock(), groups, text, [
                {"text": "Cambridge", "label": "placeName", "start": start, "end": start + 9},
            ])
        assert groups == before
        lookup.assert_not_called()

    def test_longest_first_and_failure_after_success_is_atomic(self):
        from copy import deepcopy

        from library.entity_service import _extend_places_to_registry_names

        text = "Cambridge Alpha Beta; Cambridge University"
        groups = {("geogName", "Cambridge"): {"count": 2, "variants": [], "raw_lemmas": []}}
        before = deepcopy(groups)
        raw = [{"text": "Cambridge", "label": "geogName", "start": start, "end": start + 9}
               for start in (0, text.rindex("Cambridge"))]
        with patch("library.organization_registry.find_organization_by_phrase", side_effect=[
            None, MagicMock(canonical_name="Cambridge Alpha"), RuntimeError("offline"),
        ]) as lookup:
            _extend_places_to_registry_names(MagicMock(), groups, text, raw)
        assert [call.args[1] for call in lookup.call_args_list] == [
            "Cambridge Alpha Beta", "Cambridge Alpha", "Cambridge University",
        ]
        assert groups == before

    def test_named_events_merge_and_fail_open(self):
        from copy import deepcopy

        from library.entity_service import _add_named_events

        groups = {("eventName", "afera Watergate"): {
            "count": 1, "variants": ["Afera Watergate"], "raw_lemmas": ["afera Watergate"],
        }}
        _add_named_events(MagicMock(), groups, "aferą Watergate")
        assert groups[("eventName", "afera Watergate")]["count"] == 2
        assert groups[("eventName", "afera Watergate")]["variants"] == ["Afera Watergate", "aferą Watergate"]
        before = deepcopy(groups)
        with patch("library.organization_registry.find_organization_by_phrase", side_effect=RuntimeError("offline")):
            _add_named_events(MagicMock(), groups, "afera Watergate, afera Cambridge Analitica")
        assert groups == before


class TestRefreshDocumentEntities:
    def test_temporal_candidates_keep_type_position_and_context(self):
        text = "Wstęp. 17 września 1939 rozpoczęła się wojna o godzinie 4:45."
        raw = [
            {"text": "17 września 1939", "label": "date", "lemma": "17 wrzesień 1939"},
            {"text": "4:45", "label": "time", "lemma": "4:45"},
        ]

        rows = _temporal_candidate_rows(42, text, raw)

        assert [(row.entity_type, row.raw_text) for row in rows] == [
            ("date", "17 września 1939"),
            ("time", "4:45"),
        ]
        assert rows[0].char_start == text.index("17 września 1939")
        assert "rozpoczęła się wojna" in rows[0].context_excerpt

    def test_compact_dates_replace_split_ner_candidates(self):
        text = "Od 06.04 do 08.04 trwały testy. W środę 09.04 wystrzelono pociski."
        raw = [
            {"text": "06.", "label": "date", "lemma": "06."},
            {"text": "04", "label": "time", "lemma": "04"},
            {"text": "08.", "label": "date", "lemma": "08."},
            {"text": "04", "label": "time", "lemma": "04"},
            {"text": "09.", "label": "date", "lemma": "09."},
            {"text": "04", "label": "date", "lemma": "04"},
        ]

        rows = _temporal_candidate_rows(42, text, raw)

        assert [(row.entity_type, row.raw_text) for row in rows] == [
            ("date", "06.04"),
            ("date", "08.04"),
            ("date", "09.04"),
        ]

    def test_replaces_rows_with_aggregated_entities(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        # advisory lock + SELECT exclusions + replace temporal candidates +
        # SELECT ner_corrections + replace entities + replace
        # document_organizations + facility refresh
        assert session.execute.call_count == 7
        lock_query = session.execute.call_args_list[0].args[0]
        assert "pg_advisory_xact_lock" in str(lock_query.compile(dialect=postgresql.dialect()))
        assert session.add_all.call_args_list[0].args[0] == rows
        # No recognised facility in RAW; the refresh still replaces its
        # derived links with an empty set.
        assert session.add_all.call_args_list[1].args[0] == []
        assert {(r.entity_type, r.entity_text, r.mention_count) for r in rows} == {
            ("persName", "Tusk", 2),
            ("geogName", "kotlina kłodzki", 1),
        }
        assert all(isinstance(r, DocumentEntity) and r.document_id == 42 for r in rows)
        # formy powierzchniowe z tekstu zapisane per wiersz (filtr per rozdział)
        assert {r.entity_text: r.variants for r in rows} == {
            "Tusk": ["Tuska", "Tusk"],
            "kotlina kłodzki": ["Kotlinie Kłodzkiej"],
        }

    def test_rows_sorted_most_mentioned_first(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert rows[0].entity_text == "Tusk"

    def test_genuinely_empty_extraction_keeps_existing_rows(self):
        """Empty extraction with the service reachable must not touch document_entities."""
        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=[]), \
             patch("library.entity_service.is_available", return_value=True):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert rows == []
        session.add_all.assert_not_called()
        session.commit.assert_called_once()  # clears any stale ner_unavailable_at

    def test_service_unavailable_raises_and_flags_document_without_touching_rows(self):
        """Empty extraction with the service down must raise, not silently return []."""
        from library.ner_client import NERServiceUnavailable

        session = MagicMock()
        with patch("library.entity_service.extract_entities", return_value=[]), \
             patch("library.entity_service.is_available", return_value=False):
            with pytest.raises(NERServiceUnavailable):
                refresh_document_entities(session, 42, "jakiś tekst")

        session.add_all.assert_not_called()
        session.commit.assert_called_once()  # sets ner_unavailable_at, own transaction

    def test_global_exclusion_drops_entity(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="tusk", entity_type="persName", scope="global")]
        )
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert {r.entity_text for r in rows} == {"kotlina kłodzki"}

    def test_exclusion_matches_raw_variant_after_country_canonicalization(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="Turcy", entity_type="placeName", scope="global")]
        )
        raw = [{"text": "Turcy", "label": "placeName", "lemma": "Turk", "pos": "NOUN"}]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "Turcy")
        assert rows == []

    def test_exclusion_matches_raw_lemma_after_country_canonicalization(self):
        session = _session_with_exclusions(
            [NerExclusion(entity_text="Turk", entity_type="placeName", scope="global")]
        )
        raw = [{"text": "Turcy", "label": "placeName", "lemma": "Turk", "pos": "NOUN"}]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "Turcy")
        assert rows == []

    @pytest.mark.parametrize("excluded_term", ["Amerykanin", "Amerykanie", "USA", "Stany Zjednoczone"])
    @pytest.mark.parametrize("country_mentions", [True, False])
    def test_doc_11237_demonym_exclusion_preserves_country(self, excluded_term, country_mentions):
        # Source sentences from doc #11237; spaCy mangles the inflected country lemma.
        text = (
            "No więc aby ograniczyć to zagrożenie, Stany Zjednoczone i inne mocarstwa "
            "zawarły w 2015 roku porozumienie. ...zdani na łaskę Stanów Zjednoczonych... "
            "USA. Amerykanie ... Amerykanów ..."
        )
        mentions = [("Amerykanie", "Amerykanin"), ("Amerykanów", "Amerykanin")]
        if country_mentions:
            mentions = [
                ("Stany Zjednoczone", "Stany Zjednoczone"),
                ("Stanów Zjednoczonych", "Stany zjednoczyć"),
                ("USA", "USA"),
            ] + mentions
        raw = [{"text": surface, "lemma": lemma, "label": "placeName", "pos": "PROPN"}
               for surface, lemma in mentions]
        session = _session_with_exclusions([
            NerExclusion(entity_text=excluded_term, entity_type="placeName", scope="global"),
        ])
        with patch("library.entity_service.extract_entities", return_value=raw), \
             patch("library.ner_corrections.apply_ner_corrections") as corrections:
            rows = refresh_document_entities(session, 11237, text)

        if excluded_term == "Stany Zjednoczone" or (excluded_term == "USA" and country_mentions):
            assert rows == []
        elif excluded_term == "Amerykanin" and not country_mentions:
            assert rows == []
        else:
            assert len(rows) == 1
            row = rows[0]
            assert (row.entity_type, row.entity_text) == ("placeName", "Stany Zjednoczone")
            remaining = [(surface, lemma) for surface, lemma in mentions
                         if excluded_term not in (surface, lemma)]
            assert row.mention_count == len(remaining)
            assert row.variants == [surface for surface, _ in remaining]
            group = corrections.call_args.args[2][("placeName", "Stany Zjednoczone")]
            assert set(group["raw_lemmas"]) == {lemma for _, lemma in remaining}

    def test_author_exclusion_applies_only_to_matching_author(self):
        exclusions = [NerExclusion(entity_text="Tusk", entity_type="*", scope="author",
                                   author="Good Times Bad Times")]
        session = _session_with_exclusions(exclusions)
        session.get.return_value = MagicMock(byline="Good Times Bad Times")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows = refresh_document_entities(session, 42, "jakiś tekst")
        assert {r.entity_text for r in rows} == {"kotlina kłodzki"}

        session2 = _session_with_exclusions(exclusions)
        session2.get.return_value = MagicMock(byline="Inny Kanał")
        with patch("library.entity_service.extract_entities", return_value=RAW):
            rows2 = refresh_document_entities(session2, 42, "jakiś tekst")
        assert {r.entity_text for r in rows2} == {"Tusk", "kotlina kłodzki"}

    def test_manual_row_survives_and_colliding_ner_group_is_dropped(self):
        """A merged (source='manual') place must survive a refresh untouched;
        a fresh NER group matching it by entity_text OR a stored variant is
        skipped instead of re-inserted (would violate the unique constraint
        or duplicate the merged name)."""
        manual_row = DocumentEntity(
            document_id=42, entity_type="placeName", entity_text="Kijów",
            mention_count=5, variants=["Kijowa"], source="manual",
        )
        session = _session_with_exclusions([])
        session.query.return_value.filter.return_value.all.return_value = [manual_row]
        raw = [
            {"text": "Kijowa", "label": "placeName", "lemma": "Kijów"},
            {"text": "Charków", "label": "placeName", "lemma": "Charków"},
        ]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert {r.entity_text for r in rows} == {"Charków"}
        assert manual_row.mention_count == 5
        assert manual_row.variants == ["Kijowa"]

    def test_manual_row_of_different_type_does_not_block_non_colliding_group(self):
        """A manual row only blocks groups of the same entity_type."""
        manual_row = DocumentEntity(
            document_id=42, entity_type="orgName", entity_text="Kijów",
            mention_count=1, variants=[], source="manual",
        )
        session = _session_with_exclusions([])
        session.query.return_value.filter.return_value.all.return_value = [manual_row]
        raw = [{"text": "Kijów", "label": "placeName", "lemma": "Kijów"}]
        with patch("library.entity_service.extract_entities", return_value=raw):
            rows = refresh_document_entities(session, 42, "jakiś tekst")

        assert {(r.entity_type, r.entity_text) for r in rows} == {("placeName", "Kijów")}


    def test_high_confidence_context_verdict_drops_false_person_and_records_it(self):
        session = _session_with_exclusions([])
        raw = [{"text": "Pocisków", "label": "persName", "lemma": "Pocisków"}]
        verdict = {
            "key": ("persName", "Pocisków"),
            "entity_text": "Pocisków",
            "context": "dostawy pocisków artyleryjskich",
            "predicted_class": "not_person",
            "confidence": "high",
            "rationale": "Rodzaj amunicji.",
            "model": "Bielik-11B-v3.0-Instruct",
            "dropped": True,
        }
        with patch("library.entity_service.extract_entities", return_value=raw), patch(
            "library.person_context_classifier.classify_single_word_person_candidates",
            return_value=[verdict],
        ):
            rows = refresh_document_entities(
                session, 42, "Rozpoczęto dostawy pocisków artyleryjskich."
            )

        assert rows == []
        classification_rows = session.add_all.call_args_list[0].args[0]
        assert len(classification_rows) == 1
        assert classification_rows[0].entity_text == "Pocisków"
        assert classification_rows[0].dropped is True


class TestChannelGlossaryInRefresh:
    """Doc #10872: one channel's mis-heard names are repaired in the text sent to NER."""

    @staticmethod
    def _session(rows):
        session = MagicMock()

        def execute(statement, *_args, **_kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = rows if "ner_channel_glossary" in str(statement) else []
            return result

        session.execute.side_effect = execute
        session.get.return_value = MagicMock(byline="Na Wschód od Bliskiego Wschodu")
        return session

    def test_ner_sees_the_repaired_text_and_variants_keep_the_original_spellings(self):
        from library.db.models import NerChannelGlossaryEntry

        entry = NerChannelGlossaryEntry(id=5, author="Na Wschód od Bliskiego Wschodu",
                                        canonical_name="Pete Hegseth", aliases=["He H"], fuzzy=True)
        session = self._session([entry])
        sent = {}

        def fake_extract(text):
            sent["text"] = text
            return [{"text": "Hegseth", "label": "persName", "lemma": "Hegseth"},
                    {"text": "Hegseth", "label": "persName", "lemma": "Hegseth"}]

        with patch("library.entity_service.extract_entities", side_effect=fake_extract), patch(
            "library.person_context_classifier.classify_single_word_person_candidates", return_value=[],
        ):
            rows = refresh_document_entities(session, 10872, "Hekset mówił. Potem Hexeta odpowiedział.")

        assert sent["text"] == "Hegseth mówił. Potem Hegseth odpowiedział."
        person = next(row for row in rows if row.entity_type == "persName")
        assert person.entity_text == "Hegseth"
        assert {"Hegseth", "Hekset", "Hexeta"} <= set(person.variants)
        applications = [a for call in session.add_all.call_args_list for a in call.args[0]
                        if type(a).__name__ == "NerGlossaryApplication"]
        assert {(a.original_text, a.replacement_text, a.glossary_id) for a in applications} == {
            ("Hekset", "Hegseth", 5), ("Hexeta", "Hegseth", 5)}

    def test_document_without_channel_never_queries_the_glossary(self):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=RAW):
            refresh_document_entities(session, 42, "Hekset")
        assert not any("ner_channel_glossary" in str(call.args[0]) for call in session.execute.call_args_list)


class TestPlaceMentionSupplement:
    """Gazetteer-detected places that spaCy never reports (doc #10872)."""

    def test_merges_into_the_existing_place_group_and_creates_new_ones(self):
        text = "Kaliningradu, czyli królewca. Obwód kaliningradzki i obwodu kaliningradzkiego. Przez przesmyk suwalski."
        raw = [{"text": "Kaliningradu", "label": "placeName", "lemma": "Kaliningrad"}]
        groups = {("placeName", "Kaliningrad"): {"count": 1, "variants": ["Kaliningradu"], "raw_lemmas": ["Kaliningrad"]}}
        _add_place_mentions(groups, text, raw)
        assert groups[("placeName", "Kaliningrad")] == {
            "count": 2, "variants": ["Kaliningradu", "królewca"], "raw_lemmas": ["Kaliningrad"],
        }
        assert groups[("placeName", "Obwód Kaliningradzki")]["count"] == 2
        assert groups[("placeName", "Przesmyk Suwalski")] == {
            "count": 1, "variants": ["przesmyk suwalski"], "raw_lemmas": ["Przesmyk Suwalski"],
        }

    def test_existing_geog_name_group_is_reused_instead_of_duplicated(self):
        groups = {("geogName", "Przesmyk Suwalski"): {"count": 1, "variants": ["Przesmyk Suwalski"]}}
        _add_place_mentions(groups, "Przesmyku Suwalskiego broni NATO", [])
        assert list(groups) == [("geogName", "Przesmyk Suwalski")]
        assert groups[("geogName", "Przesmyk Suwalski")]["count"] == 2

    def test_text_without_gazetteer_places_changes_nothing(self):
        groups = {("placeName", "Warszawa"): {"count": 1, "variants": ["Warszawie"]}}
        _add_place_mentions(groups, "Mieszkam w Warszawie.", [])
        assert groups == {("placeName", "Warszawa"): {"count": 1, "variants": ["Warszawie"]}}


class TestOrganizationMerging:
    """docs/organization-ner-alias-plan.md reference case: doc 9267, Interia/Interii."""

    @pytest.mark.parametrize("excluded", [False, True])
    def test_compound_org_merge_precedes_exclusions_and_corrections(self, excluded):
        head = "Agencja Unii Europejskiej"
        tail = "Bezpieczeństwa Lotniczego"
        canonical = f"{head} ds. {tail} (EASA)"
        raw = [{"text": name, "label": "orgName", "lemma": name} for name in (head, tail, "EASA")]
        exclusions = [NerExclusion(entity_text=tail, entity_type="orgName", scope="global")] if excluded else []
        session = _session_with_exclusions(exclusions)
        fake_org = MagicMock(id=7, canonical_name=canonical)

        def check_corrections(_session, _document_id, groups, _author):
            assert set(groups) == (set() if excluded else {("orgName", canonical)})
            return []

        with patch("library.entity_service.extract_entities", return_value=raw), \
             patch("library.entity_service.resolve_or_create",
                   return_value=(fake_org, "canonical_matched")) as resolve, \
             patch("library.ner_corrections.apply_ner_corrections", side_effect=check_corrections):
            rows = refresh_document_entities(
                session, 10770, f"**{head}** [link8] ds. **{tail}** (EASA)",
            )

        if excluded:
            assert rows == []
            resolve.assert_not_called()
        else:
            assert [(row.entity_text, row.mention_count) for row in rows] == [(canonical, 1)]
            resolve.assert_called_once()
            assert resolve.call_args.args[1] == canonical
            assert "EASA" in resolve.call_args.args[2]

    def test_merges_orgname_lemma_split_and_creates_document_organization(self):
        session = _session_with_exclusions([])
        raw = [
            {"text": "Interii", "label": "orgName", "lemma": "Interia"},
            {"text": "Interią", "label": "orgName", "lemma": "Interia"},
            {"text": "Interii", "label": "orgName", "lemma": "Interii"},
            {"text": "Interii", "label": "orgName", "lemma": "Interii"},
        ]
        fake_org = MagicMock(id=7, canonical_name="Interia")
        with patch("library.entity_service.extract_entities", return_value=raw), \
             patch("library.entity_service.resolve_or_create",
                   return_value=(fake_org, "canonical_matched")) as mock_resolve:
            rows = refresh_document_entities(session, 42, "tekst")

        assert len(rows) == 1
        assert rows[0].entity_text == "Interia"
        assert rows[0].mention_count == 4
        assert set(rows[0].variants) == {"Interii", "Interią"}

        # merge_ner_groups picked the richer-variant group's name before registry resolution
        mock_resolve.assert_called_once()
        called_name, called_variants = mock_resolve.call_args.args[1], mock_resolve.call_args.args[2]
        assert called_name == "Interia"
        assert set(called_variants) == {"Interii", "Interią"}

        added_orgs = [
            call.args[0] for call in session.add.call_args_list
            if type(call.args[0]).__name__ == "DocumentOrganization"
        ]
        assert len(added_orgs) == 1
        assert added_orgs[0].document_id == 42
        assert added_orgs[0].organization_id == 7
        assert added_orgs[0].confidence == "canonical_matched"
        assert added_orgs[0].document_entity_id == rows[0].id


class TestAmbiguousOrganizationNames:
    """A bare institution name with several curated meanings ("Kongres", "Senat") is settled by the
    document context, and left unresolved when the context does not settle it."""

    RAW = [
        {"text": "Kongresie", "label": "orgName", "lemma": "Kongresie"},
        {"text": "Kongresu", "label": "orgName", "lemma": "Kongresie"},
        {"text": "Kongres", "label": "orgName", "lemma": "Kongresie"},
    ]
    CANDIDATES = [MagicMock(id=1), MagicMock(id=2)]

    def _refresh(self, chosen):
        session = _session_with_exclusions([])
        with patch("library.entity_service.extract_entities", return_value=self.RAW), \
             patch("library.entity_service.ambiguous_alias_candidates_for_forms",
                   return_value=("Kongres", self.CANDIDATES)) as lookup, \
             patch("library.entity_service.select_ambiguous_alias_candidate_with_llm",
                   return_value=chosen) as select, \
             patch("library.entity_service.resolve_or_create") as resolve:
            rows = refresh_document_entities(session, 11237, "Kongres, Kongresie, Kongresu")
        return session, rows, lookup, select, resolve

    def test_lookup_covers_the_group_name_and_every_variant(self):
        _session, _rows, lookup, select, _resolve = self._refresh(None)

        forms = lookup.call_args.args[1]
        assert forms[0] == "Kongresie"
        assert {"Kongresu", "Kongres"} <= set(forms)
        assert select.call_args.args[2] == "Kongres"

    def test_context_choice_links_the_chosen_organization(self):
        us = MagicMock(id=55, canonical_name="Kongres Stanów Zjednoczonych")

        session, rows, _lookup, _select, resolve = self._refresh(us)

        assert [row.entity_text for row in rows] == ["Kongres Stanów Zjednoczonych"]
        resolve.assert_not_called()
        links = [c.args[0] for c in session.add.call_args_list if type(c.args[0]).__name__ == "DocumentOrganization"]
        assert [(link.organization_id, link.confidence) for link in links] == [(55, "context_llm_matched")]

    def test_no_choice_leaves_the_mention_unresolved_without_a_global_alias_or_new_organization(self):
        session, rows, _lookup, _select, resolve = self._refresh(None)

        resolve.assert_not_called()
        assert [row.entity_text for row in rows] == ["Kongresie"]
        assert rows[0].mention_count >= 1
        assert not [c for c in session.add.call_args_list if type(c.args[0]).__name__ == "DocumentOrganization"]


class TestMergeDocumentEntities:
    """POST /document/<id>/places/merge (server.py) — per-document only, no cross-document registry."""

    def test_sums_mention_count_and_unions_variants(self):
        source = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Amerykanin",
            mention_count=1, variants=["Amerykanie"],
        )
        target = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Amerykanów",
            mention_count=1, variants=["Amerykanów"],
        )
        merge_document_entities(source, target)
        assert target.mention_count == 2
        assert set(target.variants) == {"Amerykanów", "Amerykanie", "Amerykanin"}
        assert target.source == "manual"

    def test_target_adopts_missing_geocode_from_source(self):
        """The Kijów case: orgName mention (no geocode) merged into the placeName mention."""
        source = DocumentEntity(
            document_id=9267, entity_type="orgName", entity_text="Kijów",
            mention_count=1, variants=[], geocode_id=8,
        )
        target = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Kijów",
            mention_count=2, variants=["Kijów"], geocode_id=None,
        )
        merge_document_entities(source, target)
        assert target.geocode_id == 8
        assert target.source == "manual"

    def test_target_geocode_is_never_overwritten(self):
        source = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Kijowa",
            mention_count=1, variants=[], geocode_id=99,
        )
        target = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Kijów",
            mention_count=1, variants=[], geocode_id=8,
        )
        merge_document_entities(source, target)
        assert target.geocode_id == 8
        assert target.source == "manual"

    def test_source_text_not_duplicated_as_variant_when_same_casefold(self):
        source = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="kijów", mention_count=1, variants=[],
        )
        target = DocumentEntity(
            document_id=9267, entity_type="placeName", entity_text="Kijów", mention_count=1, variants=[],
        )
        merge_document_entities(source, target)
        assert target.variants == []
        assert target.source == "manual"


class TestIsExcluded:
    def test_case_insensitive_text_match(self):
        rules = [NerExclusion(entity_text="starling", entity_type="persName", scope="global")]
        assert is_excluded(rules, "persName", "Starling", None) is True

    def test_wildcard_type_matches_all_types(self):
        rules = [NerExclusion(entity_text="Taliban", entity_type="*", scope="global")]
        assert is_excluded(rules, "persName", "Taliban", None) is True
        assert is_excluded(rules, "geogName", "Taliban", None) is True

    def test_specific_type_does_not_match_other_types(self):
        rules = [NerExclusion(entity_text="Taliban", entity_type="persName", scope="global")]
        assert is_excluded(rules, "geogName", "Taliban", None) is False

    def test_place_types_are_equivalent_after_label_merging(self):
        rules = [NerExclusion(entity_text="Ukraina", entity_type="geogName", scope="global")]
        assert is_excluded(rules, "placeName", "Ukraina", None) is True

    def test_document_scope_applies_only_to_its_document(self):
        rules = [NerExclusion(entity_text="Ewa", entity_type="persName", scope="document", document_id=11184)]
        assert is_excluded(rules, "persName", "Ewa", None, document_id=11184) is True
        assert is_excluded(rules, "persName", "Ewa", None, document_id=1) is False
        assert is_excluded(rules, "persName", "Ewa", None) is False

    def test_author_scope_needs_author(self):
        rules = [NerExclusion(entity_text="Starlinek", entity_type="persName",
                              scope="author", author="Kanał X")]
        assert is_excluded(rules, "persName", "Starlinek", None) is False
        assert is_excluded(rules, "persName", "Starlinek", "kanał x") is True
        assert is_excluded(rules, "persName", "Starlinek", "Inny") is False

    def test_matches_raw_terms(self):
        rules = [NerExclusion(entity_text="Turcy", entity_type="placeName", scope="global")]
        assert is_excluded(rules, "placeName", "Turcja", None, raw_terms=["Turk", "Turcy"]) is True

    def test_generic_common_noun_capitalized_at_sentence_start(self):
        """doc #9394, rozdział 2: "Lotnisko w Chartumie wciąż nie obsługuje
        regularnie lotów międzynarodowych." spaCy złapało samo "Lotnisko"
        (duże "L" z początku zdania, nie właściwa nazwa) jako geogName;
        LocationIQ trafił w niepowiązane, ale realnie istniejące miejsce o
        tej samej nazwie ("Lotnisko, Bemowo, Warszawa") i confirm_places_
        with_llm nie mógł wyłapać niedopasowania, bo widzi tylko tekst
        powierzchniowy, nie rozstrzygniętą tożsamość miejsca. Chartum ma już
        własną, poprawnie zgeokodowaną encję w tym samym dokumencie — ten sam
        wzorzec co "kraj"/"unia"/"Teza" (rzeczowniki pospolite z początku
        zdania) w istniejących regułach ner_exclusions."""
        rules = [NerExclusion(entity_text="Lotnisko", entity_type="*", scope="global")]
        assert is_excluded(rules, "geogName", "Lotnisko", None) is True

    def test_orphaned_arabic_prefix_from_split_person_name(self):
        """doc #9394, rozdział 4: "...cieszyli się przychylnością Omara
        al-Baszira, dyktatora Sudanu..." spaCy rozbiło "al-Baszira" na
        persName "Baszir" (poprawnie dopasowany do Omara al-Baszira w
        rejestrze osób) i osierocony fragment arabskiego przedimka "Al-"
        otagowany jako placeName — prawdopodobnie zasugerowany modelowi
        przez sąsiednie "Al-Faszir"/"Al-Ubajid" w tym samym dokumencie.
        geocode_cache poprawnie odrzucił dopasowanie (LocationIQ trafił w
        niepowiązaną Albanię, ale próg dopasowania to odfiltrował) — problem
        jest wcześniej, w samej ekstrakcji NER, nie w geokodowaniu."""
        rules = [NerExclusion(entity_text="Al-", entity_type="placeName", scope="global")]
        assert is_excluded(rules, "placeName", "Al-", None) is True


class TestGetDocumentEntities:
    @pytest.mark.parametrize("source", ["ner", "manual"])
    @pytest.mark.parametrize("linked", [False, True])
    def test_event_related_organizations(self, source, linked):
        event = self._event_row("afera Lodz Analytica")
        event.source = source
        org = self._event_row("ŁÓDŹ Analytica")
        org.entity_type, org.id = "orgName", 78
        session = self._event_session([event, org, self._event_row("afera Watergate")], [])
        link = MagicMock(document_entity_id=78, organization_id=1239)
        link.organization.links = []
        session.scalars.side_effect = lambda statement: MagicMock(**{
            "all.return_value": [link] if linked and "document_organizations" in str(statement) else [],
        })
        events = get_document_entities(session, 42)["eventName"]
        expected = {"text": "ŁÓDŹ Analytica"}
        if linked:
            expected["organization_id"] = 1239
        assert events[0]["related_organizations"] == [expected]
        assert "related_organizations" not in events[1]

    def test_needs_review_exposes_proposal_without_accepted_coordinates(self):
        from library.db.models import DocumentEntity, GeocodeCache
        row = DocumentEntity(id=7, entity_type="placeName", entity_text="Huty", mention_count=4,
                             variants=["Huty"], place_verification_status="needs_review",
                             place_review_reason="generic_huty")
        row.geocode = GeocodeCache(id=9, query="Huti", resolved=True, lat=49, lon=24, display_name="Huti, Ukraina")
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]
        item = get_document_entities(session, 10753)["placeName"][0]
        assert item["verified"] is False
        assert item["proposed_display_name"] == "Huti, Ukraina"
        assert item["proposed_geocode_id"] == 9
        assert item["place_review_reason"] == "generic_huty"
        assert "lat" not in item and "lon" not in item and "display_name" not in item

    def test_filters_facility_by_alias_used_in_chapter(self):
        grouped = filter_entities_to_text({
            "facility": [{
                "id": 5,
                "text": "Elektrownia jądrowa Gravelines",
                "count": 3,
                "variants": ["elektrownia Gravelines", "elektrowni Gravelines"],
                "facility_description": "Elektrownia jądrowa we Francji.",
            }],
        }, "Co powiedział EDF o bezpieczeństwie elektrowni Gravelines?")

        assert grouped["facility"] == [{
            "id": 5,
            "text": "Elektrownia jądrowa Gravelines",
            "count": 1,
            "variants": ["elektrownia Gravelines", "elektrowni Gravelines"],
            "facility_description": "Elektrownia jądrowa we Francji.",
            "chapter_variants": ["elektrowni Gravelines"],
        }]

    def test_groups_by_type(self):
        row1 = MagicMock(id=1, entity_type="persName", entity_text="Tusk", mention_count=2, geocode=None,
                         relevance="central", place_verification_status=None, place_review_reason=None,
                         variants=["Tuska", "Tusk"])
        row2 = MagicMock(id=2, entity_type="geogName", entity_text="kotlina kłodzki", mention_count=1, geocode=None,
                         relevance="central", place_verification_status=None, place_review_reason=None,
                         variants=["Kotlinie Kłodzkiej"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row1, row2]

        grouped = get_document_entities(session, 42)

        assert grouped == {
            "persName": [{"id": 1, "text": "Tusk", "count": 2, "relevance": "central", "variants": ["Tuska", "Tusk"]}],
            "orgName": [],
            "geogName": [{"id": 2, "text": "kotlina kłodzki", "count": 1, "variants": ["Kotlinie Kłodzkiej"],
                          "is_country": False, "relevance": "central",
                          "place_verification_status": None, "place_review_reason": None}],
            "placeName": [],
            "facility": [],
            "eventName": [],
            "productName": [],
        }

    @staticmethod
    def _event_session(rows, links):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
        session.execute.return_value.all.return_value = links
        return session

    @staticmethod
    def _event_row(text, variants=()):
        return MagicMock(id=77, entity_type="eventName", entity_text=text, mention_count=1, geocode=None,
                         relevance="central", place_verification_status=None, place_review_reason=None,
                         variants=list(variants), description=None)

    def test_event_name_carries_the_registry_event_it_is_linked_to_in_this_document(self):
        link = MagicMock(name_key="konwencja demokratów", surface="Konwencja Demokratów")
        event = MagicMock(id=68, title="Krajowa Konwencja Demokratów 2024 (Chicago)", status="confirmed")
        session = self._event_session([self._event_row("Konwencja Demokratów")], [(link, event)])

        item = get_document_entities(session, 11237)["eventName"][0]

        assert item["registry_event"] == {
            "id": 68, "title": "Krajowa Konwencja Demokratów 2024 (Chicago)", "status": "confirmed",
            "surface": "Konwencja Demokratów"}

    def test_event_name_is_matched_to_its_link_through_a_spelling_variant(self):
        link = MagicMock(name_key="konwencja demokratów", surface="Konwencja Demokratów")
        event = MagicMock(id=68, title="Krajowa Konwencja Demokratów 2024 (Chicago)", status="proposed")
        session = self._event_session([self._event_row("Konwencja", ["Konwencji  Demokratów", "Konwencja Demokratów"])],
                                      [(link, event)])

        assert get_document_entities(session, 11237)["eventName"][0]["registry_event"]["id"] == 68

    def test_unlinked_event_name_has_no_registry_event(self):
        session = self._event_session([self._event_row("Szczyt NATO")], [])

        assert get_document_entities(session, 11237)["eventName"][0]["registry_event"] is None

    def test_groups_organization_without_geocoding_fields(self):
        row = MagicMock(
            id=4, entity_type="orgName", entity_text="Bloomberg",
            mention_count=1, geocode=None,
            relevance="central", place_verification_status=None, place_review_reason=None, variants=["Bloomberg"],
        )
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["orgName"] == [{
            "id": 4, "text": "Bloomberg", "count": 1, "relevance": "central",
            "variants": ["Bloomberg"], "is_country": False,
        }]
        assert grouped["geogName"] == []
        assert grouped["placeName"] == []

    def test_verified_place_carries_geocode_fields(self):
        geo = MagicMock(resolved=True, lat=50.45, lon=30.52, display_name="Kyiv, Ukraine")
        row = MagicMock(id=3, entity_type="placeName", entity_text="Kijów", mention_count=3, geocode=geo,
                        relevance="central", place_verification_status=None, place_review_reason=None,
                        variants=["Kijowa"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["placeName"] == [{
            "id": 3, "text": "Kijów", "count": 3, "variants": ["Kijowa"], "place_verification_status": None,
            "relevance": "central", "place_review_reason": None, "is_country": False, "verified": True,
            "lat": 50.45, "lon": 30.52, "display_name": "Kyiv, Ukraine",
        }]

    def test_unresolved_place_marked_not_verified(self):
        geo = MagicMock(resolved=False)
        row = MagicMock(id=4, entity_type="geogName", entity_text="Jagami", mention_count=1, geocode=geo,
                        relevance="central", place_verification_status=None, place_review_reason=None,
                        variants=[])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["geogName"] == [{"id": 4, "text": "Jagami", "count": 1, "variants": [],
                                        "place_verification_status": None,
                                        "relevance": "central", "place_review_reason": None,
                                        "is_country": False, "verified": False}]

    def test_country_substring_in_a_place_name_is_not_flagged_as_country(self):
        """doc #9394: "Port Sudan" contains "Sudan" but is a city, not the
        country — is_country must require the whole entity_text to BE a
        country (canonical_country_name), not merely contain one
        (detect_countries() over-matched this and silently dropped "Port
        Sudan" out of place_verification.py's geocoding candidates)."""
        row = MagicMock(id=5, entity_type="placeName", entity_text="Port Sudan", mention_count=2, geocode=None,
                         relevance="central", place_verification_status=None, place_review_reason=None,
                        variants=["Port Sudanu"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["placeName"] == [{
            "id": 5, "text": "Port Sudan", "count": 2, "variants": ["Port Sudanu"], "is_country": False,
            "relevance": "central", "place_verification_status": None, "place_review_reason": None,
        }]

    def test_actual_country_name_is_flagged_as_country(self):
        row = MagicMock(id=6, entity_type="placeName", entity_text="Sudan", mention_count=13, geocode=None,
                         relevance="central", place_verification_status=None, place_review_reason=None,
                        variants=["Sudanie", "Sudanu"])
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [row]

        grouped = get_document_entities(session, 42)

        assert grouped["placeName"] == [{
            "id": 6, "text": "Sudan", "count": 13, "variants": ["Sudanie", "Sudanu"], "is_country": True,
            "relevance": "central", "place_verification_status": None, "place_review_reason": None,
        }]

    def test_empty_document_returns_all_type_keys(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert get_document_entities(session, 42) == {
            "persName": [], "orgName": [], "geogName": [], "placeName": [], "facility": [], "eventName": [],
            "productName": [],
        }


def test_refresh_replays_relevance_on_replacement_rows():
    from library.db.models import EntityReviewDecision

    session = _session_with_exclusions([])
    saved = EntityReviewDecision(id=10, document_id=42, entity_type="persName", entity_text="TUSKA",
                                 decision="relevance_set", details={"relevance": "related", "variants": []})

    def scalars(statement):
        result = MagicMock()
        sql = str(statement)
        if "entity_review_decisions" in sql:
            result.all.return_value = [saved] if statement.compile().params.get("decision_1") == "relevance_set" else []
        elif "FROM document_entities" in sql:
            result.all.return_value = [
                row for call in session.add_all.call_args_list for row in call.args[0]
                if isinstance(row, DocumentEntity)
            ]
        else:
            result.all.return_value = []
        return result

    session.scalars.side_effect = scalars
    with patch("library.entity_service.extract_entities", return_value=RAW), patch(
        "library.person_context_classifier.classify_single_word_person_candidates", return_value=[],
    ):
        rows = refresh_document_entities(session, 42, "Tusk mówił o Kotlinie Kłodzkiej.")
    person = next(row for row in rows if row.entity_type == "persName")
    assert person.relevance == "related"
    assert person.source != "manual"


class TestApplyChannelGlossaryText:
    """Channel euphemisms resolved for country detection ("państwo z gwiazdką" = Izrael)."""

    def test_euphemism_becomes_the_country_name_on_a_copy(self):
        from library.country_gazetteer import detect_countries
        from library.db.models import NerChannelGlossaryEntry
        from library.entity_service import apply_channel_glossary_text

        entry = NerChannelGlossaryEntry(id=7, author="Na Wschód od Bliskiego Wschodu", canonical_name="Izrael",
                                        aliases=["państwo z gwiazdką", "państwem z gwiazdką"], fuzzy=False)
        session = MagicMock()
        session.get.return_value = MagicMock(byline="Na Wschód od Bliskiego Wschodu")
        session.execute.return_value.scalars.return_value.all.return_value = [entry]
        text = "Rozmowy z państwem z gwiazdką trwają, a państwo z gwiazdką atakuje."

        result = apply_channel_glossary_text(session, 10872, text)

        assert result == "Rozmowy z Izrael trwają, a Izrael atakuje."
        assert [c.name_pl for c in detect_countries(text)] == []
        assert [c.name_pl for c in detect_countries(result)] == ["Izrael"]

    def test_document_without_channel_returns_text_unchanged(self):
        from library.entity_service import apply_channel_glossary_text

        session = MagicMock()
        session.get.return_value = MagicMock(byline=None)
        assert apply_channel_glossary_text(session, 1, "tekst") == "tekst"

    def test_database_failure_returns_text_unchanged(self):
        from library.entity_service import apply_channel_glossary_text

        session = MagicMock()
        session.get.side_effect = RuntimeError("db down")
        assert apply_channel_glossary_text(session, 1, "tekst") == "tekst"
