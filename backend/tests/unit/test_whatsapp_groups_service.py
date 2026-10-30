"""SQLite integration tests for snapshot safety and exact member identities."""

import datetime as dt
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

from library.db.models import (
    ChatConversation, ChatMessage, Contact, ContactCategory, ContactChangeLog, ContactGroup, ContactGroupMembership,
    WhatsappGroup, WhatsappGroupMember, WhatsappGroupMemberEvent, WhatsappSyncChat,
)
from library import whatsapp_groups_service as svc
from library.whatsapp_sync_service import BridgeClient, BridgeError

@pytest.fixture
def session():
    metadata = MetaData()
    for model in (ChatConversation, ChatMessage, Contact, ContactCategory, ContactChangeLog,
                  ContactGroup, ContactGroupMembership, WhatsappGroup, WhatsappGroupMember,
                  WhatsappGroupMemberEvent, WhatsappSyncChat):
        model.__table__.to_metadata(metadata)
    for table in metadata.tables.values():
        for constraint in list(table.foreign_key_constraints):
            if any(f.target_fullname.split(".")[0] not in metadata.tables for f in constraint.elements):
                table.constraints.remove(constraint)
                for fk in constraint.elements:
                    table.foreign_keys.remove(fk)
                    fk.parent.foreign_keys.remove(fk)
        for column in table.columns:
            if isinstance(column.type, (JSONB, ARRAY)):
                column.type = JSON()
            if isinstance(column.type, BigInteger):
                column.type = Integer()
            if column.server_default is not None and "::" in str(column.server_default.arg):
                column.server_default = None
            if column.name == "uuid":
                column.server_default = None
    engine = create_engine("sqlite://")
    engine.dialect.colspecs = {**engine.dialect.colspecs, ARRAY: JSON, JSONB: JSON}
    metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        @event.listens_for(session, "before_flush")
        def defaults(session, context, instances):
            for row in session.new:
                if isinstance(row, Contact):
                    row.uuid = row.uuid or str(uuid4())
                    for field, legacy in (("phone_numbers", "phone_number"), ("email_addresses", "email")):
                        if getattr(row, field) is None:
                            value = getattr(row, legacy)
                            setattr(row, field, [{"value": value, "label": None}] if value else [])
                    for field in ("languages", "nationality"):
                        if getattr(row, field) is None:
                            setattr(row, field, [])

        session.add_all([ChatConversation(id=1, chat_key="a", display_name="Sąsiedzi"),
                         ChatConversation(id=2, chat_key="b", display_name="Inni"),
                         ContactCategory(id=1, name="Osoby")])
        session.commit()
        yield session
    engine.dispose()


def message(session, name="Ala", **values):
    n = (session.scalar(select(func.max(ChatMessage.id))) or 0) + 1
    row = ChatMessage(id=n, conversation_id=1, sender_name_raw=name, sent_at=dt.datetime(2026, 10, 29, 12, n),
                      message_type="text", dedup_hash=f"hash-{n}")
    for key, value in values.items():
        setattr(row, key, value)
    session.add(row)
    session.flush()
    return row


def contact(session, id, **values):
    row = Contact(id=id, uuid=f"contact-{id}", category_id=1, display_label=f"Kontakt {id}",
                  languages=[], nationality=[], **values)
    session.add(row)
    session.flush()
    return row


NOW = dt.datetime(2026, 10, 30, 12)


def participant(n, **values):
    return {"jid": f"{n}@lid", "lid": f"{n}@lid", "phone": f"4857906{n:04d}",
            "display_name": "", "is_admin": False, "is_super_admin": False, **values}


def snapshot(*members, jid="group@g.us", **values):
    return {"jid": jid, "name": "Sąsiedzi", "participant_count": len(members),
            "participants": list(members), **values}


def sync(session, *groups, now=NOW):
    return svc.sync_groups(session, SimpleNamespace(groups=lambda: list(groups)), now=now)


def members(session):
    return list(session.scalars(select(WhatsappGroupMember).order_by(WhatsappGroupMember.id)))


def events(session):
    return list(session.scalars(select(WhatsappGroupMemberEvent).order_by(WhatsappGroupMemberEvent.id)))


def test_baseline_join_leave_rejoin_and_idempotence(session):
    session.add(WhatsappSyncChat(jid="group@g.us", conversation_id=1))
    result = sync(session, snapshot(participant(1), participant(2)))
    group = session.scalar(select(WhatsappGroup))
    assert result == {"groups": 1, "new": 1, "joins": 0, "leaves": 0, "skipped": []}
    assert group.conversation_id == 1 and group.baseline_at == NOW
    assert events(session) == []
    later = NOW + dt.timedelta(minutes=30)
    result = sync(session, snapshot(participant(2), participant(3)), now=later)
    assert result["joins"] == result["leaves"] == 1
    assert {e.event_type for e in events(session)} == {"join", "leave"}
    assert all(e.previous_synced_at == NOW and e.detected_at == later for e in events(session))
    first = members(session)[0]
    assert first.left_at == later
    result = sync(session, snapshot(participant(1), participant(2), participant(3)), now=later)
    assert result["joins"] == 1 and first.left_at is None
    assert first.first_seen_at == NOW
    sync(session, snapshot(participant(1), participant(2), participant(3)), now=later)
    assert len(events(session)) == 3


@pytest.mark.parametrize("new_jid", ["1@lid", "48579060001@s.whatsapp.net"])
def test_lid_to_phone_preserves_row_without_events(session, new_jid):
    sync(session, snapshot(participant(1, phone="")))
    member = members(session)[0]
    original_id = member.id
    sync(session, snapshot(participant(1, jid=new_jid)))
    assert len(members(session)) == 1
    assert member.id == original_id and member.member_key == participant(1)["phone"]
    assert events(session) == []
    sync(session, snapshot(participant(1, phone="")))
    assert member.phone == participant(1)["phone"]
    assert events(session) == []


@pytest.mark.parametrize("bad", [snapshot(participant(1), participant_count=2), snapshot(participant_count=2),
                                 snapshot(participant(1), participant(1))])
def test_incomplete_snapshot_preserves_watermark_and_members(session, bad):
    sync(session, snapshot(participant(1), participant(2)))
    result = sync(session, bad, now=NOW + dt.timedelta(hours=1))
    assert result["skipped"]
    assert all(m.left_at is None for m in members(session))
    assert session.scalar(select(WhatsappGroup)).last_synced_at == NOW
    assert events(session) == []


def test_mass_departure_guard_and_exact_half_allowed(session, caplog):
    sync(session, snapshot(*(participant(i) for i in range(12))))
    result = sync(session, snapshot(*(participant(i) for i in range(5))))
    assert result["skipped"][0]["reason"] == "mass_departure"
    assert len(events(session)) == 0
    assert "@lid" not in caplog.text and "4857906" not in caplog.text
    result = sync(session, snapshot(*(participant(i) for i in range(6))))
    assert result["leaves"] == 6


def test_empty_groups_is_error_without_changes(session):
    sync(session, snapshot(participant(1)))
    with pytest.raises(BridgeError, match="empty groups"):
        sync(session)
    assert session.scalar(select(WhatsappGroup)).is_active
    assert members(session)[0].left_at is None and events(session) == []


def test_missing_group_inactive_without_member_events(session):
    sync(session, snapshot(participant(1)), snapshot(jid="other@g.us"))
    sync(session, snapshot(jid="other@g.us"))
    assert not session.scalar(select(WhatsappGroup).where(WhatsappGroup.jid == "group@g.us")).is_active
    assert members(session)[0].left_at is None and events(session) == []


def test_partial_snapshot_does_not_deactivate_other_groups(session):
    sync(session, snapshot(participant(1)), snapshot(jid="other@g.us"))
    sync(session, snapshot(participant_count=1))
    assert all(g.is_active for g in session.scalars(select(WhatsappGroup)))


def test_exact_phone_secondary_numbers_no_suffix_or_name_matching(session):
    contact(session, 1, phone_number="+48 579 060 001")
    contact(session, 2, phone_numbers=[{"value": "+48 579 060 002", "label": "mobile"}])
    contact(session, 3, phone_number="+44 579 060 003")
    sync(session, snapshot(participant(1), participant(2), participant(3),
                           participant(4, phone="", display_name="Kontakt 1")))
    index = svc.ContactIndex(session, members(session))
    rows = [svc.member_dict(m, index) for m in members(session)]
    assert [r["status"] for r in rows] == ["in_contacts", "in_contacts", "missing", "unverified"]
    assert [r["can_add"] for r in rows] == [False, False, True, False]


@pytest.mark.parametrize("field", ["wa_sender_jid", "wa_sender_alt_jid"])
def test_message_contact_resolves_lid_without_phone(session, field):
    contact(session, 1)
    message(session, contact_id=1, **{field: "1@lid"})
    sync(session, snapshot(participant(1, phone="")))
    member = members(session)[0]
    row = svc.member_dict(member, svc.ContactIndex(session, [member]))
    assert row["status"] == "in_contacts" and row["contact"]["id"] == 1


def test_contact_creation_provenance_nickname_and_exact_link(session):
    sync(session, snapshot(participant(1), participant(2), participant(3, phone="")))
    a, b, unknown = members(session)
    msg = message(session, "Żaneta", wa_sender_jid="1@lid")
    result = svc.create_contact_from_member(session, a)
    assert result["outcome"] == "created"
    created = session.get(Contact, result["contact_id"])
    assert created.display_label == "Żaneta" and created.phone_number == "+48579060001"
    assert "Poznany(-a) z kanału WhatsApp „Sąsiedzi”" in created.notes
    assert created.groups[0].name == "WhatsApp: Sąsiedzi"
    assert msg.contact_id == a.contact_id == created.id
    contact(session, 20, phone_number="+48579060002")
    assert svc.create_contact_from_member(session, b) == {"outcome": "linked_existing", "contact_id": 20}
    assert svc.create_contact_from_member(session, unknown)["outcome"] == "skipped"


def test_contact_without_nickname_keeps_phone_as_last_name(session):
    sync(session, snapshot(participant(1)))
    result = svc.create_contact_from_member(session, members(session)[0])
    created = session.get(Contact, result["contact_id"])
    assert created.last_name == "+48579060001" and created.display_label is None


def test_worker_noop_without_bridge(monkeypatch, session):
    monkeypatch.setattr("library.config_loader.load_config", lambda: {})
    assert svc.execute_whatsapp_groups_sync(session, None) == {"status": "not_configured"}


def test_bridge_groups_endpoint():
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"groups": [snapshot()]})
    bridge = BridgeClient("http://bridge", "secret", http=SimpleNamespace(request=request))
    assert bridge.groups() == [snapshot()]
    assert calls[0][0:2] == ("GET", "http://bridge/groups")
    assert calls[0][2]["headers"] == {"Authorization": "Bearer secret"}


def test_bridge_failure_keeps_snapshot(session):
    sync(session, snapshot(participant(1)))
    bridge = BridgeClient("http://bridge", "secret", http=SimpleNamespace(
        request=lambda *args, **kwargs: SimpleNamespace(status_code=503)))
    with pytest.raises(BridgeError):
        svc.sync_groups(session, bridge)
    assert events(session) == [] and members(session)[0].left_at is None


def test_skipped_first_snapshot_does_not_establish_baseline(session):
    result = sync(session, snapshot(participant_count=1))
    assert result["skipped"] and session.scalar(select(WhatsappGroup)) is None
    sync(session, snapshot(participant(1)))
    assert events(session) == []


def test_contact_index_query_count_does_not_grow_with_members(session):
    sync(session, snapshot(*(participant(i) for i in range(100))))
    rows = members(session)
    statements = []
    connection = session.connection()

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        index = svc.ContactIndex(session, rows)
        for row in rows:
            svc.member_dict(row, index)
        assert len(statements) == 2
    finally:
        event.remove(connection, "before_cursor_execute", capture)


def test_worker_dispatch_and_configured_sync(session, monkeypatch):
    import worker
    from library.job_queue import JOB_TYPES

    calls = []
    monkeypatch.setattr("library.config_loader.load_config", lambda: {
        "WHATSAPP_BRIDGE_URL": "http://bridge", "WHATSAPP_BRIDGE_TOKEN": "secret",
    })
    monkeypatch.setattr(svc, "BridgeClient", lambda url, token: SimpleNamespace(groups=lambda: [snapshot()]))
    original = svc.execute_whatsapp_groups_sync

    def execute(s, job):
        calls.append(job)
        return original(s, job)

    monkeypatch.setattr(svc, "execute_whatsapp_groups_sync", execute)
    job = SimpleNamespace(type="whatsapp_groups_sync")
    assert "whatsapp_groups_sync" in JOB_TYPES
    assert worker.execute(session, job)["groups"] == 1
    assert calls == [job]


def test_scheduler_thirty_minutes_and_idempotency(monkeypatch):
    import worker

    task = SimpleNamespace(id="whatsapp_groups_sync", enabled=True, timezone="Europe/Warsaw",
                           times=[f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)])
    db = SimpleNamespace(scalars=lambda query: SimpleNamespace(all=lambda: [task]))
    calls = []
    monkeypatch.setattr(worker, "enqueue", lambda *args, **kwargs: calls.append((args, kwargs)))
    now = NOW.replace(tzinfo=dt.timezone.utc)
    worker.scheduler(db, now)
    worker.scheduler(db, now)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0][0] == (db, "whatsapp_groups_sync")
    worker.scheduler(db, now + dt.timedelta(minutes=1))
    assert len(calls) == 2
    worker.scheduler(db, now + dt.timedelta(minutes=30))
    assert len(calls) == 3 and calls[-1] != calls[0]

