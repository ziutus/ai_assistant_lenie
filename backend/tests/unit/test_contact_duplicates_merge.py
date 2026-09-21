"""Duplicate review contracts without a database connection."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from library.contact_duplicates import dismiss_duplicate_pair, find_duplicate_candidates
from library.contact_merge import merge_contacts
from library.db.models import Contact, ContactChangeLog, ContactDuplicateDismissal, ContactRelationship


@pytest.mark.parametrize("choices", [{"uuid": "duplicate"}, {"notes": "other"}, [], None])
def test_invalid_choices_do_not_write(choices):
    session = MagicMock()
    with pytest.raises(ValueError):
        merge_contacts(session, 1, 2, choices)
    session.execute.assert_not_called()
    session.delete.assert_not_called()


def test_dismissal_normalizes_order_and_updates_existing_note():
    session = MagicMock()
    row = ContactDuplicateDismissal(contact_id_a=1, contact_id_b=2, note="old")
    session.scalar.return_value = row
    assert dismiss_duplicate_pair(session, 2, 1, "new") is row
    assert row.note == "new"
    assert session.scalar.call_args.args[0].compile().params == {"contact_id_a_1": 1, "contact_id_b_1": 2}
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_detection_excludes_empty_names_archived_and_dismissed_pairs():
    session = MagicMock()
    session.execute.return_value = []
    find_duplicate_candidates(session)
    query = session.execute.call_args.args[0]
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "similarity(unaccent(lower(trim(concat(" in sql
    assert sql.count("!= ''") == 2
    assert sql.count("is_archived IS false") == 2
    assert "contacts_1.id < contacts_2.id" in sql
    assert "NOT (EXISTS" in sql and "contact_duplicate_dismissals" in sql
    find_duplicate_candidates(session, include_archived=True)
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "is_archived IS false" not in sql


def test_merge_preserves_history_channels_and_resolves_relationship_conflicts():
    primary = Contact(id=1, first_name="Anna", notes="primary", email="a@example.com",
                      email_addresses=[{"value": "a@example.com", "label": None}])
    duplicate = Contact(id=2, first_name="Ania", notes="duplicate", pesel="12345678901", email="b@example.com",
                        email_addresses=[{"value": "b@example.com", "label": None}])
    direct = ContactRelationship(id=10, contact_id=2, related_contact_id=1, relationship_type="kolega")
    collision = ContactRelationship(id=11, contact_id=2, related_contact_id=3, relationship_type="kolega")
    incoming = ContactRelationship(id=12, contact_id=4, related_contact_id=2, relationship_type="kolega")
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [primary, duplicate]), [], [], [], [], [], [],
        MagicMock(all=lambda: [direct, collision, incoming]),
    ]
    session.scalar.side_effect = [None, 20, None]
    result = merge_contacts(session, 1, 2, {"pesel": "duplicate", "email": "duplicate"})
    assert result is primary
    updates = [call.args[0] for call in session.execute.call_args_list]
    compiled = [query.compile(dialect=postgresql.dialect()) for query in updates]
    assert compiled[0].params["pesel"] is None
    values = compiled[1].params
    assert values["pesel"] == "12345678901"
    assert values["email"] == "b@example.com"
    assert [entry["value"] for entry in values["email_addresses"]] == ["b@example.com", "a@example.com"]
    assert "notes" not in values and "first_name" not in values
    tables = {query.table.name for query in updates}
    assert {"chat_messages", "contact_change_log", "contact_family_creations", "contact_education",
            "contact_links", "contact_lookup_results", "contact_addresses", "contact_organizations"} <= tables
    assert incoming.related_contact_id == 1
    assert [call.args[0] for call in session.delete.call_args_list] == [direct, collision, duplicate]
    log = next(call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactChangeLog))
    assert log.source == "other" and "#2 (Ania)" in log.note
    assert set(log.changed_fields) == {"pesel", "email", "email_addresses"}
    session.commit.assert_not_called()


def test_missing_contact_does_not_mutate():
    session = MagicMock()
    session.scalars.return_value.all.return_value = [Contact(id=1)]
    with pytest.raises(ValueError, match="not found"):
        merge_contacts(session, 1, 2, {})
    session.execute.assert_not_called()
