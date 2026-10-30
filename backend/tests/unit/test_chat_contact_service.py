"""Tests for adding a chat sender to the contact book and for reading links out of messages.

In-memory SQLite, no bridge, no private messages. The full create path touches Contact
(JSONB columns), so what is covered here is the sender identity rules and message linking."""

import datetime as dt

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from library import chat_contact_service as svc
from library.chat_routes import urls_in_text
from library.db.models import ChatConversation, ChatMessage
from library.whatsapp_sync_service import BridgeClient, BridgeError


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    ChatConversation.__table__.create(engine)
    ChatMessage.__table__.create(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        s.add(ChatConversation(id=1, chat_key="g", display_name="Sąsiedzi"))
        s.add(ChatConversation(id=2, chat_key="h", display_name="Wędkarze"))
        s.flush()
        yield s


_COUNTER = iter(range(1, 1000))


def _msg(session, *, conversation_id=1, name="Ala", jid=None, alt=None, from_me=False, contact_id=None,
         message_type="text", content="hej"):
    n = next(_COUNTER)
    row = ChatMessage(
        conversation_id=conversation_id, sender_name_raw=name, wa_sender_jid=jid, wa_sender_alt_jid=alt,
        is_from_me=from_me, contact_id=contact_id, sent_at=dt.datetime(2026, 10, 29, 12, 0), message_type=message_type,
        content=content, dedup_hash=f"h{n}", source="sync" if jid else "import",
    )
    session.add(row)
    session.flush()
    return row


class TestSenderIdentity:
    def test_phone_from_alt_jid_wins_over_lid(self, session):
        m = _msg(session, jid="123456789012@lid", alt="48579063654@s.whatsapp.net")
        assert svc.sender_phone(m) == "48579063654"

    def test_phone_from_label_of_a_txt_import(self, session):
        assert svc.sender_phone(_msg(session, name="+48 579 063 654")) == "48579063654"

    def test_no_phone_for_a_bare_lid(self, session):
        assert svc.sender_phone(_msg(session, jid="123456789012@lid")) is None

    def test_nickname_is_the_push_name_not_a_number(self, session):
        assert svc.sender_nickname(_msg(session, name="Ala z Bloku")) == "Ala z Bloku"
        assert svc.sender_nickname(_msg(session, name="+48579063654")) is None
        assert svc.sender_nickname(_msg(session, name="WhatsApp 1234")) is None


class TestLinkSenderMessages:
    def test_links_every_unresolved_message_of_that_sender_across_chats(self, session):
        jid = "48579063654@s.whatsapp.net"
        first = _msg(session, jid=jid)
        other_chat = _msg(session, conversation_id=2, jid=jid)
        stranger = _msg(session, jid="48600600600@s.whatsapp.net", name="Ktoś")
        already = _msg(session, jid=jid, contact_id=7)
        mine = _msg(session, jid=jid, from_me=True)

        assert svc.link_sender_messages(session, first, 42) == 2
        session.expire_all()
        assert {first.contact_id, other_chat.contact_id} == {42}
        assert stranger.contact_id is None and already.contact_id == 7 and mine.contact_id is None

    def test_without_a_jid_only_the_same_label_in_the_same_chat(self, session):
        a = _msg(session, name="Ala")
        same = _msg(session, name="Ala")
        elsewhere = _msg(session, conversation_id=2, name="Ala")

        assert svc.link_sender_messages(session, a, 5) == 2
        session.expire_all()
        assert same.contact_id == 5 and elsewhere.contact_id is None


def test_urls_in_text_keeps_order_drops_punctuation_and_repeats():
    text = "zobacz https://youtu.be/abc, a potem (https://example.com/a?b=1). Jeszcze https://youtu.be/abc"
    assert urls_in_text(text) == ["https://youtu.be/abc", "https://example.com/a?b=1"]
    assert urls_in_text(None) == []


class _Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class _Http:
    def __init__(self, response):
        self.response, self.calls = response, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get("params")))
        return self.response


class TestBridgeAvatar:
    def test_returns_bytes_and_type(self):
        http = _Http(_Resp(200, b"\xff\xd8jpeg", {"Content-Type": "image/jpeg"}))
        assert BridgeClient("http://b", "t", http=http).avatar("48@s.whatsapp.net") == (b"\xff\xd8jpeg", "image/jpeg")
        assert http.calls[0] == ("GET", "http://b/avatar", {"jid": "48@s.whatsapp.net"})

    def test_404_means_no_picture(self):
        assert BridgeClient("http://b", "t", http=_Http(_Resp(404))).avatar("48@s.whatsapp.net") == (None, None)

    def test_server_error_is_a_bridge_error(self):
        with pytest.raises(BridgeError):
            BridgeClient("http://b", "t", http=_Http(_Resp(502))).avatar("48@s.whatsapp.net")


def test_selecting_still_works(session):
    _msg(session)
    assert session.scalar(select(ChatMessage.id)) is not None


class TestMentionMap:
    def test_linked_contact_wins_and_is_resolved_by_lid(self, session, monkeypatch):
        from library import chat_routes

        monkeypatch.setattr(session, "get", lambda model, pk: object())
        monkeypatch.setattr(chat_routes, "_contact_summary", lambda c: {"id": 492, "display_name": "Bartłomiej Karalus"})
        _msg(session, name="+48572317523", jid="113344723824824@lid", alt="48572317523@s.whatsapp.net", contact_id=492)

        result = chat_routes.mention_map(session, ["@113344723824824 żyjesz, urlop?", None])

        assert result == {"113344723824824": {"contact": {"id": 492, "display_name": "Bartłomiej Karalus"}, "name": None}}

    def test_falls_back_to_the_whatsapp_name_and_skips_unknown_or_numeric(self, session):
        from library import chat_routes

        _msg(session, name="Ala z Bloku", jid="111111111111@lid")
        _msg(session, name="+48600600600", jid="222222222222@lid")

        result = chat_routes.mention_map(session, ["@111111111111 @222222222222 @333333333333 @12"])

        assert result == {"111111111111": {"contact": None, "name": "Ala z Bloku"}}

    def test_no_mentions_no_query(self, session):
        from library import chat_routes

        assert chat_routes.mention_map(session, ["bez wzmianek", None]) == {}
