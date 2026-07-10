"""Unit tests for library/place_verification.py — geocode cache + miejsce-* tagging."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, GeocodeCache  # noqa: E402
from library.place_verification import _slugify, verify_document_places  # noqa: E402


def _entity(text, etype="geogName", geocode_id=None, geocode=None, mention_count=1):
    ent = MagicMock(spec=DocumentEntity)
    ent.entity_text = text
    ent.entity_type = etype
    ent.geocode_id = geocode_id
    ent.geocode = geocode
    ent.mention_count = mention_count
    return ent


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
        hit = {"display_name": "Strait of Hormuz, Oman", "lat": "26.4", "lon": "56.2",
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
        cached = MagicMock(spec=GeocodeCache)
        cached.resolved = True
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
        geo = MagicMock(spec=GeocodeCache)
        geo.resolved = True
        ent = _entity("Kijów", geocode_id=7, geocode=geo)
        session = _session_with_entities([ent])
        doc = self._doc(tags="geopolityka")

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm", return_value=[]):
                verify_document_places(session, doc, "tekst")

        assert doc.tags == "geopolityka"

    def test_frequent_mention_auto_confirmed_without_llm(self):
        """Miejsce wspomniane >=3 razy jest jawnie omawiane — tag bez wywołania LLM."""
        geo = MagicMock(spec=GeocodeCache)
        geo.resolved = True
        ent = _entity("Teheran", geocode_id=7, geocode=geo, mention_count=5)
        session = _session_with_entities([ent])
        doc = self._doc()

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm") as mock_llm:
                summary = verify_document_places(session, doc, "tekst")

        mock_llm.assert_not_called()
        assert summary["tagged"] == ["miejsce-teheran"]

    def test_duplicate_tag_not_added_twice(self):
        geo = MagicMock(spec=GeocodeCache)
        geo.resolved = True
        ent = _entity("Kijów", geocode_id=7, geocode=geo)
        session = _session_with_entities([ent])
        doc = self._doc(tags="miejsce-kijow")

        with patch("library.place_verification._is_country", return_value=False):
            with patch("library.article_tagging.confirm_places_with_llm", return_value=["Kijów"]):
                summary = verify_document_places(session, doc, "tekst")

        assert summary["tagged"] == []
        assert doc.tags == "miejsce-kijow"
