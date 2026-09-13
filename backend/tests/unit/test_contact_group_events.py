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
