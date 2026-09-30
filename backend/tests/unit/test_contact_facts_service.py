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


@pytest.mark.parametrize('attribute,value,expected', [
    ('birthday', {'month': 4, 'day': 12}, {'year': None, 'month': 4, 'day': 12}),
    ('birthday', {'year': 1984}, {'year': 1984, 'month': None, 'day': None}),
    ('birthday', {'year': 2000, 'month': 2, 'day': 29}, {'year': 2000, 'month': 2, 'day': 29}),
    ('birthday', {'month': 2, 'day': 29}, {'year': None, 'month': 2, 'day': 29}),
    ('gender', {'gender': 'female'}, {'gender': 'female'}),
    ('current_city', {'current_city': '  Lodz '}, {'current_city': 'Lodz'}),
])
def test_validate_assertion_value_accepts_and_normalises(attribute, value, expected):
    assert facts.validate_assertion_value(attribute, value) == expected


@pytest.mark.parametrize('attribute,value', [
    ('education', {'institution': 'MIT'}),            # many-valued, has its own endpoints
    ('birthday', {}), ('birthday', {'month': 4}), ('birthday', {'day': 4}),
    ('birthday', {'month': 2, 'day': 30}), ('birthday', {'year': 1899}),
    ('birthday', {'year': '1984'}), ('birthday', {'year': True}), ('birthday', {'age': 40}),
    ('gender', {'gender': 'attack helicopter'}), ('gender', {'gender': ''}), ('gender', {'sex': 'male'}),
    ('current_city', {'current_city': 'x' * 201}), ('hometown', {'hometown': None}), ('hometown', 'Lodz'),
])
def test_validate_assertion_value_rejects_bad_input(attribute, value):
    with pytest.raises(ValueError):
        facts.validate_assertion_value(attribute, value)


def test_rejecting_the_shown_claim_blanks_the_cache_but_keeps_the_claim(session):
    claim = record(session, 'facebook', value={'year': 1990, 'month': 4, 'day': 12}, status='confirmed')
    contact = session.get(Contact, 1)
    assert contact.birthday == dt.date(1990, 4, 12)
    facts.set_assertion_status(session, claim.id, 'rejected', by='owner', note='vanity year')
    assert session.get(ContactFactAssertion, claim.id).review_note == 'vanity year'
    assert claim.status == 'rejected' and claim.reviewed_by == 'owner' and claim.reviewed_at is not None
    assert (contact.birthday, contact.birthday_year, contact.birthday_month, contact.birthday_day) == (None,) * 4
    assert session.get(ContactFactSlot, claim.slot_id).selected_assertion_id is None


def test_rejecting_the_shown_claim_falls_back_to_the_next_best(session):
    worse = record(session, 'other', value={'month': 1, 'day': 2}, status='confirmed')
    better = record(session, 'linkedin', value={'month': 3, 'day': 4}, status='confirmed')
    contact = session.get(Contact, 1)
    assert contact.birthday_month == 3
    facts.set_assertion_status(session, better.id, 'rejected', by='owner')
    assert (contact.birthday_month, contact.birthday_day) == (1, 2)
    assert session.get(ContactFactSlot, worse.slot_id).selected_assertion_id == worse.id


def test_rejecting_a_hidden_claim_leaves_directly_written_cache_alone(session):
    contact = session.get(Contact, 1)
    contact.birthday_month, contact.birthday_day = 7, 8         # value written before the slot existed
    low = record(session, 'facebook', value={'month': 1, 'day': 2})   # priority 10 < 50: never applied
    assert session.get(ContactFactSlot, low.slot_id).selected_assertion_id is None
    facts.set_assertion_status(session, low.id, 'rejected', by='owner')
    assert (contact.birthday_month, contact.birthday_day) == (7, 8)


def test_rejecting_a_pinned_claim_releases_the_pin(session):
    claim = record(session, 'facebook', value={'month': 1, 'day': 2})
    facts.pin_assertion(session, claim.id, by='owner')
    slot = session.get(ContactFactSlot, claim.slot_id)
    assert slot.resolution_mode == 'pinned' and session.get(Contact, 1).birthday_month == 1
    facts.set_assertion_status(session, claim.id, 'rejected', by='owner')
    assert slot.resolution_mode == 'auto' and slot.decision_by is None and slot.selected_assertion_id is None
    assert session.get(Contact, 1).birthday_month is None


def test_set_assertion_status_guards(session):
    manual = record(session)
    claim = record(session, 'facebook', value={'month': 1, 'day': 2})
    with pytest.raises(PermissionError):
        facts.set_assertion_status(session, manual.id, 'rejected', by='owner')
    with pytest.raises(ValueError):
        facts.set_assertion_status(session, claim.id, 'superseded', by='owner')
    with pytest.raises(LookupError):
        facts.set_assertion_status(session, 9999, 'rejected', by='owner')
    with pytest.raises(LookupError):
        facts.set_assertion_status(session, claim.id, 'rejected', by='owner', contact_id=2)
    assert claim.status == 'candidate' and session.get(Contact, 1).birthday_month == 4


def test_reassign_source_repairs_facebook_value_stored_as_manual(session):
    wrong = record(session, value={'year': 1977, 'month': 12, 'day': 6})
    slot = session.get(ContactFactSlot, wrong.slot_id)
    assert slot.resolution_mode == 'pinned'
    facts.reassign_assertion_source(session, wrong.id, 'facebook')
    assert wrong.source_key == 'facebook' and slot.resolution_mode == 'auto'
    assert slot.selected_assertion_id == wrong.id and session.get(Contact, 1).birthday_year == 1977
    # a better source can now compete with it instead of being blocked by a fake manual pin
    better = record(session, 'linkedin', value={'year': 1978, 'month': 12, 'day': 6}, status='confirmed')
    assert slot.selected_assertion_id == better.id and session.get(Contact, 1).birthday_year == 1978
    with pytest.raises(ValueError):
        facts.reassign_assertion_source(session, wrong.id, 'user_manual')
    with pytest.raises(ValueError):
        facts.reassign_assertion_source(session, wrong.id, 'nonexistent')


def test_reassign_source_refuses_to_merge_into_an_existing_assertion(session):
    manual = record(session, value={'month': 4, 'day': 12})
    facebook = facts.record_assertion(
        session, contact_id=1, attribute_key='birthday', item_key='singleton', source_key='facebook',
        source_record_key=manual.source_record_key, value={'month': 4, 'day': 12}, status='candidate')
    with pytest.raises(ValueError):
        facts.reassign_assertion_source(session, manual.id, 'facebook')
    assert manual.source_key == 'user_manual' and facebook.id != manual.id


@pytest.fixture
def client(session, monkeypatch):
    from library import contact_routes as routes
    session.add(Contact(id=2, uuid='other-contact', category_id=1, first_name='Other',
                        phone_numbers=[], email_addresses=[], languages=[], nationality=[]))
    session.flush()
    monkeypatch.setattr(routes, 'get_scoped_session', lambda: session)
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    return app.test_client()


def post_claim(client, contact_id=1, **overrides):
    body = {'attribute_key': 'birthday', 'source_key': 'facebook', 'value': {'month': 4, 'day': 12},
            'source_url': 'https://www.facebook.com/x', 'status': 'confirmed', **overrides}
    return client.post(f'/contacts/{contact_id}/facts/assertions', json=body)


def test_post_assertion_applies_a_confirmed_claim_with_its_source(client, session):
    response = post_claim(client, value={'year': 1990, 'month': 4, 'day': 12}, confidence=0.4,
                          evidence_note='Data widoczna na profilu')
    assert response.status_code == 200
    result = response.json['assertions'][0]
    assert result['applied'] is True and result['source_key'] == 'facebook' and result['status'] == 'confirmed'
    assertion = session.get(ContactFactAssertion, result['assertion_id'])
    assert assertion.source_key == 'facebook' and assertion.source_url == 'https://www.facebook.com/x'
    assert assertion.evidence_note == 'Data widoczna na profilu' and float(assertion.confidence) == 0.4
    assert assertion.source_record_key == 'profile' and assertion.asserted_by == 'unknown'
    assert session.get(Contact, 1).birthday == dt.date(1990, 4, 12)


def test_post_assertion_never_overrides_the_owners_pinned_value(client, session):
    record(session, value={'month': 9, 'day': 26})                # owner's own, pinned
    result = post_claim(client, value={'year': 1984, 'month': 9, 'day': 26}).json['assertions'][0]
    assert result['applied'] is False and result['resolution_mode'] == 'pinned'
    contact = session.get(Contact, 1)
    assert (contact.birthday_year, contact.birthday_month, contact.birthday_day) == (None, 9, 26)
    listing = client.get('/contacts/1/facts?attribute_key=birthday').json['facts'][0]
    assert [a['source_key'] for a in listing['assertions']] == ['user_manual', 'facebook']


def test_post_assertion_records_a_known_false_claim(client, session):
    result = post_claim(client, value={'year': 1984}, status='rejected',
                        evidence_note='Fałszywy rok urodzenia na FB (zgłoszone przez usera)').json['assertions'][0]
    assert result['status'] == 'rejected' and result['applied'] is False
    assert session.get(Contact, 1).birthday_year is None


def test_post_assertion_batch_and_low_priority_candidate(client, session):
    response = client.post('/contacts/1/facts/assertions', json={'assertions': [
        {'attribute_key': 'current_city', 'source_key': 'facebook', 'value': {'current_city': 'Lodz'},
         'status': 'confirmed'},
        {'attribute_key': 'birthday', 'source_key': 'facebook', 'value': {'month': 1, 'day': 2}},
    ]})
    first, second = response.json['assertions']
    assert first['applied'] is True and second['applied'] is False and second['status'] == 'candidate'
    contact = session.get(Contact, 1)
    assert contact.current_city == 'Lodz' and contact.birthday_month is None


@pytest.mark.parametrize('overrides', [
    {'source_key': 'user_manual'}, {'source_key': 'nonexistent'}, {'source_key': None},
    {'attribute_key': 'education', 'value': {'institution': 'MIT'}}, {'attribute_key': 'nope'},
    {'value': {'month': 2, 'day': 30}}, {'value': 'x'}, {'status': 'superseded'}, {'status': 'pending'},
    {'confidence': 2}, {'confidence': True}, {'confidence': 'high'}, {'source_url': 'u' * 2001},
    {'source_record_key': 5},
])
def test_post_assertion_validation(client, session, overrides):
    response = post_claim(client, **overrides)
    assert response.status_code == 400 and response.json['status'] == 'error'
    assert session.scalar(select(func.count()).select_from(ContactFactAssertion)) == 0


def test_post_assertion_payload_shape_and_missing_contact(client, session):
    assert client.post('/contacts/1/facts/assertions', json={'assertions': []}).status_code == 400
    assert client.post('/contacts/1/facts/assertions', json={'assertions': [{}] * 21}).status_code == 400
    assert client.post('/contacts/1/facts/assertions', json=['x']).status_code == 400
    assert client.post('/contacts/1/facts/assertions', data='not json').status_code == 400
    assert post_claim(client, contact_id=999).status_code == 404
    # one bad item rejects the whole batch: nothing is written
    body = {'assertions': [
        {'attribute_key': 'gender', 'source_key': 'facebook', 'value': {'gender': 'male'}, 'status': 'confirmed'},
        {'attribute_key': 'gender', 'source_key': 'facebook', 'value': {'gender': 'robot'}},
    ]}
    response = client.post('/contacts/1/facts/assertions', json=body)
    assert response.status_code == 400 and 'assertions[1]' in response.json['message']
    assert session.scalar(select(func.count()).select_from(ContactFactAssertion)) == 0


def test_patch_assertion_marks_the_shown_claim_false(client, session):
    result = post_claim(client, value={'year': 1984, 'month': 9, 'day': 26}).json['assertions'][0]
    assert session.get(Contact, 1).birthday_year == 1984
    response = client.patch(f"/contacts/1/facts/assertions/{result['assertion_id']}",
                            json={'status': 'rejected', 'review_note': 'Rok zmyślony, potwierdzone przez usera'})
    assert response.status_code == 200
    assert response.json['assertion'] == {**result, 'status': 'rejected', 'applied': False,
                                           'selected_assertion_id': None}
    contact = session.get(Contact, 1)
    assert (contact.birthday_year, contact.birthday_month, contact.birthday_day) == (None, None, None)
    stored = session.get(ContactFactAssertion, result['assertion_id'])
    assert stored.review_note == 'Rok zmyślony, potwierdzone przez usera' and stored.reviewed_at is not None


def test_patch_assertion_errors(client, session):
    manual = record(session, value={'month': 9, 'day': 26})
    claim = post_claim(client, attribute_key='gender', value={'gender': 'male'}).json['assertions'][0]
    assert client.patch(f'/contacts/1/facts/assertions/{manual.id}', json={'status': 'rejected'}).status_code == 409
    assert client.patch(f"/contacts/2/facts/assertions/{claim['assertion_id']}",
                        json={'status': 'rejected'}).status_code == 404       # belongs to contact 1
    assert client.patch('/contacts/1/facts/assertions/9999', json={'status': 'rejected'}).status_code == 404
    assert client.patch('/contacts/999/facts/assertions/1', json={'status': 'rejected'}).status_code == 404
    for body in ({}, {'status': 'superseded'}, {'status': 'confirmed', 'review_note': 5}):
        assert client.patch(f"/contacts/1/facts/assertions/{claim['assertion_id']}", json=body).status_code == 400
    assert session.get(ContactFactAssertion, claim['assertion_id']).status == 'confirmed'
    assert session.get(Contact, 1).birthday_month == 9


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
