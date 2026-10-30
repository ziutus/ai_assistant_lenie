"""Tests for the cached WhatsApp picture thumbnails of chat senders (library/chat_avatars.py)."""

from io import BytesIO
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("PIL")

from PIL import Image

from library import chat_avatars
from library.whatsapp_sync_service import BridgeError

JID = "48601379007@s.whatsapp.net"


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def exists(self, key):
        return key in self.objects

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data

    def presigned_get_url(self, key, expires_in=3600):
        return f"https://minio/{key}"


class FakeBridge:
    def __init__(self, result):
        self.result, self.calls = result, []

    def avatar(self, jid):
        self.calls.append(jid)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (40, 40), "red").save(out, format="PNG")
    return out.getvalue()


def test_avatar_jid_prefers_the_phone_jid_over_the_lid():
    both = SimpleNamespace(wa_sender_jid="1@lid", wa_sender_alt_jid=JID)
    lid_only = SimpleNamespace(wa_sender_jid="1@lid", wa_sender_alt_jid=None)
    none = SimpleNamespace(wa_sender_jid=None, wa_sender_alt_jid=None)
    assert chat_avatars.avatar_jid(both) == JID
    assert chat_avatars.avatar_jid(lid_only) == "1@lid"
    assert chat_avatars.avatar_jid(none) is None


def test_nothing_cached_yet_is_unknown():
    assert chat_avatars.cached(FakeStorage(), JID) == (None, False)


def test_a_picture_is_stored_as_a_jpeg_thumbnail_and_then_served_from_cache():
    storage, bridge = FakeStorage(), FakeBridge((_png(), "image/png"))

    url, done = chat_avatars.fetch_and_cache(storage, bridge, JID)

    assert done and url == f"https://minio/{chat_avatars.photo_key(JID)}"
    assert storage.objects[chat_avatars.photo_key(JID)][:2] == b"\xff\xd8"  # JPEG
    assert chat_avatars.cached(storage, JID) == (url, True)


def test_no_picture_is_remembered_so_the_bridge_is_not_asked_again():
    storage, bridge = FakeStorage(), FakeBridge((None, None))

    assert chat_avatars.fetch_and_cache(storage, bridge, JID) == (None, True)
    assert chat_avatars.cached(storage, JID) == (None, True)
    assert bridge.calls == [JID]


def test_a_bridge_error_caches_nothing_so_it_is_retried():
    storage = FakeStorage()

    assert chat_avatars.fetch_and_cache(storage, FakeBridge(BridgeError("down")), JID) == (None, False)
    assert storage.objects == {}


def test_an_unreadable_image_counts_as_no_picture():
    storage = FakeStorage()

    assert chat_avatars.fetch_and_cache(storage, FakeBridge((b"not an image", "image/jpeg")), JID) == (None, True)
    assert chat_avatars.none_key(JID) in storage.objects
