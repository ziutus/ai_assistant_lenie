"""REST contracts, independent summaries and transactional bulk creation."""

import datetime as dt
from types import SimpleNamespace

import pytest
import test_whatsapp_groups_service as service_tests
from flask import Flask, g
from sqlalchemy import func, select

from library import whatsapp_groups_routes as routes
from library.db.models import Contact, WhatsappGroup, WhatsappGroupMember
from test_whatsapp_groups_service import (
    NOW, contact, members, message, participant, snapshot, sync,
)

db_session = service_tests.session


@pytest.fixture
def api(db_session, monkeypatch):
    session = db_session
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes, "_bridge", lambda: pytest.fail("No implicit bridge calls"))
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["AUTH_KIND"] = "user"

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind=app.config["AUTH_KIND"])

    sync(session, snapshot(participant(1, display_name="Żaneta"), participant(2), participant(3, phone=""),
                           parent_jid="community@g.us"), snapshot(jid="community@g.us", is_community=True))
    session.commit()
    return app.test_client(), session


@pytest.mark.parametrize("path", ["/whatsapp_groups", "/whatsapp_groups/1/members", "/whatsapp_groups/sync"])
def test_cors_preflight_is_not_rejected_without_auth(path):
    # Production skips auth for OPTIONS (server.py before_request), so g.auth is unset on a preflight.
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    client = app.test_client()
    assert client.options(path).status_code != 403
    assert client.get("/whatsapp_groups").status_code == 403  # a real request still needs a key


def test_list_groups_parent_conversation_counts(api):
    client, session = api
    contact(session, 1, phone_number="+48579060001")
    response = client.get("/whatsapp_groups")
    assert response.status_code == 200
    data = response.json
    assert data["summary"] == {"groups": 1, "communities": 1}
    group = next(g for g in data["groups"] if g["jid"] == "group@g.us")
    parent = next(g for g in data["groups"] if g["is_community"])
    assert group["parent_id"] == parent["id"]
    assert (group["active_members"], group["in_contacts"], group["missing"], group["unverified"]) == (3, 1, 1, 1)
    assert group["last_synced_at"] == NOW.isoformat()
    assert group["joins_7d"] == group["leaves_7d"] == 0


def test_members_filters_pagination_and_independent_summary(api):
    client, session = api
    contact(session, 1, phone_number="+48579060001")
    url = "/whatsapp_groups/1/members"
    data = client.get(url + "?status=missing&limit=1").json
    assert data["total"] == 1 and len(data["members"]) == 1
    assert data["summary"] == {"active": 3, "in_contacts": 1, "missing": 1, "unverified": 1}
    assert data["members"][0]["can_add"]
    assert client.get(url + "?q=zaneta").json["total"] == 1
    assert client.get(url + "?q=Kontakt").json["total"] == 1
    assert client.get(url + "?q=60002").json["total"] == 1
    data = client.get(url + "?status=unverified&offset=1&limit=999").json
    assert data["total"] == 1 and data["members"] == [] and data["limit"] == 500
    assert data["summary"]["active"] == 3


def test_left_all_and_events_order_filter_interval(api):
    client, session = api
    later = NOW + dt.timedelta(minutes=30)
    sync(session, snapshot(participant(2), participant(3, phone=""), participant(4)), now=later)
    assert client.get("/whatsapp_groups/1/members").json["total"] == 3
    assert client.get("/whatsapp_groups/1/members?state=all").json["total"] == 4
    data = client.get("/whatsapp_groups/1/members?state=left").json
    assert data["total"] == 1 and not data["members"][0]["can_add"]
    assert data["summary"]["active"] == 3
    data = client.get("/whatsapp_groups/1/events").json
    assert data["total"] == 2
    assert data["events"][0]["id"] > data["events"][1]["id"]
    assert all(e["detected_at"] == later.isoformat() and e["previous_synced_at"] == NOW.isoformat()
               for e in data["events"])
    contact(session, 1, phone_number="+48579060001")
    data = client.get("/whatsapp_groups/1/events?type=leave&limit=1").json
    assert data["total"] == 1 and data["events"][0]["contact"]["id"] == 1
    assert client.get("/whatsapp_groups/1/events?offset=1&limit=1").json["total"] == 2


@pytest.mark.parametrize("path", ["members", "events"])
def test_not_found(api, path):
    client, _ = api
    assert client.get(f"/whatsapp_groups/999/{path}").status_code == 404


@pytest.mark.parametrize("path", ["members?state=bad", "members?status=bad", "members?limit=abc",
                                  "events?type=bad", "events?offset=abc"])
def test_invalid_filters(api, path):
    client, _ = api
    assert client.get(f"/whatsapp_groups/1/{path}").status_code == 400


def test_add_created_linked_skipped_and_default_no_photo(api):
    client, session = api
    a, b, c = members(session)
    contact(session, 1, phone_number="+48579060002")
    message(session, "Żaneta", wa_sender_jid=a.jid)
    response = client.post("/whatsapp_groups/1/members/add_contacts",
                           json={"member_ids": [a.id, b.id, c.id, 999, a.id]})
    assert response.status_code == 200
    assert response.json["counts"] == {"created": 1, "linked_existing": 1, "skipped": 3, "error": 0}
    assert a.contact_id and b.contact_id == 1 and c.contact_id is None
    assert session.get(Contact, a.contact_id).display_label == "Żaneta"


def test_bulk_savepoint_failure_does_not_leak_or_undo_other_items(api, monkeypatch):
    client, session = api
    a, b, _ = members(session)
    original = routes.create_contact_from_member

    def fail_after_insert(session, member, **kwargs):
        result = original(session, member, **kwargs)
        if member.id == a.id:
            raise RuntimeError("private data and secret token")
        return result

    monkeypatch.setattr(routes, "create_contact_from_member", fail_after_insert)
    response = client.post("/whatsapp_groups/1/members/add_contacts", json={"member_ids": [a.id, b.id]})
    assert response.status_code == 200
    assert response.json["counts"] == {"created": 1, "linked_existing": 0, "skipped": 0, "error": 1}
    assert "private data" not in response.text and "secret token" not in response.text
    assert a.contact_id is None and b.contact_id is not None
    assert session.scalar(select(func.count()).select_from(Contact)) == 1


@pytest.mark.parametrize("body", [{}, [], {"member_ids": []}, {"member_ids": [True]},
                                  {"member_ids": [1] * 51}, {"member_ids": ["1"]},
                                  {"member_ids": [1], "fetch_photo": "false"},
                                  {"member_ids": [1], "category_id": True},
                                  {"member_ids": [1], "category_id": 999}])
def test_bulk_validation(api, body):
    client, _ = api
    assert client.post("/whatsapp_groups/1/members/add_contacts", json=body).status_code == 400


def test_bulk_50_allowed_and_group_404(api):
    client, _ = api
    assert client.post("/whatsapp_groups/1/members/add_contacts", json={"member_ids": [999] * 50}).status_code == 200
    assert client.post("/whatsapp_groups/999/members/add_contacts", json={"member_ids": [1]}).status_code == 404


def test_bulk_member_from_another_group_and_left_member_skipped(api):
    client, session = api
    a = members(session)[0]
    a.left_at = NOW
    other = WhatsappGroupMember(group_id=2, member_key="other", jid="other@lid", first_seen_at=NOW, last_seen_at=NOW)
    session.add(other)
    session.commit()
    response = client.post("/whatsapp_groups/1/members/add_contacts", json={"member_ids": [a.id, other.id]})
    assert response.json["counts"]["skipped"] == 2


def test_sync_job_and_service_key(api, monkeypatch):
    client, session = api
    client.application.config["AUTH_KIND"] = "service"
    calls = []

    def enqueue(s, kind):
        calls.append((s, kind))
        return SimpleNamespace(id="job-id")

    monkeypatch.setattr("library.job_queue.enqueue", enqueue)
    response = client.post("/whatsapp_groups/sync")
    assert response.status_code == 202 and response.json["job_id"] == "job-id"
    assert calls == [(session, "whatsapp_groups_sync")]
    assert client.get("/whatsapp_groups").status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/whatsapp_groups"), ("get", "/whatsapp_groups/1/members"),
                                         ("get", "/whatsapp_groups/1/events"),
                                         ("post", "/whatsapp_groups/sync"),
                                         ("post", "/whatsapp_groups/1/members/add_contacts")])
def test_auth_required(api, method, path):
    client, _ = api
    client.application.config["AUTH_KIND"] = "other"
    assert getattr(client, method)(path).status_code == 403


def test_unexpected_read_error_does_not_leak(api, monkeypatch):
    client, _ = api

    def fail(*args):
        raise RuntimeError("private database connection string")

    monkeypatch.setattr(routes, "_load", fail)
    response = client.get("/whatsapp_groups")
    assert response.status_code == 500 and "private database" not in response.text


def test_inactive_groups_hidden(api):
    client, session = api
    session.get(WhatsappGroup, 1).is_active = False
    assert len(client.get("/whatsapp_groups").json["groups"]) == 1
