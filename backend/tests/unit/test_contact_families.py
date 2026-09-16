from unittest.mock import MagicMock

import pytest

from library.contact_families import create_family
from library.db.models import Contact, ContactPhoto, ContactFamilyCreation, ContactGroup, ContactRelationship


@pytest.fixture
def family():
    parent_group = ContactGroup(id=17, name="Rodzice")
    children_group = ContactGroup(id=18, name="Grupa przedszkolna")
    root = Contact(id=493, first_name="Anna", last_name="Przykładowa", category_id=1,
                   photo_storage_key="photo.png", photo_thumbnail_storage_key="old-shared-thumb.jpg", groups=[parent_group])
    peer = Contact(id=10, first_name="Filip", category_id=1)
    photo = ContactPhoto(storage_key="photo.png", user_description="Bliźnięta.", ai_descriptions={})
    session = MagicMock()
    rows = []
    def get(model, key, **kwargs):
        if model is Contact:
            return {493: root, 10: peer}.get(key)
        if model is ContactPhoto:
            return photo if key == photo.storage_key else None
        if model is ContactGroup:
            return children_group if key == 18 else None
        if model is ContactFamilyCreation:
            return next((row for row in rows if isinstance(row, ContactFamilyCreation) and row.request_id == key), None)
    def add(row):
        if isinstance(row, Contact):
            row.id = 1000 + len(rows)
        rows.append(row)
    session.get.side_effect = get
    session.add.side_effect = add
    payload = {
        "request_id": "00000000-0000-4000-8000-000000000001", "storage_key": "photo.png",
        "spouse": {"display_label": "Drugi rodzic"}, "spouse_relationship": "mąż",
        "children": [{"display_label": "Dziecko 1"}, {"display_label": "Dziecko 2"}],
        "source_note": "To mąż i dwoje dzieci, bliźnięta.", "twins": True,
        "share_photo": True, "copy_parent_groups": True, "peer_contact_id": 10, "children_group_id": 18,
    }
    return session, rows, payload, root


def test_family_is_atomic_with_twins_peer_and_shared_photo(family):
    session, rows, body, root = family
    result, status = create_family(session, root.id, body)
    assert status == 201
    contacts = [row for row in rows if isinstance(row, Contact)]
    assert len(contacts) == 3
    assert all(row.first_name is None and row.last_name is None for row in contacts)
    assert all(row.photo_storage_key == "photo.png" for row in contacts)
    assert all(row.photo_thumbnail_storage_key == "old-shared-thumb.jpg" for row in contacts)
    assert [g.id for g in contacts[0].groups] == [17]
    assert all([g.id for g in row.groups] == [18] for row in contacts[1:])
    relations = [row for row in rows if isinstance(row, ContactRelationship)]
    assert sum(row.relationship_type == "dziecko" for row in relations) == 4
    assert sum(row.relationship_type == "bliźnięta" for row in relations) == 1
    assert sum(row.related_contact_id == 10 for row in relations) == 2
    session.commit.assert_called_once()


def test_retry_returns_original_ids_without_duplicates(family):
    session, rows, body, root = family
    first, _ = create_family(session, root.id, body)
    count = len(rows)
    # Idempotency also survives changing the photo after the first success.
    root.photo_storage_key = "new.png"
    second, status = create_family(session, root.id, body)
    assert status == 200 and second["replayed"]
    assert second["family"] == first["family"]
    assert len(rows) == count
    assert create_family(session, root.id, {**body, "twins": False})[1] == 409


def test_failure_rolls_back_every_contact(family):
    session, rows, body, root = family
    session.commit.side_effect = RuntimeError("db failed")
    assert create_family(session, root.id, body)[1] == 500
    session.rollback.assert_called_once()


@pytest.mark.parametrize("change", [
    {"twins": "yes"}, {"twins": True, "children": [{"display_label": "Jedno dziecko"}]},
    {"source_note": ""}, {"children": [{}]}, {"peer_contact_id": 493},
    {"peer_contact_id": 999}, {"children_group_id": 999}, {"spouse_relationship": "zgadnięte"},
    {"request_id": "invalid"}, {"spouse": []},
])
def test_invalid_family_does_not_write_anything(family, change):
    session, rows, body, root = family
    assert create_family(session, root.id, {**body, **change})[1] == 400
    assert rows == []
    session.commit.assert_not_called()


def test_no_twins_without_user_fact_and_children_do_not_inherit_parent_groups(family):
    session, rows, body, root = family
    body.update(twins=False, children_group_id=None, share_photo=False)
    assert create_family(session, root.id, body)[1] == 201
    assert not any(row.relationship_type == "bliźnięta" for row in rows if isinstance(row, ContactRelationship))
    children = [row for row in rows if isinstance(row, Contact)][1:]
    assert all(not child.groups and child.photo_storage_key is None for child in children)


def test_changed_photo_rejects_creation(family):
    session, rows, body, root = family
    root.photo_storage_key = "new.png"
    assert create_family(session, root.id, body)[1] == 409
    assert rows == []
