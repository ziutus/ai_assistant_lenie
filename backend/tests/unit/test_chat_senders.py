"""Sender aggregation and bulk contact creation on isolated SQLite tables."""

import datetime as dt
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import Flask, g
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

from library import chat_routes
from library.chat_contact_service import SenderError
from library.db.models import (
    ChatConversation, ChatMessage, Contact, ContactCategory, ContactChangeLog, ContactGroup, ContactGroupMembership,
)


@pytest.fixture
def api(monkeypatch):
    metadata = MetaData()
    for model in (ChatConversation, ChatMessage, Contact, ContactCategory, ContactChangeLog,
                  ContactGroup, ContactGroupMembership):
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
        monkeypatch.setattr(chat_routes, "get_scoped_session", lambda: session)
        monkeypatch.setattr(chat_routes, "_bridge", lambda: pytest.fail("Bridge must not be used by default"))
        app = Flask(__name__)
        app.register_blueprint(chat_routes.bp)

        @app.before_request
        def auth():
            g.auth = SimpleNamespace(kind="user")

        yield app.test_client(), session
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


def test_aggregation_identity_latest_name_and_frequent_contact(api):
    client, session = api
    contact(session, 1)
    contact(session, 2)
    for cid in (1, 1, 2):
        message(session, "Dawna nazwa", wa_sender_jid="123@lid", contact_id=cid)
    latest_name = message(session, "Łukasz", wa_sender_jid="123@lid")
    latest = message(session, "", wa_sender_jid="123@lid")
    message(session, "Łukasz")
    message(session, "Łukasz", wa_sender_jid="456@lid")
    message(session, "Ja", is_from_me=True)
    message(session, "", message_type="deleted")
    message(session, "   ")
    queries = []

    def track(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(session.bind, "before_cursor_execute", track)
    result = client.get("/chat_conversations/1/senders").json
    event.remove(session.bind, "before_cursor_execute", track)
    assert len(queries) == 2  # Conversation and a single aggregate query, independent of author count.
    assert result["summary"] == {"senders": 3, "in_contacts": 1, "missing": 2}
    first = result["senders"][0]
    assert first["key"] == "123@lid" and first["name"] == latest_name.sender_name_raw
    assert first["message_count"] == 5 and first["sample_message_id"] == latest.id
    assert first["contact"] == {"id": 1, "display_name": "Kontakt 1"}
    assert not first["can_add"]
    assert first["last_at"] == latest.sent_at.isoformat()


def test_filters_summary_paging_and_phone(api):
    client, session = api
    contact(session, 1)
    message(session, "Łukasz", contact_id=1)
    message(session, "Żaneta", wa_sender_jid="48123456789@s.whatsapp.net")
    message(session, "Beata")
    result = client.get("/chat_conversations/1/senders?status=missing&q=zaneta&limit=1").json
    assert result["total"] == 1 and result["summary"] == {"senders": 3, "in_contacts": 1, "missing": 2}
    assert result["senders"][0]["phone"] == "48123456789"
    assert result["senders"][0]["can_add"]
    assert client.get("/chat_conversations/1/senders?q=123456").json["total"] == 1
    assert client.get("/chat_conversations/1/senders?status=in_contacts&q=LUKASZ").json["total"] == 1
    assert client.get("/chat_conversations/1/senders?offset=3&limit=999").json["senders"] == []
    assert client.get("/chat_conversations/1/senders?limit=999").json["limit"] == 500


def test_empty_and_invalid_requests(api):
    client, _ = api
    assert client.get("/chat_conversations/1/senders").json["summary"]["senders"] == 0
    assert client.get("/chat_conversations/1/senders?status=no").status_code == 400
    assert client.get("/chat_conversations/999/senders").status_code == 404
    assert client.post("/chat_conversations/999/senders/add_contacts", json={"message_ids": [1]}).status_code == 404


def test_deleted_senders_and_eligibility(api):
    client, session = api
    message(session, "Usunięty", message_type="deleted")
    message(session, "", message_type="deleted", wa_sender_jid="111@lid")
    message(session, "", message_type="text", wa_sender_jid="222@lid")
    message(session, "", message_type="deleted", wa_sender_jid="222@lid")
    rows = {s["key"]: s for s in client.get("/chat_conversations/1/senders").json["senders"]}
    assert rows["Usunięty"]["can_add"]
    assert not rows["111@lid"]["can_add"]
    assert rows["222@lid"]["can_add"]
    assert rows["222@lid"]["message_count"] == 2


def test_bulk_explicit_photo_option(api, monkeypatch):
    client, session = api
    row = message(session)
    session.commit()
    bridge = object()
    calls = []
    monkeypatch.setattr(chat_routes, "_bridge", lambda: bridge)

    def create(session, message, **kwargs):
        calls.append(kwargs)
        return {"existing": False, "contact_id": 42}

    monkeypatch.setattr(chat_routes, "create_contact_from_message", create)
    response = client.post("/chat_conversations/1/senders/add_contacts",
                           json={"message_ids": [row.id], "fetch_photo": True, "category_id": 1})
    assert response.json["counts"]["created"] == 1
    assert calls == [{"bridge": bridge, "fetch_photo": True, "category_id": 1}]


@pytest.mark.parametrize("body", [None, [], {}, {"message_ids": []}, {"message_ids": list(range(51))},
                                  {"message_ids": [True]}, {"message_ids": ["1"]},
                                  {"message_ids": [1], "fetch_photo": "false"},
                                  {"message_ids": [1], "category_id": False}])
def test_bulk_validation(api, body):
    assert api[0].post("/chat_conversations/1/senders/add_contacts", json=body).status_code == 400


def test_bulk_real_creation_linking_and_skips(api):
    client, session = api
    existing = contact(session, 7, phone_number="+48579063654")
    new = message(session, "Nowa osoba")
    known_phone = message(session, "+48 579 063 654")
    already = message(session, "Znany", contact_id=existing.id)
    elsewhere = message(session, "Inny", conversation_id=2)
    session.commit()
    result = client.post("/chat_conversations/1/senders/add_contacts",
                         json={"message_ids": [new.id, known_phone.id, already.id, elsewhere.id, 999]}).json
    assert result["counts"] == {"created": 1, "linked_existing": 1, "skipped": 3, "error": 0}
    assert result["results"][1]["contact_id"] == existing.id
    assert result["results"][2]["reason"] == "already_in_contacts"
    assert result["results"][3]["reason"] == "not_in_conversation"
    assert session.scalar(select(func.count()).select_from(Contact)) == 2
    assert session.scalar(select(ContactGroup.name)) == "WhatsApp: Sąsiedzi"
    assert session.scalar(select(func.count()).select_from(ContactChangeLog)) == 2


@pytest.mark.parametrize("exception", [SenderError("private details"), RuntimeError("private details")])
def test_savepoint_rolls_back_one_item_and_does_not_leak(api, monkeypatch, exception):
    client, session = api
    bad = message(session, "Błąd")
    good = message(session, "Dobra osoba")
    session.commit()
    original = chat_routes.create_contact_from_message

    def create(session, row, **kwargs):
        result = original(session, row, **kwargs)
        if row.id == bad.id:
            raise exception
        return result

    monkeypatch.setattr(chat_routes, "create_contact_from_message", create)
    response = client.post("/chat_conversations/1/senders/add_contacts", json={"message_ids": [bad.id, good.id]})
    assert response.status_code == 200
    assert "private details" not in response.get_data(as_text=True)
    assert response.json["counts"] == {"created": 1, "linked_existing": 0, "skipped": 0, "error": 1}
    session.expire_all()
    assert session.get(ChatMessage, bad.id).contact_id is None
    assert session.get(ChatMessage, good.id).contact_id is not None
    assert session.scalar(select(func.count()).select_from(Contact)) == 1
    assert session.scalar(select(func.count()).select_from(ContactChangeLog)) == 1


def test_bulk_requires_authorization(api, monkeypatch):
    from flask import abort

    monkeypatch.setattr(chat_routes, "_authorized", lambda: abort(403))
    assert api[0].post("/chat_conversations/1/senders/add_contacts", json={"message_ids": [1]}).status_code == 403
