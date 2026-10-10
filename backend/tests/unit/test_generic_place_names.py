"""Generic-name guards and reconciliation without database or network access."""

from unittest.mock import MagicMock, patch

import pytest

from library.db.models import Document, DocumentEntity, GeocodeCache
from library.generic_place_names import match_generic_place_name
from library.place_verification import add_place_tag, verify_document_places
from imports.reconcile_generic_place_tags import reconcile_document


@pytest.mark.parametrize("name", ["Huty", "Huti", "Huta", "Południe", "poludnie", " HUTY "])
def test_exact_generic_forms(name):
    assert match_generic_place_name(name, []) is not None


@pytest.mark.parametrize("name", ["Nowa Huta", "Biegun Południowy", "Huta Katowice", "Kosti", "Sahel", "Wisła"])
def test_compound_and_other_names_are_not_generic(name):
    assert match_generic_place_name(name, [name], name) is None


def test_variants_and_geocoder_name_are_checked():
    assert match_generic_place_name("inna", ["Huty"]) is not None
    assert match_generic_place_name("inna", [], "Południe") is not None


def place(name="Huty", count=1, status=None):
    return DocumentEntity(
        id=1, document_id=10753, entity_type="placeName", entity_text=name, variants=[name],
        source="ner", mention_count=count, place_verification_status=status,
        geocode_id=7, geocode=GeocodeCache(id=7, query="Huti", resolved=True,
                                         display_name="Huti, Ukraina", lat=49, lon=24),
    )


@pytest.mark.parametrize("count", [1, 3, 4])
@pytest.mark.parametrize("name", ["Huty", "Huti", "Południe"])
def test_generic_stays_visible_without_rename_merge_or_tag_despite_llm(count, name):
    entity = place(name, count)
    doc = Document(id=10753, title="Test", tags="topic")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [entity]
    with patch("library.place_context_classifier.classify_place_context_candidates", return_value=[{
        "key": name, "predicted_class": "place", "confidence": "high", "dropped": False,
    }]) as classify, patch("library.article_tagging.confirm_places_with_llm", return_value=[name]) as confirm:
        result = verify_document_places(session, doc, name)
    assert entity.place_verification_status == "needs_review"
    assert entity.entity_text == name
    assert entity.variants == [name]
    assert entity.mention_count == count
    assert result["tagged"] == []
    assert doc.tags == "topic"
    session.delete.assert_not_called()
    classify.assert_not_called()
    confirm.assert_not_called()


def test_confirmed_generic_is_tagged_without_llm():
    entity = place(status="confirmed")
    entity.source = "manual"
    doc = Document(id=10753, tags="topic")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [entity]
    verify_document_places(session, doc, "Huty")
    assert doc.tags == "topic,miejsce-huti"
    assert entity.place_verification_status == "confirmed"


def test_manual_rename_does_not_bypass_an_existing_review_requirement():
    entity = place(status="needs_review")
    entity.source = "manual"
    doc = Document(id=10753, tags="topic")
    assert add_place_tag(doc, entity) is None
    assert doc.tags == "topic"


@pytest.mark.parametrize("supported", [False, True])
def test_reconciliation_only_removes_unsupported_tag(supported):
    entity = place()
    other = place(status="confirmed")
    other.id = 2
    doc = Document(id=10753, tags="topic,miejsce-huti")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [entity, other] if supported else [entity]
    reconcile_document(session, doc)
    assert entity.place_verification_status == "needs_review"
    assert entity.geocode.resolved is True
    assert ("miejsce-huti" in doc.tags) is supported
    session.commit.assert_not_called()
