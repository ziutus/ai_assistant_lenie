"""Unit tests for imports.refresh_entities repair planning and safety."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from imports.refresh_entities import build_canonical_map, classify_entity_changes, repair_document
from library.ner_client import NERExtractionError


def _row(text, entity_type="placeName", variants=None, count=1, geocode_id=None):
    return SimpleNamespace(
        entity_text=text,
        entity_type=entity_type,
        variants=variants or [],
        mention_count=count,
        geocode_id=geocode_id,
    )


def _group(count, variants, raw_lemmas=None):
    return {"count": count, "variants": variants, "raw_lemmas": raw_lemmas or []}


def test_build_canonical_map_uses_variants_and_raw_lemmas():
    old = [_row("Turk", variants=["Turcy"]), _row("polska", variants=["Polska"])]
    new = {
        ("placeName", "Turcja"): _group(2, ["Turcy"], ["Turk"]),
        ("geogName", "Polska"): _group(3, ["Polska"], ["polska"]),
    }
    assert build_canonical_map(old, new) == {"Turk": "Turcja", "polska": "Polska"}


def test_classify_removed_merged_changed_and_counts():
    old = [_row("Polska", count=1), _row("polska", count=2), _row("A.", count=1)]
    new = {("placeName", "Polska"): _group(3, ["Polska"])}
    mapping = {"Polska": "Polska", "polska": "Polska"}
    result = classify_entity_changes(old, new, mapping)
    assert result["removed"] == ["A."]
    assert result["removed_count"] == 1
    assert result["changed"] == [("polska", "Polska")]
    assert result["changed_count"] == 1
    assert result["merged"] == ["Polska"]
    assert result["merged_count"] == 1
    assert result["count_changes"] == [("Polska", 1, 3), ("polska", 2, 3)]


def test_ambiguous_mapping_is_left_unmapped_for_safe_removal():
    old = [_row("Kijowa", variants=["Kijowa"])]
    new = {
        ("placeName", "Kijów"): _group(1, ["Kijowa"]),
        ("placeName", "Kijowa Dolnego"): _group(1, ["Kijowa"]),
    }
    assert build_canonical_map(old, new) == {}


def test_ner_failure_does_not_start_database_replacement():
    session = MagicMock()
    doc = SimpleNamespace(id=9204, text_md="tekst", text=None, tags=None, author=None)
    with patch("imports.refresh_entities.extract_entities_strict", side_effect=NERExtractionError("window 2")):
        with pytest.raises(NERExtractionError):
            repair_document(session, doc, dry_run=False)
    session.execute.assert_not_called()
    session.add_all.assert_not_called()
