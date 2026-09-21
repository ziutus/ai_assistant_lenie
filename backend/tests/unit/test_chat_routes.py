"""Unit tests for chat log browsing endpoints (library/chat_routes.py).

Same pattern as test_contact_routes.py: call the Flask blueprint through a
bare test client with get_scoped_session monkeypatched to a MagicMock — no
real DB needed.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask


def _conversation_api(monkeypatch):
    from library.chat_routes import bp
    from library.db.models import ChatConversation

    session = MagicMock()
    conversation = ChatConversation(id=2, chat_key="tuwima-gardens/czat-ogolny", display_name="Tuwima Gardens")
    session.get.return_value = conversation
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.scalars.return_value.all.return_value = []
    monkeypatch.setattr("library.chat_routes.get_scoped_session", lambda: session)

    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client(), session


class TestChatMessagesContactFilter:
    def test_contact_id_adds_contact_filter_to_query(self, monkeypatch):
        client, session = _conversation_api(monkeypatch)

        response = client.get("/chat_conversations/2/messages", query_string={"contact_id": "380"})

        assert response.status_code == 200
        sqls = [str(call.args[0]) for call in session.execute.call_args_list]
        assert any("chat_messages.contact_id =" in sql for sql in sqls)

    def test_without_contact_id_query_param_has_no_contact_filter(self, monkeypatch):
        client, session = _conversation_api(monkeypatch)

        response = client.get("/chat_conversations/2/messages")

        assert response.status_code == 200
        sqls = [str(call.args[0]) for call in session.execute.call_args_list]
        assert not any("chat_messages.contact_id =" in sql for sql in sqls)
