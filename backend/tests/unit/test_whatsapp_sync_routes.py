"""Unit tests for the WhatsApp sync status/selection endpoints (library/whatsapp_sync_routes.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library.db.models import ChatConversation, WhatsappSyncChat


def _client(monkeypatch, kind="user"):
    from library.whatsapp_sync_routes import bp

    session = MagicMock()
    monkeypatch.setattr("library.whatsapp_sync_routes.get_scoped_session", lambda: session)
    monkeypatch.setattr("library.whatsapp_sync_routes._bridge", lambda: None)
    app = Flask(__name__)

    @app.before_request
    def _auth():
        g.auth = SimpleNamespace(kind=kind) if kind else None

    app.register_blueprint(bp)
    return app.test_client(), session


@pytest.mark.parametrize("kind", [None, "read_only"])
def test_endpoints_require_a_user_or_service_key(monkeypatch, kind):
    client, _ = _client(monkeypatch, kind)
    assert client.get("/whatsapp_sync/status").status_code == 403
    assert client.patch("/whatsapp_sync/chats/1", json={"enabled": True}).status_code == 403
    assert client.post("/whatsapp_sync/pairing/reset").status_code == 403


def test_selecting_a_chat_requires_a_boolean_and_a_known_conversation(monkeypatch):
    client, session = _client(monkeypatch)
    chat = WhatsappSyncChat(id=1, jid="1@s.whatsapp.net", display_name="Ala", enabled=False)
    session.get.side_effect = lambda model, pk: chat if model is WhatsappSyncChat else None

    assert client.patch("/whatsapp_sync/chats/1", json={"enabled": "yes"}).status_code == 400
    assert client.patch("/whatsapp_sync/chats/1", json={"conversation_id": 99}).status_code == 400
    assert chat.enabled is False

    ok = client.patch("/whatsapp_sync/chats/1", json={"enabled": True})
    assert ok.status_code == 200 and chat.enabled is True and ok.get_json()["chat"]["jid"] == "1@s.whatsapp.net"


def test_linking_an_existing_conversation_is_allowed(monkeypatch):
    client, session = _client(monkeypatch)
    chat = WhatsappSyncChat(id=1, jid="1@s.whatsapp.net", display_name="Ala", enabled=False)
    conv = ChatConversation(id=5, chat_key="k", display_name="K")
    session.get.side_effect = lambda model, pk: chat if model is WhatsappSyncChat else conv
    response = client.patch("/whatsapp_sync/chats/1", json={"conversation_id": 5, "enabled": True})
    assert response.status_code == 200 and chat.conversation_id == 5


def test_unknown_chat_is_404_and_pairing_without_bridge_is_409(monkeypatch):
    client, session = _client(monkeypatch)
    session.get.return_value = None
    assert client.patch("/whatsapp_sync/chats/7", json={"enabled": True}).status_code == 404
    assert client.post("/whatsapp_sync/pairing/reset").status_code == 409
    assert client.get("/whatsapp_sync/pairing/qr.png").status_code == 409
