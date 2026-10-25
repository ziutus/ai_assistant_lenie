"""Entities added by hand from selected text (context menu on /ner/:id) and their replay after a rebuild."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import DocumentEntity  # noqa: E402
from library.entity_overrides import (  # noqa: E402
    ADDABLE_ENTITY_TYPES, add_manual_entity, count_mentions, replay_manual_added_entities,
)


def entity(text, entity_type="placeName", count=1, variants=None, source="ner"):
    return DocumentEntity(
        id=hash((text, entity_type)) % 100000, document_id=1, entity_type=entity_type, entity_text=text,
        mention_count=count, variants=variants or [], source=source,
    )


def decision(entity_text, entity_type="placeName", **details):
    return SimpleNamespace(id=1, decision="entity_added", entity_text=entity_text, entity_type=entity_type, details=details)


def test_count_mentions_is_case_insensitive_and_literal():
    text = "Kaliningradzkiej enklawy... w kaliningradzkiej enklawy (x.y)"
    assert count_mentions(text, "kaliningradzkiej enklawy") == 2
    assert count_mentions(text, "x.y") == 1
    assert count_mentions(text, "a.b") == 0
    assert count_mentions(None, "x") == 0


def test_creates_a_manual_place_row_with_the_surface_as_variant():
    session = MagicMock()
    row, organization = add_manual_entity(
        session, 1, "placeName", "kaliningradzkiej enklawy", "Obwód Kaliningradzki", 2, entities=[])
    assert organization is None
    assert (row.entity_type, row.entity_text, row.mention_count, row.source) == (
        "placeName", "Obwód Kaliningradzki", 2, "manual")
    assert row.variants == ["kaliningradzkiej enklawy"]
    session.add.assert_called_once_with(row)


def test_folds_into_the_same_named_place_of_either_place_type():
    existing = entity("Obwód Kaliningradzki", entity_type="geogName", count=7, variants=["obwód kaliningradzki"])
    session = MagicMock()
    row, _ = add_manual_entity(
        session, 1, "placeName", "kaliningradzkiej enklawy", "Obwód Kaliningradzki", 2, entities=[existing])
    assert row is existing
    assert existing.mention_count == 9
    assert existing.variants == ["obwód kaliningradzki", "kaliningradzkiej enklawy"]
    assert existing.source == "manual"
    session.add.assert_not_called()


def test_a_replay_survivor_is_not_counted_twice():
    existing = entity("Bałtowie", entity_type="persName", count=3, source="manual")
    add_manual_entity(MagicMock(), 1, "persName", "Bałtowie", None, 3, entities=[existing],
                      survivors=frozenset({id(existing)}))
    assert existing.mention_count == 3


def test_replay_readds_a_hand_added_entity_only_when_it_is_missing():
    kept = entity("Litwa", variants=["litewskiej"])
    added = decision("Obwód Kaliningradzki", surface="kaliningradzkiej enklawy", name="Obwód Kaliningradzki", count=2)
    present = decision("Litwa", surface="litewskiej", name="Litwa", count=1)
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[added, present], [kept], []]
    assert replay_manual_added_entities(session, 1) == {"entity_added": 1}
    (created,) = [call.args[0] for call in session.add.call_args_list]
    assert (created.entity_text, created.variants, created.mention_count) == (
        "Obwód Kaliningradzki", ["kaliningradzkiej enklawy"], 2)


def test_replay_does_not_bring_back_an_entity_deleted_after_it_was_added():
    added = SimpleNamespace(id=1, decision="entity_added", entity_text="Szczyt NATO", entity_type="eventName",
                            details={"surface": "szczyt NATO", "name": "Szczyt NATO", "count": 1})
    deleted = SimpleNamespace(id=2, decision="deleted", entity_text="szczyt nato", entity_type="eventName", details=None)
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[added], [], [deleted]]
    assert replay_manual_added_entities(session, 1) == {}
    session.add.assert_not_called()


SOURCE_SENTENCE = (
    "Zełeński naciskał w niedzielę na więcej informacji na temat yyy yyy możliwych ograniczeń dla Starshieldu. "
    "Kijów wykorzystuje Starshielda do zapewnienia łączności swoim dronom."
)  # doc #11137: Starshield (military Starlink) used to be reported as two persons


def test_a_product_is_a_plain_manual_entity_and_folds_its_inflected_forms():
    assert "productName" in ADDABLE_ENTITY_TYPES
    session = MagicMock()
    row, organization = add_manual_entity(
        session, 11137, "productName", "Starshieldu", "Starshield", count_mentions(SOURCE_SENTENCE, "Starshieldu"),
        entities=[])
    assert organization is None
    assert (row.entity_type, row.entity_text, row.source, row.mention_count) == (
        "productName", "Starshield", "manual", 1)
    assert row.variants == ["Starshieldu"]
    session.add.assert_called_once_with(row)

    folded, _ = add_manual_entity(session, 11137, "productName", "Starshielda", "Starshield", 1, entities=[row])
    assert folded is row
    assert row.mention_count == 2
    assert row.variants == ["Starshieldu", "Starshielda"]


def test_replay_readds_a_product_after_the_document_was_reopened():
    added = decision("Starshield", entity_type="productName", surface="Starshieldu", name="Starshield", count=2)
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[added], [], []]
    assert replay_manual_added_entities(session, 11137) == {"entity_added": 1}
    (created,) = [call.args[0] for call in session.add.call_args_list]
    assert (created.entity_type, created.entity_text, created.variants, created.mention_count) == (
        "productName", "Starshield", ["Starshieldu"], 2)


def test_an_event_is_a_plain_manual_entity():
    session = MagicMock()
    row, organization = add_manual_entity(session, 1, "eventName", "szczytu NATO w Hadze", "Szczyt NATO w Hadze", 1, entities=[])
    assert organization is None
    assert (row.entity_type, row.entity_text, row.source) == ("eventName", "Szczyt NATO w Hadze", "manual")
    assert row.variants == ["szczytu NATO w Hadze"]
