"""Unit tests for imports/backfill_organizations.py — apply_entity_merge() ordering.

Regression test for the delete-before-rename fix: renaming the surviving
row before deleting its duplicates could collide with
unique(document_id, entity_type, entity_text) when the canonical name
already belongs to another row in the same document (the "Interia" +
"Interii" reference case, docs/organization-ner-alias-plan.md).
"""

import os
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

os.environ.setdefault("SECRETS_BACKEND", "env")

from imports.backfill_organizations import apply_entity_merge  # noqa: E402


class _FakeEntity:
    """Minimal DocumentEntity stand-in that records writes to entity_text,
    so the test can assert *when* the rename happens relative to deletes."""

    def __init__(self, entity_id, entity_text, mention_count, variants, events):
        self.id = entity_id
        self._entity_text = entity_text
        self.mention_count = mention_count
        self.variants = variants
        self._events = events

    @property
    def entity_text(self):
        return self._entity_text

    @entity_text.setter
    def entity_text(self, value):
        self._events.append(("rename", self.id, value))
        self._entity_text = value


def _make_session(entities_by_id, events):
    session = MagicMock()
    session.get.side_effect = lambda _model, entity_id: entities_by_id.get(entity_id)

    def _delete(entity):
        events.append(("delete", entity.id))
        entities_by_id.pop(entity.id, None)

    session.delete.side_effect = _delete
    session.query.return_value.filter.return_value.first.return_value = None
    return session


def test_deletes_duplicates_before_renaming_survivor():
    """Interia/Interii reference case: the surviving row's rename target
    ("Interia") already belongs to a duplicate row in this document.
    Renaming first would hit the unique constraint while the duplicate
    still exists — duplicates must be deleted (and flushed) first."""
    events: list[tuple] = []
    surviving = _FakeEntity(1, "Interii", 2, ["Interii"], events)
    duplicate = _FakeEntity(2, "Interia", 2, [], events)
    session = _make_session({1: surviving, 2: duplicate}, events)

    plan = {
        "document_id": 9267,
        "organization_id": 5,
        "canonical_name": "Interia",
        "surviving_entity_id": 1,
        "duplicate_entity_ids": [2],
        "new_mention_count": 4,
        "new_variants": ["Interii"],
        "link_exists": False,
    }

    apply_entity_merge(session, plan)

    assert events == [("delete", 2), ("rename", 1, "Interia")]
    assert surviving.entity_text == "Interia"
    assert surviving.mention_count == 4
    session.add.assert_called_once()


def test_no_duplicates_just_renames_and_links():
    events: list[tuple] = []
    surviving = _FakeEntity(1, "Bloomberg", 3, [], events)
    session = _make_session({1: surviving}, events)

    plan = {
        "document_id": 42,
        "organization_id": 7,
        "canonical_name": "Bloomberg",
        "surviving_entity_id": 1,
        "duplicate_entity_ids": [],
        "new_mention_count": 3,
        "new_variants": [],
        "link_exists": False,
    }

    apply_entity_merge(session, plan)

    assert events == [("rename", 1, "Bloomberg")]
    session.delete.assert_not_called()
    session.add.assert_called_once()
