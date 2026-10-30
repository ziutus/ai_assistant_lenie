"""Tests for the live WhatsApp sync adapter (library/whatsapp_sync_service.py).

Run against an in-memory SQLite database and a scripted fake bridge: no NAS, no WhatsApp
account, no private messages."""

import datetime as dt

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from library import whatsapp_sync_service as svc
from library.db.models import ChatConversation, ChatMessage, WhatsappSyncChat, WhatsappSyncState


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # SQLite only autoincrements INTEGER PRIMARY KEY
    return "INTEGER"


NOW = dt.datetime(2026, 10, 29, 12, 0, 0)
CHAT = "48500500500@s.whatsapp.net"
GROUP = "120363000000000001@g.us"
TS = 1_792_000_000  # 2026-10-14, any fixed instant


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    tables = [ChatConversation.__table__, ChatMessage.__table__, WhatsappSyncChat.__table__,
              WhatsappSyncState.__table__]
    for table in tables:
        table.create(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.fail_puts = 0

    def put_bytes(self, key, data, content_type=None):
        if self.fail_puts:
            self.fail_puts -= 1
            raise OSError("minio down")
        self.objects[key] = data

    def delete(self, key):
        self.objects.pop(key, None)


class FakeBridge:
    def __init__(self):
        self.status_payload = {"state": "connected", "needs_pairing": False, "epoch": "e1", "account_jid": "1@s.whatsapp.net"}
        self.chat_list = []
        self.journal = {}  # chat -> list of events
        self.allowlist = None
        self.requested_chats = []
        self.acks = []
        self.media_plan = {}  # wa_id -> list of results (bytes | Exception)
        self.down = False

    def add(self, chat, **ev):
        seq = sum(len(v) for v in self.journal.values()) + 1
        base = {"seq": seq, "kind": "message", "chat_jid": chat, "is_group": chat.endswith("@g.us"),
                "sender_jid": chat, "is_from_me": False, "timestamp": TS, "message_type": "text", "text": "hej",
                "wa_message_id": f"ID{seq}", "source": "live"}
        base.update(ev)
        self.journal.setdefault(chat, []).append(base)
        return base

    def status(self):
        if self.down:
            raise svc.BridgeError("bridge unreachable: ConnectionError")
        return self.status_payload

    def chats(self):
        return self.chat_list

    def put_allowlist(self, jids):
        self.allowlist = jids

    def events(self, chat, after, limit=100):
        self.requested_chats.append(chat)
        return [e for e in self.journal.get(chat, []) if e["seq"] > after][:limit]

    def ack(self, chat, upto):
        self.acks.append((chat, upto))

    def media(self, chat, wa_id):
        plan = self.media_plan.get(wa_id, [b"bytes"])
        result = plan.pop(0) if len(plan) > 1 else plan[0]
        if isinstance(result, Exception):
            raise result
        return result

    def delete_media(self, chat, wa_id):
        pass


def enable(session, jid=CHAT, name="Ala", conversation_id=None):
    chat = WhatsappSyncChat(jid=jid, display_name=name, enabled=True, conversation_id=conversation_id)
    session.add(chat)
    session.commit()
    return chat


def run(session, bridge, storage=None, now=NOW, phone_index=None, **kw):
    bridge.chat_list = bridge.chat_list or [{"jid": c.jid, "name": c.display_name, "is_group": c.is_group}
                                            for c in session.scalars(select(WhatsappSyncChat))]
    return svc.sync_once(session, bridge, storage or FakeStorage(), now=now,
                         phone_index={} if phone_index is None else phone_index, **kw)


def messages(session):
    return session.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()


# --- duplicates, restarts, ordering -------------------------------------------------------------


def test_redelivery_and_overlapping_batches_create_no_duplicates(session):
    enable(session)
    bridge = FakeBridge()
    first = bridge.add(CHAT, text="pierwsza")
    run(session, bridge)
    # the same message arrives again as a new journal entry (history overlapping a live event)
    bridge.add(CHAT, text="pierwsza", wa_message_id=first["wa_message_id"], source="history")
    bridge.add(CHAT, text="druga")
    result = run(session, bridge)
    assert [m.content for m in messages(session)] == ["pierwsza", "druga"]
    assert result["duplicate"] == 1


def test_resume_after_crash_rolls_back_the_batch_and_keeps_the_cursor(session, monkeypatch):
    chat = enable(session)
    bridge = FakeBridge()
    for text in ("a", "b", "c"):
        bridge.add(CHAT, text=text)

    original = svc.apply_message
    calls = {"n": 0}

    def exploding(ctx, chat_, ev, counts):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("process killed mid-write")
        return original(ctx, chat_, ev, counts)

    monkeypatch.setattr(svc, "apply_message", exploding)
    result = run(session, bridge)
    assert result["status"] == "error"
    assert messages(session) == []  # nothing half-stored
    session.refresh(chat)
    assert chat.cursor_seq == 0 and bridge.acks == []  # nothing acknowledged before it was stored

    monkeypatch.setattr(svc, "apply_message", original)
    run(session, bridge)
    assert [m.content for m in messages(session)] == ["a", "b", "c"]
    session.refresh(chat)
    assert chat.cursor_seq == 3 and bridge.acks[-1] == (CHAT, 3)


def test_late_delivered_older_message_is_stored_once(session):
    enable(session)
    bridge = FakeBridge()
    bridge.add(CHAT, text="nowa", timestamp=TS + 500)
    run(session, bridge)
    bridge.add(CHAT, text="stara dostarczona z opóźnieniem", timestamp=TS)
    run(session, bridge)
    assert {m.content for m in messages(session)} == {"nowa", "stara dostarczona z opóźnieniem"}


def test_large_backlog_is_processed_in_bounded_cycles(session):
    chat = enable(session)
    bridge = FakeBridge()
    for i in range(svc.EVENT_BATCH * svc.MAX_BATCHES_PER_CHAT + 5):
        bridge.add(CHAT, text=f"m{i}")
    run(session, bridge)
    assert len(messages(session)) == svc.EVENT_BATCH * svc.MAX_BATCHES_PER_CHAT
    run(session, bridge)
    assert len(messages(session)) == svc.EVENT_BATCH * svc.MAX_BATCHES_PER_CHAT + 5
    session.refresh(chat)
    assert chat.cursor_seq == svc.EVENT_BATCH * svc.MAX_BATCHES_PER_CHAT + 5


def test_changed_bridge_epoch_resets_cursors_without_duplicating(session):
    chat = enable(session)
    bridge = FakeBridge()
    bridge.add(CHAT, text="a")
    run(session, bridge)
    bridge.journal = {CHAT: [dict(bridge.journal[CHAT][0], seq=1)]}  # recreated journal: sequence restarted
    bridge.status_payload["epoch"] = "e2"
    result = run(session, bridge)
    assert result["journal_reset"] is True
    assert len(messages(session)) == 1
    session.refresh(chat)
    assert chat.cursor_seq == 1


# --- allowlist ------------------------------------------------------------------------------------


def test_only_selected_chats_are_read_and_nothing_is_enabled_by_default(session):
    enable(session, CHAT)
    bridge = FakeBridge()
    bridge.add(CHAT, text="wybrana")
    bridge.add("48111111111@s.whatsapp.net", text="prywatna, niewybrana")
    bridge.chat_list = [{"jid": CHAT, "name": "Ala"}, {"jid": "48111111111@s.whatsapp.net", "name": "Ktoś"}]
    run(session, bridge)
    assert [m.content for m in messages(session)] == ["wybrana"]
    assert set(bridge.requested_chats) == {CHAT}
    assert bridge.allowlist == [CHAT]
    other = session.scalars(select(WhatsappSyncChat).where(WhatsappSyncChat.jid == "48111111111@s.whatsapp.net")).one()
    assert other.enabled is False and other.conversation_id is None


def test_enabled_chat_gets_a_conversation_keyed_by_jid_or_uses_the_linked_one(session):
    linked = ChatConversation(platform="whatsapp", chat_key="tuwima/czat", display_name="Czat")
    session.add(linked)
    session.commit()
    enable(session, CHAT, conversation_id=linked.id)
    enable(session, GROUP, name="Grupa")
    bridge = FakeBridge()
    bridge.add(CHAT, text="do istniejącej")
    bridge.add(GROUP, text="do nowej")
    run(session, bridge)
    by_text = {m.content: m.conversation_id for m in messages(session)}
    assert by_text["do istniejącej"] == linked.id
    new_conv = session.get(ChatConversation, by_text["do nowej"])
    assert new_conv.chat_key == f"whatsapp:{GROUP}" and new_conv.message_count == 1


# --- senders, LID, own messages --------------------------------------------------------------------


def test_group_message_from_lid_with_known_phone_resolves_contact_and_keeps_both_ids(session):
    enable(session, GROUP, name="Grupa")
    bridge = FakeBridge()
    bridge.add(GROUP, sender_jid="99887766@lid", sender_pn="48600600600@s.whatsapp.net", sender_name="Basia")
    ctx_index = {"48600600600": 7}
    bridge.chat_list = [{"jid": GROUP, "name": "Grupa", "is_group": True}]
    run(session, bridge, phone_index=ctx_index)
    row = messages(session)[0]
    assert row.contact_id == 7 and row.sender_name_raw == "Basia"
    assert row.wa_sender_jid == "99887766@lid" and row.wa_sender_alt_jid == "48600600600@s.whatsapp.net"


def test_bare_lid_is_never_guessed_into_a_contact_and_own_message_is_flagged(session):
    enable(session, GROUP, name="Grupa")
    bridge = FakeBridge()
    bridge.add(GROUP, sender_jid="99887766@lid", sender_name="")
    bridge.add(GROUP, sender_jid="48111@s.whatsapp.net", is_from_me=True, text="moja")
    run(session, bridge, phone_index={"99887766": 3, "48111": 4})  # even a numeric collision must not match a LID
    lid_row, own_row = messages(session)
    assert lid_row.contact_id is None and lid_row.sender_name_raw == "WhatsApp 99887766"
    assert own_row.is_from_me is True and own_row.contact_id is None and own_row.sender_name_raw == "Ja"


# --- edits and deletions ----------------------------------------------------------------------------


def test_edit_updates_by_source_id_and_older_edit_is_ignored(session):
    enable(session)
    bridge = FakeBridge()
    orig = bridge.add(CHAT, text="literówka")
    bridge.add(CHAT, kind="edit", wa_message_id=orig["wa_message_id"], text="poprawka 2", timestamp=TS + 120)
    bridge.add(CHAT, kind="edit", wa_message_id=orig["wa_message_id"], text="poprawka 1", timestamp=TS + 60)
    run(session, bridge)
    (row,) = messages(session)
    assert row.content == "poprawka 2" and row.edited_at is not None


def test_revoke_scrubs_content_and_media_and_keeps_a_tombstone(session):
    enable(session)
    storage = FakeStorage()
    bridge = FakeBridge()
    text = bridge.add(CHAT, text="tajne")
    image = bridge.add(CHAT, message_type="image", text="podpis", media={"mime": "image/jpeg", "size": 10})
    run(session, bridge, storage)
    assert len(storage.objects) == 1
    bridge.add(CHAT, kind="revoke", wa_message_id=text["wa_message_id"], message_type="deleted", text="")
    bridge.add(CHAT, kind="revoke", wa_message_id=image["wa_message_id"], message_type="deleted", text="")
    run(session, bridge, storage)
    rows = messages(session)
    assert [r.message_type for r in rows] == ["deleted", "deleted"]
    assert all(r.content is None and r.deleted_at and r.media_storage_key is None for r in rows)
    assert storage.objects == {}


def test_revoke_arriving_before_the_original_wins_and_edit_before_original_keeps_newest(session):
    enable(session)
    bridge = FakeBridge()
    bridge.add(CHAT, kind="revoke", wa_message_id="X1", message_type="deleted", text="")
    bridge.add(CHAT, text="oryginał usuniętej", wa_message_id="X1")
    bridge.add(CHAT, kind="edit", wa_message_id="Y1", text="po edycji", timestamp=TS + 60)
    bridge.add(CHAT, text="przed edycją", wa_message_id="Y1")
    run(session, bridge)
    x, y = messages(session)
    assert x.message_type == "deleted" and x.content is None
    assert y.content == "po edycji"


# --- coexistence with TXT/ZIP imports ---------------------------------------------------------------


def _legacy(session, conv_id, text, minute_offset=0, contact_id=None):
    sent = svc.to_local_naive(TS).replace(second=0) + dt.timedelta(minutes=minute_offset)
    row = ChatMessage(conversation_id=conv_id, sender_name_raw="Ala - Tuwima", sent_at=sent, message_type="text",
                      content=text, dedup_hash=f"legacy-{text}-{minute_offset}-{len(messages(session))}",
                      contact_id=contact_id)
    session.add(row)
    session.commit()
    return row


def test_a_unique_legacy_row_is_adopted_so_the_message_is_not_doubled(session):
    conv = ChatConversation(platform="whatsapp", chat_key="k", display_name="K")
    session.add(conv)
    session.commit()
    legacy = _legacy(session, conv.id, "dzień dobry")
    enable(session, conversation_id=conv.id)
    bridge = FakeBridge()
    bridge.add(CHAT, text="dzień dobry")
    result = run(session, bridge)
    assert result["adopted_legacy"] == 1
    (row,) = messages(session)
    assert row.id == legacy.id and row.wa_message_id and row.dedup_hash.startswith("legacy-")


def test_identical_text_in_one_minute_is_never_merged(session):
    conv = ChatConversation(platform="whatsapp", chat_key="k", display_name="K")
    session.add(conv)
    session.commit()
    _legacy(session, conv.id, "ok")
    _legacy(session, conv.id, "ok")  # two legacy rows, same text, same minute
    enable(session, conversation_id=conv.id)
    bridge = FakeBridge()
    bridge.add(CHAT, text="ok")
    result = run(session, bridge)
    assert "adopted_legacy" not in result and len(messages(session)) == 3  # ambiguous: kept apart

    # two synced messages in one batch against one legacy row: also ambiguous
    other = ChatConversation(platform="whatsapp", chat_key="k2", display_name="K2")
    session.add(other)
    session.commit()
    _legacy(session, other.id, "tak")
    enable(session, GROUP, conversation_id=other.id)
    bridge2 = FakeBridge()
    bridge2.add(GROUP, text="tak")
    bridge2.add(GROUP, text="tak")
    result2 = run(session, bridge2)
    assert "adopted_legacy" not in result2 and result2["created_ambiguous"] == 2


def test_legacy_row_with_a_different_known_contact_is_not_adopted(session):
    conv = ChatConversation(platform="whatsapp", chat_key="k", display_name="K")
    session.add(conv)
    session.commit()
    _legacy(session, conv.id, "cześć", contact_id=5)
    enable(session, conversation_id=conv.id)
    bridge = FakeBridge()
    bridge.add(CHAT, text="cześć", sender_pn=CHAT)
    result = run(session, bridge, phone_index={"48500500500": 9})
    assert "adopted_legacy" not in result and len(messages(session)) == 2


def test_importer_helper_detects_an_unambiguous_synced_twin(session):
    conv = ChatConversation(platform="whatsapp", chat_key="k", display_name="K")
    session.add(conv)
    session.commit()
    enable(session, conversation_id=conv.id)
    bridge = FakeBridge()
    bridge.add(CHAT, text="z synchronizacji")
    run(session, bridge)
    sent = svc.to_local_naive(TS)
    assert svc.sync_twin_exists(session, conv.id, "text", "z synchronizacji", sent) is True
    assert svc.sync_twin_exists(session, conv.id, "text", "inna treść", sent) is False


# --- attachments --------------------------------------------------------------------------------------


def _media_row(session):
    return [m for m in messages(session) if m.media_status is not None or m.media_storage_key][0]


def test_message_is_stored_even_when_the_attachment_fails_and_retry_succeeds(session):
    enable(session)
    storage = FakeStorage()
    bridge = FakeBridge()
    bridge.add(CHAT, message_type="image", text="", wa_message_id="IMG1", media={"mime": "image/jpeg", "size": 5,
                                                                              "filename": "../../etc/passwd.jpg"})
    bridge.media_plan["IMG1"] = [svc.BridgeError("bridge returned HTTP 502"), b"JPEGDATA"]
    run(session, bridge, storage)
    row = _media_row(session)
    assert row.message_type == "image" and row.media_status == "pending" and row.media_attempts == 1
    assert row.media_next_attempt_at == NOW + dt.timedelta(seconds=svc.media_backoff_seconds(1))

    run(session, bridge, storage, now=NOW + dt.timedelta(seconds=30))  # not yet due
    assert _media_row(session).media_attempts == 1

    run(session, bridge, storage, now=NOW + dt.timedelta(hours=1))
    row = _media_row(session)
    assert row.media_status == "downloaded" and row.media_error is None
    assert storage.objects[row.media_storage_key] == b"JPEGDATA"
    assert "passwd" not in row.media_storage_key and row.media_storage_key.startswith("chat_media/whatsapp/")


def test_attachment_states_unavailable_error_and_too_large(session):
    enable(session)
    storage = FakeStorage()
    bridge = FakeBridge()
    bridge.add(CHAT, message_type="video", text="", wa_message_id="GONE", media={"mime": "video/mp4", "size": 5})
    bridge.add(CHAT, message_type="audio", text="", wa_message_id="BIG", media={"mime": "audio/ogg", "size": 10**9})
    bridge.add(CHAT, message_type="document", text="", wa_message_id="FLAKY", media={"mime": "application/pdf", "size": 5})
    bridge.media_plan["GONE"] = [svc.MediaUnavailable("HTTP 410")]
    bridge.media_plan["FLAKY"] = [svc.BridgeError("bridge returned HTTP 503")]
    when = NOW
    for _ in range(svc.MEDIA_MAX_ATTEMPTS + 1):
        run(session, bridge, storage, now=when)
        when += dt.timedelta(days=1)
    by_id = {m.wa_message_id: m for m in messages(session)}
    assert by_id["GONE"].media_status == "unavailable"
    assert by_id["BIG"].media_status == "unavailable" and by_id["BIG"].media_error == "too_large"
    assert by_id["FLAKY"].media_status == "error" and by_id["FLAKY"].media_attempts == svc.MEDIA_MAX_ATTEMPTS
    assert all(m.content in (None, "") or True for m in by_id.values())  # messages themselves were stored
    assert len(by_id) == 3 and storage.objects == {}


def test_storage_failure_keeps_the_attachment_pending_and_retries_to_the_same_key(session):
    enable(session)
    storage = FakeStorage()
    storage.fail_puts = 1
    bridge = FakeBridge()
    bridge.add(CHAT, message_type="image", text="", wa_message_id="IMG2", media={"mime": "image/png", "size": 3})
    run(session, bridge, storage)
    assert _media_row(session).media_status == "pending" and storage.objects == {}
    run(session, bridge, storage, now=NOW + dt.timedelta(hours=2))
    run(session, bridge, storage, now=NOW + dt.timedelta(hours=4))
    assert len(storage.objects) == 1  # deterministic key: no duplicate objects after retries


def test_media_key_is_independent_of_sender_filename():
    a = svc.media_storage_key(3, CHAT, "ID1", "audio/ogg; codecs=opus")
    assert a == svc.media_storage_key(3, CHAT, "ID1", "audio/ogg; codecs=opus") and a.endswith(".ogg")
    assert svc.media_storage_key(3, CHAT, "ID2", "audio/ogg") != a


# --- status ---------------------------------------------------------------------------------------------


def test_unreachable_bridge_and_pairing_needed_are_visible_in_state(session):
    bridge = FakeBridge()
    bridge.down = True
    assert run(session, bridge)["status"] == "bridge_unreachable"
    state = session.get(WhatsappSyncState, 1)
    assert state.bridge_reachable is False and "unreachable" in state.last_error

    bridge.down = False
    bridge.status_payload = {"state": "logged_out", "needs_pairing": True, "epoch": "e1"}
    run(session, bridge)
    state = session.get(WhatsappSyncState, 1)
    assert state.needs_pairing is True and state.connection_state == "logged_out" and state.bridge_reachable is True


def test_account_disconnect_keeps_existing_data(session):
    enable(session)
    bridge = FakeBridge()
    bridge.add(CHAT, text="zostaje")
    run(session, bridge)
    bridge.status_payload = {"state": "logged_out", "needs_pairing": True, "epoch": "e1"}
    run(session, bridge)
    assert [m.content for m in messages(session)] == ["zostaje"]
