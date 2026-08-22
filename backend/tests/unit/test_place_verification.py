"""Unit tests for library/place_verification.py — geocode cache + miejsce-* tagging."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, GeocodeCache  # noqa: E402
from library.place_verification import (  # noqa: E402
    _canonicalize_and_merge_places,
    _get_or_create_geocode,
    _is_country,
    _relabel_alias_hit,
    _retry_after_stripping_country,
    _slugify,
    remove_orphaned_tag,
    verify_document_places,
)


def _entity(text, etype="geogName", geocode_id=None, geocode=None, mention_count=1):
    ent = MagicMock(spec=DocumentEntity)
    ent.entity_text = text
    ent.entity_type = etype
    ent.geocode_id = geocode_id
    ent.geocode = geocode
    ent.mention_count = mention_count
    return ent


def _resolved_geocode(display_name):
    geo = MagicMock(spec=GeocodeCache)
    geo.resolved = True
    geo.display_name = display_name
    return geo


def _session_with_entities(entities, cached_geocode=None):
    session = MagicMock()
    # first query() call -> entities; GeocodeCache lookups -> cached_geocode
    entity_query = MagicMock()
    entity_query.filter.return_value.all.return_value = entities
    cache_query = MagicMock()
    cache_query.filter.return_value.one_or_none.return_value = cached_geocode
    session.query.side_effect = lambda model: cache_query if model is GeocodeCache else entity_query
    return session


class TestSlugify:
    def test_polish_diacritics_and_spaces(self):
        assert _slugify("Cieśnina Ormuz") == "ciesnina-ormuz"
        assert _slugify("Morze Czerwone") == "morze-czerwone"


class TestIsCountry:
    """_is_country() must require the WHOLE entity_text to be a country —
    doc #9394 found "Port Sudan" (contains "Sudan" as a substring) and
    "Al-Faszirze Emiraty" (contains "Emiraty") silently dropped out of the
    geocoding candidate list (verify_document_places() filters is_country
    places out entirely) because the previous implementation used
    country_gazetteer.detect_countries() — a deliberately over-matching
    candidate generator meant for LLM-filtered tag prescreening, not an
    exact-identity check."""

    @pytest.mark.parametrize("name", ["Sudan", "Sudanu", "Iran", "Stany Zjednoczone", "USA"])
    def test_exact_country_name_is_true(self, name):
        assert _is_country(name) is True

    @pytest.mark.parametrize("name", ["Port Sudan", "Port Sudanu", "Al-Faszirze Emiraty", "Cieśnina Ormuz"])
    def test_place_name_merely_containing_a_country_substring_is_false(self, name):
        assert _is_country(name) is False


class TestRelabelAliasHit:
    def test_replaces_leading_segment_with_original_query(self):
        hit = {"display_name": "El Fasher, Sudan Zachodni, Sudan", "lat": "13.6", "lon": "25.3"}
        relabeled = _relabel_alias_hit("Al-Faszir", hit)
        assert relabeled["display_name"] == "Al-Faszir, Sudan Zachodni, Sudan"
        assert relabeled["lat"] == "13.6"  # coordinates untouched

    def test_single_segment_display_name(self):
        hit = {"display_name": "El Fasher"}
        assert _relabel_alias_hit("Al-Faszir", hit)["display_name"] == "Al-Faszir"

    def test_missing_display_name(self):
        assert _relabel_alias_hit("Al-Faszir", {})["display_name"] == "Al-Faszir"


class TestGetOrCreateGeocodeAliasFallback:
    """doc 9394: "Al-Faszir" (Polish "sz") returned an unrelated Cairo alley
    from LocationIQ under its Polish spelling — the city is indexed as
    "El Fasher"/"Al Fashir" in OSM. geocode_aliases.py retries once via the
    English transliteration when the Polish query fails is_plausible_match()."""

    def _session(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = None
        return session

    def test_polish_query_fails_then_alias_succeeds(self):
        session = self._session()
        cairo_alley = {"display_name": "Al Huruqi Alley Alley, Kair, Egipt"}
        sudan_city = {
            "display_name": "El Fasher, Sudan Zachodni, Sudan",
            "lat": "13.6", "lon": "25.3", "class": "place", "type": "city", "importance": 0.4,
        }

        def fake_geocode(query):
            return sudan_city if query == "El Fasher" else cairo_alley

        with patch("library.place_verification.geocode", side_effect=fake_geocode):
            with patch(
                "library.place_verification.is_plausible_match",
                side_effect=lambda q, hit: hit is sudan_city,
            ):
                row = _get_or_create_geocode(session, "Al-Faszir")

        assert row.resolved is True
        # display_name relabeled back to the Polish query, not "El Fasher"
        assert row.display_name == "Al-Faszir, Sudan Zachodni, Sudan"
        assert row.lat == "13.6"

    def test_no_alias_registered_stays_unresolved(self):
        """"Cieśnina Ormuz" has no geocode_aliases entry — behavior unchanged."""
        session = self._session()

        with patch("library.place_verification.geocode",
                   return_value={"display_name": "Płytka Cieśnina, Iława"}) as mock_geocode:
            with patch("library.place_verification.is_plausible_match", return_value=False):
                row = _get_or_create_geocode(session, "Cieśnina Ormuz")

        mock_geocode.assert_called_once_with("Cieśnina Ormuz")  # alias never attempted
        assert row.resolved is False

    def test_successful_polish_query_never_tries_alias(self):
        session = self._session()
        hit = {"display_name": "Al-Faszir, Sudan Zachodni, Sudan"}

        with patch("library.place_verification.geocode", return_value=hit) as mock_geocode:
            with patch("library.place_verification.is_plausible_match", return_value=True):
                row = _get_or_create_geocode(session, "Al-Faszir")

        mock_geocode.assert_called_once_with("Al-Faszir")
        assert row.resolved is True
        assert row.display_name == "Al-Faszir, Sudan Zachodni, Sudan"


class TestRetryAfterStrippingCountry:
    """doc #9394: geogName "Al-Faszirze Emiraty" — NER merged a place with an
    adjacent country mention across a missing comma. The retry strips the
    country, canonicalizes the inflected remainder via city_gazetteer (the
    merged span never went through the normal per-mention canonicalization
    in ner_client.py), and geocodes that instead."""

    def _session(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = None
        return session

    def test_strips_country_canonicalizes_and_resolves_remainder(self):
        session = self._session()
        hit = {
            "display_name": "Al-Faszir, Al Fasher, Darfur Północny, Sudan",
            "lat": "13.6", "lon": "25.3", "class": "place", "type": "city", "importance": 0.4,
        }

        with patch("library.place_verification.geocode", return_value=hit) as mock_geocode:
            with patch("library.place_verification.is_plausible_match", return_value=True):
                result = _retry_after_stripping_country(session, "Al-Faszirze Emiraty")

        assert result is not None
        remainder, row = result
        assert remainder == "Al-Faszir"  # canonicalized via city_gazetteer, not the raw "Al-Faszirze"
        mock_geocode.assert_called_once_with("Al-Faszir")
        assert row.resolved is True

    def test_strips_country_canonicalizes_remainder_via_region_gazetteer(self):
        session = self._session()
        hit = {
            "display_name": "Kordofan Północny, Sudan",
            "lat": "15.0", "lon": "29.99", "class": "boundary", "type": "administrative", "importance": 0.47,
        }

        with patch("library.place_verification.geocode", return_value=hit) as mock_geocode:
            with patch("library.place_verification.is_plausible_match", return_value=True):
                result = _retry_after_stripping_country(session, "Kordofanu Północnego Emiraty")

        assert result is not None
        remainder, row = result
        assert remainder == "Kordofan Północny"  # canonicalized via region_gazetteer
        mock_geocode.assert_called_once_with("Kordofan Północny")
        assert row.resolved is True

    def test_no_country_edge_returns_none(self):
        session = self._session()
        with patch("library.place_verification.geocode") as mock_geocode:
            result = _retry_after_stripping_country(session, "Cieśnina Ormuz")
        mock_geocode.assert_not_called()
        assert result is None

    def test_remainder_still_fails_to_geocode_returns_none(self):
        session = self._session()
        with patch("library.place_verification.geocode", return_value=None):
            result = _retry_after_stripping_country(session, "Nibylandia Emiraty")
        assert result is None


class TestVerifyDocumentPlaces:
    def _doc(self, tags=""):
        doc = MagicMock()
        doc.id = 42
        doc.title = "Tytuł"
        doc.tags = tags
        return doc

    def test_resolved_and_confirmed_place_gets_tag(self):
        ent = _entity("Cieśnina Ormuz")
        session = _session_with_entities([ent])
        # display_name po polsku — geocode() prosi o accept-language=pl
        hit = {"display_name": "Cieśnina Ormuz, Oman", "lat": "26.4", "lon": "56.2",
               "class": "natural", "type": "strait", "importance": 0.6}
        doc = self._doc(tags="geopolityka")

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_verification.geocode", return_value=hit):
                with patch("library.place_verification.is_plausible_match", return_value=True):
                    with patch("library.article_tagging.confirm_places_with_llm",
                               return_value=["Cieśnina Ormuz"]):
                        summary = verify_document_places(session, doc, "tekst artykułu")

        assert summary["resolved"] == ["Cieśnina Ormuz"]
        assert summary["tagged"] == ["miejsce-ciesnina-ormuz"]
        assert doc.tags == "geopolityka,miejsce-ciesnina-ormuz"
        session.add.assert_called_once()  # GeocodeCache row created

    def test_implausible_hit_cached_as_unresolved_no_tag(self):
        ent = _entity("Cieśnina Ormuz")
        session = _session_with_entities([ent])
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_verification.geocode", return_value={"display_name": "Płytka Cieśnina, Iława"}):
                with patch("library.place_verification.is_plausible_match", return_value=False):
                    summary = verify_document_places(session, doc, "tekst")

        assert summary["resolved"] == []
        assert summary["tagged"] == []
        cached = session.add.call_args.args[0]
        assert cached.resolved is False

    def test_merged_span_with_country_is_split_and_resolved(self):
        """doc #9394 regression: geogName "Al-Faszirze Emiraty" (NER merged a
        place with an adjacent country mention across a missing comma) gets
        split, canonicalized to "Al-Faszir" and geocoded, instead of showing
        the garbled span to the reader unresolved."""
        ent = _entity("Al-Faszirze Emiraty")
        session = _session_with_entities([ent])
        doc = self._doc()
        hit = {
            "display_name": "Al-Faszir, Al Fasher, Darfur Północny, Sudan",
            "lat": "13.6", "lon": "25.3", "class": "place", "type": "city", "importance": 0.4,
        }

        def fake_geocode(query):
            return None if query == "Al-Faszirze Emiraty" else hit

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_verification.geocode", side_effect=fake_geocode):
                with patch("library.place_verification.is_plausible_match", return_value=True):
                    with patch("library.article_tagging.confirm_places_with_llm", return_value=["Al-Faszir"]):
                        summary = verify_document_places(session, doc, "tekst")

        assert ent.entity_text == "Al-Faszir"
        assert summary["resolved"] == ["Al-Faszir"]
        assert summary["tagged"] == ["miejsce-al-faszir"]

    def test_countries_are_skipped_entirely(self):
        ent = _entity("Ukraina", etype="placeName")
        session = _session_with_entities([ent])
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=True):
            with patch("library.place_verification.geocode") as mock_geocode:
                summary = verify_document_places(session, doc, "tekst")

        mock_geocode.assert_not_called()
        assert summary == {"checked": 0, "resolved": [], "tagged": []}

    def test_cached_query_not_geocoded_again(self):
        cached = _resolved_geocode("Kijów, Ukraina")
        cached.id = 7
        ent = _entity("Kijów", etype="placeName")
        session = _session_with_entities([ent], cached_geocode=cached)
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_verification.geocode") as mock_geocode:
                with patch("library.article_tagging.confirm_places_with_llm", return_value=[]):
                    summary = verify_document_places(session, doc, "tekst")

        mock_geocode.assert_not_called()
        assert summary["resolved"] == ["Kijów"]
        assert summary["tagged"] == []  # LLM nie potwierdził istotności

    def test_llm_rejection_leaves_tags_untouched(self):
        ent = _entity("Kijów", geocode_id=7, geocode=_resolved_geocode("Kijów, Ukraina"))
        session = _session_with_entities([ent])
        doc = self._doc(tags="geopolityka")

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm", return_value=[]):
                verify_document_places(session, doc, "tekst")

        assert doc.tags == "geopolityka"

    def test_frequent_mention_auto_confirmed_without_llm(self):
        """Miejsce wspomniane >=3 razy jest jawnie omawiane — tag bez wywołania LLM."""
        ent = _entity("Teheran", geocode_id=7, geocode=_resolved_geocode("Teheran, Iran"), mention_count=5)
        session = _session_with_entities([ent])
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm") as mock_llm:
                summary = verify_document_places(session, doc, "tekst")

        mock_llm.assert_not_called()
        assert summary["tagged"] == ["miejsce-teheran"]

    def test_duplicate_tag_not_added_twice(self):
        ent = _entity("Kijów", geocode_id=7, geocode=_resolved_geocode("Kijów, Ukraina"))
        session = _session_with_entities([ent])
        doc = self._doc(tags="miejsce-kijow")

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm", return_value=["Kijów"]):
                summary = verify_document_places(session, doc, "tekst")

        assert summary["tagged"] == []
        assert doc.tags == "miejsce-kijow"

    def test_inflected_variants_produce_one_tag(self):
        """Regresja na realny przypadek (doc 9216): "Kijów" i "Kijowa" dawały miejsce-kijow + miejsce-kijowa.

        Odmieniona forma geokoduje się nawet do innego obiektu OSM (wieś Kijów
        pod Otmuchowem), ale kanoniczna pisownia obu trafień slugu je scala.
        """
        ents = [
            _entity("Kijów", geocode_id=7, geocode=_resolved_geocode("Kijow, Ukraina")),
            _entity("Kijowa", geocode_id=8, geocode=_resolved_geocode("Kijów, gmina Otmuchów, Polska")),
        ]
        session = _session_with_entities(ents)
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm",
                       return_value=["Kijów", "Kijowa"]):
                summary = verify_document_places(session, doc, "tekst")

        assert summary["tagged"] == ["miejsce-kijow"]
        assert doc.tags == "miejsce-kijow"

    def test_mention_counts_merged_before_auto_confirm(self):
        """Warianty tej samej nazwy sumują wzmianki — razem przekraczają próg auto-confirm bez LLM."""
        ents = [
            _entity("Grenlandia", geocode_id=7, geocode=_resolved_geocode("Grenlandia"), mention_count=2),
            _entity("Grenlandią", geocode_id=8, geocode=_resolved_geocode("Grenlandia"), mention_count=2),
        ]
        session = _session_with_entities(ents)
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm") as mock_llm:
                summary = verify_document_places(session, doc, "tekst")

        mock_llm.assert_not_called()
        assert summary["tagged"] == ["miejsce-grenlandia"]

    def test_context_classifier_blocks_auto_confirm_for_non_place_mention(self):
        """Regresja doc 9267: "Pilica" (mention_count=3) przekracza AUTO_CONFIRM_MENTIONS,
        ale mowa o systemie "Wisła-Narew-Pilica" — kontekstowy klasyfikator musi
        to złapać ZANIM próg auto-confirm w ogóle zdecyduje o tagu."""
        ent = _entity("Pilica", geocode_id=393, geocode=_resolved_geocode("Pilica, Polska"), mention_count=3)
        session = _session_with_entities([ent])
        doc = self._doc()

        not_place_result = [{
            "key": "Pilica", "entity_text": "Pilica", "context": "system Wisła-Narew-Pilica",
            "predicted_class": "not_place", "confidence": "high",
            "rationale": "Część nazwy systemu.", "model": "Bielik", "dropped": True,
        }]
        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_context_classifier.classify_place_context_candidates",
                       return_value=not_place_result):
                with patch("library.article_tagging.confirm_places_with_llm") as mock_llm:
                    summary = verify_document_places(session, doc, "system Wisła-Narew-Pilica")

        mock_llm.assert_not_called()  # mention_count=3 would've hit AUTO_CONFIRM_MENTIONS either way
        assert summary["tagged"] == []  # but the context classifier drops it before that check runs
        assert doc.tags == ""

    def test_context_classifier_result_persisted_as_audit_row(self):
        ent = _entity("Kijów", geocode_id=7, geocode=_resolved_geocode("Kijów, Ukraina"))
        session = _session_with_entities([ent])
        doc = self._doc()

        confirmed_result = [{
            "key": "Kijów", "entity_text": "Kijów", "context": "stolica Ukrainy",
            "predicted_class": "place", "confidence": "high",
            "rationale": "Mowa o mieście.", "model": "Bielik", "dropped": False,
        }]
        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.place_context_classifier.classify_place_context_candidates",
                       return_value=confirmed_result):
                with patch("library.article_tagging.confirm_places_with_llm", return_value=["Kijów"]):
                    verify_document_places(session, doc, "stolica Ukrainy")

        added = [
            call.args[0] for call in session.add_all.call_args_list
            if call.args[0] and type(call.args[0][0]).__name__ == "NerContextClassification"
        ]
        assert len(added) == 1
        assert added[0][0].entity_type == "placeName"
        assert added[0][0].dropped is False

    def test_tag_built_from_canonical_spelling(self):
        """Ucięta wzmianka ("Ankar") dostaje tag z pełnej nazwy geokodera, nie z formy z tekstu."""
        geo = _resolved_geocode("Ankara, Çankaya, Ankara, Central Anatolia Region, Turcja")
        ent = _entity("Ankar", geocode_id=7, geocode=geo, mention_count=3)
        session = _session_with_entities([ent])
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            summary = verify_document_places(session, doc, "tekst")

        assert summary["tagged"] == ["miejsce-ankara"]


class TestCanonicalizeAndMergePlaces:
    """Faza 3 (tmp/plan-ner-multiword-place-display-names.md): rename
    entity_text to the geocoder's canonical spelling and physically merge
    document_entities rows that converge on the same canonical place —
    closing the gap left by ner_client.py's text-only nominative preference
    (no nominative anywhere in the text; two entities lemmatized apart)."""

    def _session(self):
        session = MagicMock()
        return session

    def test_two_entities_with_same_canonical_name_are_merged(self):
        """'Port Sudan' (placeName) and 'Port Sudanem' (geogName) never
        shared a lemma-based group (ner_client.py Faza 1 doesn't touch the
        grouping key) but resolve to the same real place via the geocoder."""
        higher = _entity("Port Sudan", etype="placeName",
                          geocode=_resolved_geocode("Port Sudan, Sudan"), mention_count=1)
        higher.variants = ["Port Sudanu"]
        lower = _entity("Port Sudanem", etype="geogName",
                         geocode=_resolved_geocode("Port Sudan, Sudan"), mention_count=1)
        lower.variants = ["Port Sudanem"]
        session = self._session()

        survivors = _canonicalize_and_merge_places(session, [higher, lower])

        assert survivors == [higher]
        assert higher.entity_text == "Port Sudan"
        assert higher.mention_count == 2
        assert higher.source == "geocoded"
        assert set(higher.variants) == {"Port Sudanu", "Port Sudanem"}
        session.delete.assert_called_once_with(lower)

    def test_entity_already_spelled_canonically_anchors_the_merge(self):
        """A row already spelled exactly like the canonical form is kept as
        the merge target — e.g. ner_client.py's Faza 1 already got the
        nominative right from the text, so the geocoder pass must not
        silently prefer the OTHER (mis-lemmatized) duplicate instead."""
        correct = _entity("Morze Czerwone", etype="placeName",
                           geocode=_resolved_geocode("Morze Czerwone, Egipt"), mention_count=1)
        correct.variants = ["Morze Czerwone"]
        garbled = _entity("Morze czerwony", etype="geogName",
                           geocode=_resolved_geocode("Morze Czerwone, Egipt"), mention_count=5)
        garbled.variants = ["Morza Czerwonego"]
        session = self._session()

        survivors = _canonicalize_and_merge_places(session, [garbled, correct])

        assert survivors == [correct]
        assert correct.entity_text == "Morze Czerwone"
        assert correct.mention_count == 6
        session.delete.assert_called_once_with(garbled)

    def test_no_nominative_anywhere_in_text_gets_renamed_to_canonical(self):
        """'Zatoki Perskiej' — every mention genitive, no nominative form in
        the text at all — ner_client.py's Faza 1 cannot fix this (it
        deliberately never generates a nominative from grammar rules); the
        geocoder's canonical spelling is the only way to recover 'Zatoka
        Perska'."""
        ent = _entity("Zatoki Perskiej", etype="geogName",
                       geocode=_resolved_geocode("Zatoka Perska"), mention_count=4)
        ent.variants = ["Zatoki Perskiej"]
        session = self._session()

        survivors = _canonicalize_and_merge_places(session, [ent])

        assert survivors == [ent]
        assert ent.entity_text == "Zatoka Perska"
        assert ent.source == "geocoded"
        session.delete.assert_not_called()

    def test_unresolved_entities_are_left_untouched(self):
        ent = _entity("Nibylandia", geocode=MagicMock(resolved=False))
        session = self._session()

        survivors = _canonicalize_and_merge_places(session, [ent])

        assert survivors == [ent]
        assert ent.entity_text == "Nibylandia"
        session.delete.assert_not_called()
        session.flush.assert_not_called()

    def test_single_resolved_entity_matching_canonical_is_a_noop(self):
        ent = _entity("Teheran", geocode=_resolved_geocode("Teheran, Iran"))
        session = self._session()

        survivors = _canonicalize_and_merge_places(session, [ent])

        assert survivors == [ent]
        assert ent.entity_text == "Teheran"
        session.delete.assert_not_called()


class TestRemoveOrphanedTag:
    """DELETE /website_entities/<id> (server.py) — doc 9267 "Pilica" regression:
    deleting the entity used to leave a stale miejsce-pilica tag behind."""

    def _doc(self, tags=""):
        doc = MagicMock()
        doc.id = 9267
        doc.tags = tags
        return doc

    def _session(self, remaining):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = remaining
        return session

    def test_removes_tag_when_last_supporting_entity_deleted(self):
        deleted = _entity("Pilica", geocode_id=393, geocode=_resolved_geocode("Pilica, Polska"))
        deleted.id = 8518
        session = self._session([])
        doc = self._doc(tags="miejsce-pilica,miejsce-wisla")

        removed = remove_orphaned_tag(session, doc, deleted)

        assert removed == "miejsce-pilica"
        assert doc.tags == "miejsce-wisla"

    def test_keeps_tag_when_another_entity_shares_canonical_place(self):
        deleted = _entity("Kijów", geocode_id=7, geocode=_resolved_geocode("Kijów, Ukraina"))
        deleted.id = 1
        survivor = _entity("Kijowa", geocode_id=8, geocode=_resolved_geocode("Kijów, Ukraina"))
        session = self._session([survivor])
        doc = self._doc(tags="miejsce-kijow")

        removed = remove_orphaned_tag(session, doc, deleted)

        assert removed is None
        assert doc.tags == "miejsce-kijow"

    def test_noop_when_entity_never_had_a_tag(self):
        deleted = _entity("Warszawa", geocode_id=1, geocode=_resolved_geocode("Warszawa, Polska"))
        deleted.id = 1
        session = self._session([])
        doc = self._doc(tags="miejsce-pilica")

        removed = remove_orphaned_tag(session, doc, deleted)

        assert removed is None
        assert doc.tags == "miejsce-pilica"

    def test_noop_for_unresolved_geocode(self):
        deleted = _entity("Nibylandia", geocode_id=1, geocode=MagicMock(resolved=False))
        deleted.id = 1
        session = self._session([])
        doc = self._doc(tags="miejsce-nibylandia")

        removed = remove_orphaned_tag(session, doc, deleted)

        assert removed is None
        assert doc.tags == "miejsce-nibylandia"

    def test_noop_for_non_place_entity_type(self):
        deleted = _entity("MON", etype="orgName")
        deleted.id = 1
        session = self._session([])
        doc = self._doc(tags="miejsce-mon")

        removed = remove_orphaned_tag(session, doc, deleted)

        assert removed is None
        assert doc.tags == "miejsce-mon"
