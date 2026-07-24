"""Unit tests for library/place_verification.py — geocode cache + miejsce-* tagging."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, GeocodeCache  # noqa: E402
from library.place_verification import _slugify, remove_orphaned_tag, verify_document_places  # noqa: E402


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
