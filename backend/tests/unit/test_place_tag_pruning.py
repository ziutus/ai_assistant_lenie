"""Unit tests for place_verification.prune_unsupported_place_tags() - stale miejsce-* tags (doc #11263).

The text said "Manili", NER later saw "Manila": verify_document_places() only ADDED tags, so miejsce-manili
outlived its entity.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library.db.models import DocumentEntity, GeocodeCache  # noqa: E402
from library.place_verification import prune_unsupported_place_tags, verify_document_places  # noqa: E402


def _geocode(display):
    geo = MagicMock(spec=GeocodeCache)
    geo.resolved = True
    geo.display_name = display
    return geo


def _place(text, display=None, status=None, relevance="central", etype="placeName"):
    return SimpleNamespace(entity_text=text, entity_type=etype, geocode=_geocode(display) if display else None,
                           relevance=relevance, place_verification_status=status, variants=["Manili", "Manilę"])


def _session(entities):
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value.all.return_value = entities
    query.filter.return_value.one_or_none.return_value = None
    cache_query = MagicMock()
    cache_query.filter.return_value.one_or_none.return_value = None
    session.query.side_effect = lambda model: cache_query if model is GeocodeCache else query
    return session


def _mock_entity(text, **kwargs):
    ent = MagicMock(spec=DocumentEntity)
    ent.entity_text = text
    ent.entity_type = "placeName"
    ent.geocode_id = kwargs.get("geocode_id")
    ent.geocode = kwargs.get("geocode")
    ent.mention_count = 2
    ent.source = kwargs.get("source", "ner")
    ent.place_verification_status = kwargs.get("status")
    ent.place_review_reason = None
    ent.variants = kwargs.get("variants", [])
    ent.relevance = "central"
    return ent


def test_variant_spelling_does_not_keep_a_stale_tag():
    doc = MagicMock(tags="geopolityka,miejsce-manili,miejsce-manila,kraj-filipiny")
    stale = prune_unsupported_place_tags(doc, [_place("Manila", "Manila, Capital District, Metro Manila, Filipiny")])
    assert stale == ["miejsce-manili"]
    assert doc.tags == "geopolityka,miejsce-manila,kraj-filipiny"


def test_canonical_geocoder_spelling_supports_a_tag():
    doc = MagicMock(tags="miejsce-kijow")
    assert prune_unsupported_place_tags(doc, [_place("Kijowa", "Kijów, Ukraina")]) == []
    assert doc.tags == "miejsce-kijow"


@pytest.mark.parametrize("kwargs", [
    {"status": "rejected"}, {"status": "needs_review"}, {"relevance": "figurative"}, {"etype": "orgName"},
])
def test_rejected_held_figurative_or_retyped_rows_justify_nothing(kwargs):
    doc = MagicMock(tags="miejsce-huty,kraj-polska")
    assert prune_unsupported_place_tags(doc, [_place("Huty", **kwargs)]) == ["miejsce-huty"]
    assert doc.tags == "kraj-polska"


def test_document_without_place_entities_keeps_its_tags():
    doc = MagicMock(tags="miejsce-manili")
    assert prune_unsupported_place_tags(doc, []) == []
    assert doc.tags == "miejsce-manili"


def test_verify_document_places_prunes_the_stale_tag():
    ent = _mock_entity("Manila", geocode_id=7, source="manual", status="confirmed", variants=["Manili"],
                       geocode=_geocode("Manila, Capital District, Metro Manila, Filipiny"))
    doc = MagicMock(id=11263, title="", tags="miejsce-manili")
    summary = verify_document_places(_session([ent]), doc, "Szczyt w Manili.")
    assert summary == {"checked": 0, "resolved": [], "tagged": []}
    assert doc.tags == "miejsce-manila"


def test_geocoder_outage_prunes_nothing():
    ent = _mock_entity("Kijowa")
    doc = MagicMock(id=1, title="", tags="miejsce-kijow")
    with patch("library.place_verification._get_or_create_geocode", return_value=None):
        verify_document_places(_session([ent]), doc, "Kijowa.")
    assert doc.tags == "miejsce-kijow"
