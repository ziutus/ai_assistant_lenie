"""ORM shape of lightweight group events."""
import datetime

from library.db.models import ContactGroupEvent


def test_create_and_repr():
    event = ContactGroupEvent(id=1, group_id=2, title="Meeting", event_date=datetime.date(2026, 9, 13))
    assert event.event_date == datetime.date(2026, 9, 13)
    assert repr(event) == "ContactGroupEvent(id=1, group_id=2, title='Meeting')"
    table = ContactGroupEvent.__table__
    assert next(iter(table.c.group_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(table.c.source_document_id.foreign_keys)).ondelete == "SET NULL"


def test_event_date_end_nullable_and_defaults_to_none():
    event = ContactGroupEvent(group_id=2, title="Meeting", event_date=datetime.date(2026, 9, 13))
    assert ContactGroupEvent.__table__.c.event_date_end.nullable
    assert event.event_date_end is None


def test_event_date_end_settable():
    event = ContactGroupEvent(
        group_id=2, title="Meeting", event_date=datetime.date(2026, 9, 13),
        event_date_end=datetime.date(2026, 9, 14),
    )
    assert event.event_date_end == datetime.date(2026, 9, 14)
    event.event_date_end = None
    assert event.event_date_end is None
