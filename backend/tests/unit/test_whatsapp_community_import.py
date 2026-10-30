"""Community grouping on /chats and the one-click community import switch."""

from types import SimpleNamespace

import pytest
import test_whatsapp_groups_service as service_tests
from flask import Flask, g
from sqlalchemy import select

from library import chat_routes
from library import whatsapp_groups_routes as groups_routes
from library import whatsapp_sync_routes as sync_routes
from library.db.models import ChatConversation, WhatsappSyncChat
from test_whatsapp_groups_service import participant, snapshot, sync

db_session = service_tests.session


@pytest.fixture
def api(db_session, monkeypatch):
    session = db_session
    for module in (groups_routes, sync_routes, chat_routes):
        monkeypatch.setattr(module, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(groups_routes.bp)
    app.register_blueprint(sync_routes.bp)
    app.register_blueprint(chat_routes.bp)

    @app.before_request
    def auth():
        # Same rule as server.py: no key check on a CORS preflight, so g.auth stays unset there.
        from flask import request
        if request.method != "OPTIONS" and app.config.get("AUTH", True):
            g.auth = SimpleNamespace(kind="user")

    one = participant(1)
    sync(
        session,
        snapshot(one, jid="community@g.us", name="Dom", is_community=True),
        snapshot(one, jid="announce@g.us", name="Dom - ogłoszenia", parent_jid="community@g.us",
                 is_announce=True, is_default_sub=True),
        snapshot(one, jid="sub1@g.us", name="Dom - ogród", parent_jid="community@g.us"),
        snapshot(one, jid="sub2@g.us", name="Dom - garaż", parent_jid="community@g.us"),
        snapshot(one, jid="other-community@g.us", name="Inna", is_community=True),
        snapshot(one, jid="other-sub@g.us", name="Inna - sub", parent_jid="other-community@g.us"),
        snapshot(one, jid="plain@g.us", name="Zwykła grupa"),
    )
    session.add(WhatsappSyncChat(jid="sub1@g.us", display_name="Dom - ogród", is_group=True, enabled=False))
    session.add(WhatsappSyncChat(jid="plain@g.us", display_name="Zwykła grupa", is_group=True, enabled=False))
    session.add(WhatsappSyncChat(jid="other-sub@g.us", display_name="Inna - sub", is_group=True, enabled=False))
    session.commit()
    return app, session


def community_id(session, jid="community@g.us"):
    return session.scalar(select(groups_routes.WhatsappGroup.id).where(groups_routes.WhatsappGroup.jid == jid))


def enabled_by_jid(session):
    return {c.jid: c.enabled for c in session.scalars(select(WhatsappSyncChat))}


def test_chat_list_carries_community_fields(api):
    app, session = api
    session.add(WhatsappSyncChat(jid="announce@g.us", display_name="x", is_group=True, enabled=False))
    session.commit()
    chats = {c["jid"]: c for c in app.test_client().get("/whatsapp_sync/chats").get_json()["chats"]}
    assert chats["sub1@g.us"]["community_name"] == "Dom"
    assert chats["sub1@g.us"]["community_group_id"] == community_id(session)
    assert chats["sub1@g.us"]["is_community"] is False and chats["sub1@g.us"]["is_announce"] is False
    assert chats["announce@g.us"]["is_announce"] is True
    assert chats["plain@g.us"]["community_group_id"] is None and chats["plain@g.us"]["community_name"] is None
    assert chats["plain@g.us"]["id"]  # existing keys are kept


def test_import_enables_subgroups_creates_missing_rows_and_leaves_others(api):
    app, session = api
    response = app.test_client().post(f"/whatsapp_groups/{community_id(session)}/import", json={})
    body = response.get_json()
    assert response.status_code == 200 and body["dry_run"] is False
    assert body["counts"] == {"subgroups": 3, "already": 0, "changed": 1, "created": 2}
    assert body["community"]["name"] == "Dom"
    assert {c["jid"] for c in body["chats"]} == {"announce@g.us", "sub1@g.us", "sub2@g.us"}
    state = enabled_by_jid(session)
    assert state["sub1@g.us"] and state["announce@g.us"] and state["sub2@g.us"]
    assert state["other-sub@g.us"] is False and state["plain@g.us"] is False  # other communities untouched
    assert "community@g.us" not in state  # the umbrella itself has nothing to import


def test_import_is_idempotent(api):
    app, session = api
    client, path = app.test_client(), f"/whatsapp_groups/{community_id(session)}/import"
    client.post(path, json={})
    counts = client.post(path, json={}).get_json()["counts"]
    assert counts == {"subgroups": 3, "already": 3, "changed": 0, "created": 0}


def test_dry_run_writes_nothing_but_reports_the_same_counts(api):
    app, session = api
    before = enabled_by_jid(session)
    body = app.test_client().post(f"/whatsapp_groups/{community_id(session)}/import",
                                  json={"dry_run": True}).get_json()
    assert body["dry_run"] is True
    assert body["counts"] == {"subgroups": 3, "already": 0, "changed": 1, "created": 2}
    assert enabled_by_jid(session) == before


def test_disable_turns_off_existing_rows_and_creates_nothing(api):
    app, session = api
    client, path = app.test_client(), f"/whatsapp_groups/{community_id(session)}/import"
    client.post(path, json={})
    body = client.post(path, json={"enabled": False}).get_json()
    assert body["counts"] == {"subgroups": 3, "already": 0, "changed": 3, "created": 0}
    assert not any(enabled_by_jid(session)[j] for j in ("announce@g.us", "sub1@g.us", "sub2@g.us"))
    # a community never imported before: disabling must not create rows
    other = client.post(f"/whatsapp_groups/{community_id(session, 'other-community@g.us')}/import",
                        json={"enabled": False, "dry_run": True}).get_json()
    assert other["counts"] == {"subgroups": 1, "already": 1, "changed": 0, "created": 0}


@pytest.mark.parametrize("path,body,code", [
    ("/whatsapp_groups/{plain}/import", {}, 400),
    ("/whatsapp_groups/999999/import", {}, 404),
    ("/whatsapp_groups/{community}/import", {"enabled": "yes"}, 400),
    ("/whatsapp_groups/{community}/import", {"dry_run": 1}, 400),
])
def test_import_validation(api, path, body, code):
    app, session = api
    path = path.format(plain=community_id(session, "plain@g.us"), community=community_id(session))
    assert app.test_client().post(path, json=body).status_code == code


def test_list_groups_counts_only_for_communities(api):
    app, session = api
    app.test_client().post(f"/whatsapp_groups/{community_id(session)}/import", json={})
    groups = {g["jid"]: g for g in app.test_client().get("/whatsapp_groups").get_json()["groups"]}
    assert (groups["community@g.us"]["import_total"], groups["community@g.us"]["import_enabled"]) == (3, 3)
    assert (groups["other-community@g.us"]["import_total"], groups["other-community@g.us"]["import_enabled"]) == (1, 0)
    assert groups["plain@g.us"]["import_total"] is None and groups["plain@g.us"]["import_enabled"] is None


def test_import_needs_a_key_but_preflight_does_not(api):
    app, session = api
    app.config["AUTH"] = False
    client, path = app.test_client(), f"/whatsapp_groups/{community_id(session)}/import"
    assert client.options(path).status_code != 403
    assert client.post(path, json={}).status_code == 403
    assert "sub2@g.us" not in enabled_by_jid(session)  # the rejected request wrote nothing


def test_conversation_list_groups_conversations_under_their_community(api):
    app, session = api
    for conversation_id, jid in ((201, "sub1@g.us"), (202, "community@g.us"), (203, "announce@g.us"),
                                 (204, "plain@g.us")):
        session.add(ChatConversation(id=conversation_id, chat_key=f"k{conversation_id}", platform="whatsapp",
                                     display_name=f"rozmowa {conversation_id}", message_count=0))
        chat = session.scalar(select(WhatsappSyncChat).where(WhatsappSyncChat.jid == jid))
        if chat is None:
            chat = WhatsappSyncChat(jid=jid, display_name=jid, is_group=True, enabled=True)
            session.add(chat)
        chat.conversation_id = conversation_id
    session.add(ChatConversation(id=205, chat_key="k205", platform="whatsapp", display_name="bez grupy",
                                 message_count=3))
    session.commit()

    rows = {c["id"]: c for c in app.test_client().get("/chat_conversations").get_json()["conversations"]}
    community = community_id(session)
    assert rows[201]["community_group_id"] == community and rows[201]["community_name"] == "Dom"
    assert rows[201]["is_community"] is False and rows[201]["is_announce"] is False
    assert rows[202]["community_group_id"] == community and rows[202]["is_community"] is True  # the umbrella
    assert rows[203]["community_group_id"] == community and rows[203]["is_announce"] is True
    assert rows[204]["community_group_id"] is None and rows[204]["community_name"] is None  # plain group
    assert rows[205]["community_group_id"] is None and rows[205]["message_count"] == 3  # no sync chat at all
    assert rows[205]["display_name"] == "bez grupy"  # existing keys are kept
