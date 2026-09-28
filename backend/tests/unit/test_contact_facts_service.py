"""Fact resolution tests on isolated SQLAlchemy sessions (no external database)."""
import datetime as dt
from types import SimpleNamespace

import pytest
from flask import Flask, g
from sqlalchemy import JSON, MetaData, create_engine, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

from library import contact_facts_service as facts
from library.db.models import (
    Contact, ContactChangeLog, ContactEducation, ContactFactAssertion, ContactFactAttribute,
    ContactFactSlot, ContactFactSource, ContactFactSourcePolicy,
)


@pytest.fixture
def session():
    # Contact route fixtures mock sessions. Here real SQL queries/flushes are needed;
    # copy only the relevant tables and adapt PostgreSQL JSON/ARRAY storage to SQLite.
    metadata = MetaData()
    models = (Contact, ContactChangeLog, ContactEducation, ContactFactSource,
              ContactFactAttribute, ContactFactSourcePolicy, ContactFactSlot, ContactFactAssertion)
    for model in models:
        model.__table__.to_metadata(metadata)
    for table in metadata.tables.values():
        for constraint in list(table.foreign_key_constraints):
            if any(fk.target_fullname.split('.')[0] not in metadata.tables for fk in constraint.elements):
                table.constraints.remove(constraint)
                for fk in constraint.elements:
                    table.foreign_keys.remove(fk)
                    fk.parent.foreign_keys.remove(fk)
        for column in table.columns:
            if isinstance(column.type, (JSONB, ARRAY)):
                column.type = JSON()
            if column.server_default is not None and '::' in str(column.server_default.arg):
                column.server_default = None
            if column.name == 'uuid':
                column.server_default = None
    engine = create_engine('sqlite://')
    engine.dialect.colspecs = {**engine.dialect.colspecs, ARRAY: JSON, JSONB: JSON}
    metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Contact(id=1, uuid='test-contact', category_id=1, first_name='Test',
                            phone_numbers=[], email_addresses=[], languages=[], nationality=[]))
        session.add_all([ContactFactSource(key=key, default_priority=priority) for key, priority in (
            ('facebook', 20), ('linkedin', 40), ('user_manual', 100), ('other', 10),
        )])
        session.add_all([ContactFactAttribute(key=key, cardinality=cardinality, min_auto_priority=priority)
                         for key, cardinality, priority in (
            ('birthday', 'single', 50), ('education', 'many', 30), ('current_city', 'single', 30),
            ('hometown', 'single', 30), ('gender', 'single', 30),
        )])
        session.flush()
        session.add_all([ContactFactSourcePolicy(source_key=source, attribute_key=attribute, priority=priority)
                         for source, attribute, priority in (
            ('facebook', 'birthday', 10), ('linkedin', 'birthday', 20),
            ('facebook', 'education', 30), ('linkedin', 'education', 80),
        )])
        session.flush()
        yield session
    engine.dispose()


def record(session, source='user_manual', attribute='birthday', value=None, **kwargs):
    return facts.record_assertion(
        session, contact_id=1, attribute_key=attribute,
        item_key='episode:1' if attribute == 'education' else 'singleton', source_key=source,
        source_record_key=f'profile:{source}', value=value or {'month': 4, 'day': 12}, **kwargs,
    )


def test_manual_wins_even_with_lower_configured_priority(session):
    session.get(ContactFactSource, 'user_manual').default_priority = 0
    session.get(ContactFactSource, 'other').default_priority = 100
    record(session, 'other', status='confirmed', value={'month': 1, 'day': 1})
    manual = record(session, asserted_by='owner', status='rejected')
    later = record(session, 'other', status='confirmed', value={'month': 2, 'day': 2})
    slot = session.get(ContactFactSlot, manual.slot_id)
    assert slot.selected_assertion_id == manual.id != later.id
    assert slot.resolution_mode == 'pinned' and slot.decision_by == 'owner'
    assert manual.status == 'confirmed'
    assert session.get(Contact, 1).birthday_day == 12


@pytest.mark.parametrize('attribute,status,first,second', [
    ('birthday', 'confirmed', {'month': 1, 'day': 2}, {'month': 3, 'day': 4}),
    ('education', 'candidate', {'institution': 'MIT'}, {'institution': 'WSHE Lodz'}),
])
def test_policy_override_selects_linkedin(session, attribute, status, first, second):
    session.get(ContactFactSource, 'facebook').default_priority = 100
    linkedin = record(session, 'linkedin', attribute, second, status=status)
    record(session, 'facebook', attribute, first, status=status, confidence=1)
    slot = session.get(ContactFactSlot, linkedin.slot_id)
    assert slot.selected_assertion_id == linkedin.id
    if attribute == 'education':
        assert session.scalar(select(ContactEducation)).institution == 'WSHE Lodz'
    else:
        assert session.get(Contact, 1).birthday_month == 3


def test_duplicate_only_refreshes_last_seen(session, monkeypatch):
    first = record(session)
    observed = first.observed_at
    later = observed + dt.timedelta(days=1)
    monkeypatch.setattr(facts, '_now', lambda: later)
    duplicate = record(session, value={'day': 12, 'month': 4})
    session.flush()
    assert duplicate.id == first.id and duplicate.dedup_key == first.dedup_key
    assert duplicate.last_seen_at == later and duplicate.observed_at == observed
    assert session.scalar(select(func.count()).select_from(ContactFactAssertion)) == 1
    assert session.scalar(select(func.count()).select_from(ContactChangeLog)) == 1


@pytest.mark.parametrize('mode', ['pinned', 'suppressed'])
def test_resolve_does_not_change_non_auto_slots(session, mode):
    assertion = record(session)
    slot = session.get(ContactFactSlot, assertion.slot_id)
    slot.resolution_mode = mode
    facts.resolve_slot(session, slot)
    assert slot.selected_assertion_id == assertion.id


def test_projection_updates_birthday_and_logs_only_changes(session):
    assertion = record(session, value={'year': 1990, 'month': 4, 'day': 12})
    contact = session.get(Contact, 1)
    assert (contact.birthday_month, contact.birthday_day, contact.birthday_year) == (4, 12, 1990)
    assert contact.birthday == dt.date(1990, 4, 12)
    session.flush()
    log = session.scalar(select(ContactChangeLog))
    assert set(log.changed_fields) == {'birthday', 'birthday_month', 'birthday_day', 'birthday_year'}
    facts.project_slot_to_cache(session, session.get(ContactFactSlot, assertion.slot_id))
    assert session.scalar(select(func.count()).select_from(ContactChangeLog)) == 1


def test_threshold_rejected_and_release_pin(session):
    low = record(session, 'facebook')
    slot = session.get(ContactFactSlot, low.slot_id)
    assert slot.selected_assertion_id is None
    confirmed = record(session, 'linkedin', value={'month': 3, 'day': 5}, status='confirmed')
    rejected = record(session, 'other', value={'month': 6, 'day': 5}, status='rejected')
    facts.pin_assertion(session, low.id, by='owner', note='known')
    assert slot.selected_assertion_id == low.id
    facts.release_pin(session, slot.id)
    assert slot.selected_assertion_id == confirmed.id != rejected.id
    confirmed.status = 'superseded'
    facts.resolve_slot(session, slot)
    assert slot.selected_assertion_id is None


@pytest.mark.parametrize('attribute,value', [
    ('birthday', {'month': 4, 'day': 12}), ('current_city', {'current_city': 'Lodz'}),
    ('hometown', {'hometown': 'Warsaw'}), ('gender', {'gender': 'female'}),
    ('education', {'institution': 'WSHE', 'start_date': '2000-01-01'}),
])
def test_suppression_clears_cache_but_preserves_assertions(session, attribute, value):
    assertion = record(session, attribute=attribute, value=value)
    facts.suppress_slot(session, assertion.slot_id, by='owner')
    session.flush()
    assert session.get(ContactFactAssertion, assertion.id) is assertion
    if attribute == 'education':
        assert session.scalar(select(ContactEducation)) is None
    elif attribute == 'birthday':
        assert session.get(Contact, 1).birthday_month is None
    else:
        assert getattr(session.get(Contact, 1), attribute) is None


def test_facts_api_and_manual_route_helper(session, monkeypatch):
    from library import contact_routes as routes
    monkeypatch.setattr(routes, 'get_scoped_session', lambda: session)
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    with app.test_request_context():
        g.auth = SimpleNamespace(user_id=7, key_id=3)
        routes._record_manual_contact_facts(session, session.get(Contact, 1), {
            'birthday_year': 1990, 'birthday_month': 4, 'birthday_day': 12,
            'current_city': ' Lodz ', 'gender': 'female', 'hometown': 'Warsaw',
        })
    response = app.test_client().get('/contacts/1/facts?attribute_key=birthday')
    assert response.status_code == 200
    slots = response.json['facts']
    assert len(slots) == 1
    assert slots[0]['assertions'][0]['asserted_by'] == 'user:7'
    assert slots[0]['assertions'][0]['source_record_key'] == 'manual:user:7'
    assert session.get(Contact, 1).current_city == 'Lodz'
    assert app.test_client().get('/contacts/999/facts').status_code == 404
