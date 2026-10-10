"""Replay of manual place decisions after a document's entities were rebuilt."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import DocumentEntity  # noqa: E402
from library.entity_overrides import apply_decisions, replay_manual_place_decisions  # noqa: E402


def entity(text, entity_type="placeName", count=1, variants=None, source="ner", geocode_id=None):
    return DocumentEntity(
        id=hash((text, entity_type)) % 100000, document_id=1, entity_type=entity_type, entity_text=text,
        mention_count=count, variants=variants or [], source=source, geocode_id=geocode_id,
    )


def decision(kind, entity_text, entity_type="placeName", **details):
    return SimpleNamespace(decision=kind, entity_text=entity_text, entity_type=entity_type, details=details or None)


def run(decisions, entities):
    session = MagicMock()
    touched, stats = apply_decisions(session, decisions, entities)
    return session, touched, stats


def test_rename_is_reapplied_to_fresh_ner_row_and_keeps_old_forms_as_variants():
    row = entity("Jemenu Północnego", count=3, variants=["Jemenu Północnym"])
    entities = [row]

    _, touched, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], entities)

    assert stats == {"renamed": 1, "merged": 0, "deleted": 0}
    assert row.entity_text == "Jemen Północny"
    assert row.source == "manual"
    assert row.geocode_id is None
    assert {"Jemenu Północnego", "Jemenu Północnym", "Jemen Północny"} <= set(row.variants)
    assert list(touched.values()) == [row]


def test_rename_matches_a_surface_variant_of_the_fresh_row():
    row = entity("Jemen Pólnocny", variants=["Jemenu Północnego"])

    _, _, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], [row])

    assert stats["renamed"] == 1
    assert row.entity_text == "Jemen Północny"


def test_rename_into_an_existing_name_merges_instead_of_duplicating():
    old = entity("Jemenu Północnego", count=2)
    existing = entity("Jemen Północny", count=5)
    entities = [old, existing]

    session, touched, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], entities)

    assert stats["renamed"] == 1
    session.delete.assert_called_once_with(old)
    assert entities == [existing]
    assert existing.mention_count == 7
    assert existing.source == "manual"
    assert list(touched.values()) == [existing]


def test_rename_without_a_matching_mention_or_already_applied_is_a_noop():
    already = entity("Jemen Północny", variants=["Jemenu Północnego"], source="manual")
    session, touched, stats = run([
        decision("renamed", "Jemenu Północnego", new_text="Jemen Północny"),
        decision("renamed", "Nigdzie", new_text="Gdzieś"),
    ], [already])

    assert stats == {"renamed": 0, "merged": 0, "deleted": 0}
    assert touched == {}
    session.delete.assert_not_called()


def test_place_merge_folds_source_into_target_and_can_take_an_org_misclassification():
    kijow_org = entity("Kijów", entity_type="orgName", count=2)
    kijow = entity("Kijów", entity_type="geogName", count=4)
    entities = [kijow_org, kijow]

    session, touched, stats = run([
        decision("place_merged", "Kijów", entity_type="geogName",
                 source_entity_text="Kijów", source_entity_type="orgName", target_entity_text="Kijów"),
    ], entities)

    assert stats["merged"] == 1
    session.delete.assert_called_once_with(kijow_org)
    assert kijow.mention_count == 6
    assert kijow.source == "manual"


def test_place_merge_needs_both_sides_to_exist():
    aden = entity("Aden")
    session, _, stats = run([
        decision("place_merged", "Rijad", source_entity_text="Aden", target_entity_text="Rijad"),
    ], [aden])

    assert stats["merged"] == 0
    session.delete.assert_not_called()


def test_deleted_place_stays_deleted_but_only_by_exact_text():
    pilica = entity("Pilica")
    hidden = entity("Inna", variants=["Pilica"])
    entities = [pilica, hidden]

    session, _, stats = run([decision("deleted", "Pilica"), decision("rejected", "Pilica")], entities)

    assert stats["deleted"] == 1
    session.delete.assert_called_once_with(pilica)
    assert entities == [hidden]


def test_decisions_replay_in_order_so_a_later_rename_can_reuse_a_deleted_name():
    pilica = entity("Pilica")
    other = entity("Pilicą")
    entities = [pilica, other]

    _, _, stats = run([
        decision("deleted", "Pilica"),
        decision("renamed", "Pilicą", new_text="Pilica"),
    ], entities)

    assert stats["deleted"] == 1 and stats["renamed"] == 1
    assert [e.entity_text for e in entities] == ["Pilica"]


def test_replay_geocodes_touched_rows_without_geocode_and_swallows_failures():
    row = entity("Jemenu Północnego")
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")]),
        MagicMock(all=lambda: [row]),
    ]
    doc = MagicMock()

    with patch("library.place_verification.geocode_single_place", side_effect=RuntimeError("boom")) as geocode:
        stats = replay_manual_place_decisions(session, 1, doc)

    assert stats["renamed"] == 1
    geocode.assert_called_once_with(session, doc, row)


def test_replay_does_nothing_without_recorded_decisions():
    session = MagicMock()
    session.scalars.return_value = MagicMock(all=lambda: [])

    assert replay_manual_place_decisions(session, 1) == {}
    assert session.scalars.call_count == 1
