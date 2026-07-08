"""Unit tests for Etap 8: API keys (library/auth.py + library/api_key_routes.py).

Covers key generation/hashing, the in-process cache (TTL, negative entries,
invalidation), resolve_api_key (user/service/unknown/inactive, no DB
on cache hits, last_used_at throttling) and the /whoami + /api_keys endpoints
(service-only management) — all with mocked sessions, no DB.
"""

import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import api_key_routes as akr  # noqa: E402
from library import auth  # noqa: E402
from library.auth import (  # noqa: E402
    AuthContext,
    CacheEntry,
    InProcessApiKeyCache,
    create_api_key,
    deactivate_api_key,
    generate_api_key,
    hash_api_key,
    resolve_api_key,
)
from library.db.models import ApiKey, User  # noqa: E402


READER_USER = User(username="krzysztof", display_name="Krzysztof")
READER_USER.id = 1


def _make_key_row(**overrides) -> ApiKey:
    row = ApiKey(
        kind="user", user_id=READER_USER.id, name="frontend-krzysztof",
        key_hash="a" * 64, key_prefix="lk_usr_abcde", active=True,
    )
    row.id = 10
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


@pytest.fixture(autouse=True)
def clean_auth_state():
    auth.invalidate_cache()
    auth._last_used_written.clear()
    yield
    auth.invalidate_cache()
    auth._last_used_written.clear()


# ---------------------------------------------------------------------------
# Key generation & hashing
# ---------------------------------------------------------------------------


class TestGenerateApiKey:
    def test_user_key_format(self):
        plaintext, key_hash, key_prefix = generate_api_key("user")
        assert plaintext.startswith("lk_usr_")
        assert key_hash == hash_api_key(plaintext)
        assert len(key_hash) == 64
        assert key_prefix == plaintext[: auth.KEY_PREFIX_LEN]

    def test_service_key_format(self):
        plaintext, _, _ = generate_api_key("service")
        assert plaintext.startswith("lk_svc_")

    def test_keys_are_unique(self):
        assert generate_api_key("user")[0] != generate_api_key("user")[0]

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError):
            generate_api_key("admin")


# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------


class TestInProcessCache:
    def test_set_get(self):
        cache = InProcessApiKeyCache()
        ctx = AuthContext(kind="service", key_id=1, key_name="x", user_id=None)
        cache.set("h1", CacheEntry(ctx, time.monotonic() + 60))
        assert cache.get("h1").context is ctx

    def test_expired_entry_is_dropped(self):
        cache = InProcessApiKeyCache()
        cache.set("h1", CacheEntry(None, time.monotonic() - 1))
        assert cache.get("h1") is None

    def test_invalidate_single_and_all(self):
        cache = InProcessApiKeyCache()
        entry = CacheEntry(None, time.monotonic() + 60)
        cache.set("h1", entry)
        cache.set("h2", entry)
        cache.invalidate("h1")
        assert cache.get("h1") is None
        assert cache.get("h2") is entry
        cache.invalidate()
        assert cache.get("h2") is None


# ---------------------------------------------------------------------------
# resolve_api_key
# ---------------------------------------------------------------------------


class TestResolveApiKey:
    def _session_returning(self, row):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = row
        return session

    def test_user_key_resolved(self):
        session = self._session_returning(_make_key_row())
        ctx = resolve_api_key(lambda: session, "raw-key")
        assert ctx == AuthContext(kind="user", key_id=10, key_name="frontend-krzysztof", user_id=1)

    def test_service_key_resolved(self):
        row = _make_key_row(kind="service", user_id=None, name="chrome-extension", id=11)
        ctx = resolve_api_key(lambda: self._session_returning(row), "raw-key")
        assert ctx.kind == "service"
        assert ctx.user_id is None
        assert not ctx.is_legacy

    def test_unknown_key_returns_none(self):
        assert resolve_api_key(lambda: self._session_returning(None), "bad") is None

    def test_cache_hit_skips_db(self):
        session = self._session_returning(_make_key_row())
        resolve_api_key(lambda: session, "raw-key")
        factory2 = MagicMock()
        ctx = resolve_api_key(factory2, "raw-key")
        assert ctx.key_id == 10
        factory2.assert_not_called()  # positive hit + throttled last_used — no session at all

    def test_negative_cache_skips_db(self):
        resolve_api_key(lambda: self._session_returning(None), "bad")
        factory2 = MagicMock()
        assert resolve_api_key(factory2, "bad") is None
        factory2.assert_not_called()

    def test_invalidate_cache_forces_db_lookup(self):
        resolve_api_key(lambda: self._session_returning(_make_key_row()), "raw-key")
        auth.invalidate_cache()
        session2 = self._session_returning(None)
        assert resolve_api_key(lambda: session2, "raw-key") is None
        session2.execute.assert_called_once()

    def test_last_used_written_once_then_throttled(self):
        session = self._session_returning(_make_key_row())
        resolve_api_key(lambda: session, "raw-key")
        # select + update in the first resolve, then nothing new
        assert session.execute.call_count == 2
        session.commit.assert_called_once()
        resolve_api_key(lambda: session, "raw-key")
        assert session.execute.call_count == 2


# ---------------------------------------------------------------------------
# create / deactivate
# ---------------------------------------------------------------------------


class TestCreateApiKey:
    def _session(self, user=READER_USER, duplicate=None):
        session = MagicMock()
        session.get.side_effect = lambda model, pk: user if (model is User and pk == user.id) else None
        session.execute.return_value.scalar_one_or_none.return_value = duplicate
        session.add.side_effect = lambda obj: setattr(obj, "id", 77)
        return session

    def test_create_user_key(self):
        session = self._session()
        row, plaintext = create_api_key(session, kind="user", name="frontend-krzysztof", user_id=1)
        assert plaintext.startswith("lk_usr_")
        assert row.key_hash == hash_api_key(plaintext)
        assert row.key_prefix == plaintext[: auth.KEY_PREFIX_LEN]
        assert row.user_id == 1
        session.commit.assert_called_once()

    def test_create_service_key(self):
        row, plaintext = create_api_key(self._session(), kind="service", name="chrome-extension")
        assert plaintext.startswith("lk_svc_")
        assert row.user_id is None

    @pytest.mark.parametrize("kwargs", [
        {"kind": "admin", "name": "x"},
        {"kind": "user", "name": "x", "user_id": None},          # user key needs user_id
        {"kind": "user", "name": "x", "user_id": 99},            # unknown user
        {"kind": "service", "name": "x", "user_id": 1},          # service must not have user_id
        {"kind": "service", "name": ""},                          # empty name
        {"kind": "service", "name": "y" * 101},                   # name too long
    ])
    def test_validation_errors(self, kwargs):
        with pytest.raises(ValueError):
            create_api_key(self._session(), **kwargs)

    def test_duplicate_name_raises(self):
        with pytest.raises(ValueError, match="already exists"):
            create_api_key(self._session(duplicate=_make_key_row()), kind="service", name="frontend-krzysztof")

    def test_create_invalidates_cache(self):
        auth.get_cache().set("h", CacheEntry(None, time.monotonic() + 60))
        create_api_key(self._session(), kind="service", name="fresh")
        assert auth.get_cache().get("h") is None


class TestDeactivateApiKey:
    def test_deactivate(self):
        row = _make_key_row()
        session = MagicMock()
        session.get.return_value = row
        result = deactivate_api_key(session, 10)
        assert result.active is False
        session.commit.assert_called_once()

    def test_missing_key_raises(self):
        session = MagicMock()
        session.get.return_value = None
        with pytest.raises(ValueError, match="not found"):
            deactivate_api_key(session, 999)


# ---------------------------------------------------------------------------
# /whoami + /api_keys endpoints
# ---------------------------------------------------------------------------


USER_AUTH = AuthContext(kind="user", key_id=10, key_name="frontend-krzysztof", user_id=1)
SERVICE_AUTH = AuthContext(kind="service", key_id=11, key_name="chrome-extension", user_id=None)


@pytest.fixture
def fake_session(monkeypatch):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: READER_USER if (model is User and pk == 1) else None
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.add.side_effect = lambda obj: setattr(obj, "id", 77)
    monkeypatch.setattr(akr, "get_scoped_session", lambda: session)
    return session


@pytest.fixture
def auth_holder():
    return {"ctx": SERVICE_AUTH}


@pytest.fixture
def client(fake_session, auth_holder):
    app = flask.Flask(__name__)

    @app.before_request
    def _set_auth():
        if auth_holder["ctx"] is not None:
            flask.g.auth = auth_holder["ctx"]

    app.register_blueprint(akr.bp)
    return app.test_client()


class TestWhoami:
    def test_user_key(self, client, auth_holder):
        auth_holder["ctx"] = USER_AUTH
        data = client.get("/whoami").get_json()
        assert data["kind"] == "user"
        assert data["key_name"] == "frontend-krzysztof"
        assert data["is_legacy"] is False
        assert data["user"] == {"id": 1, "username": "krzysztof", "display_name": "Krzysztof"}

    def test_service_key(self, client):
        data = client.get("/whoami").get_json()
        assert data["kind"] == "service"
        assert data["user"] is None

    def test_unauthenticated_401(self, client, auth_holder):
        auth_holder["ctx"] = None
        assert client.get("/whoami").status_code == 401


class TestApiKeyManagement:
    def test_user_key_gets_403(self, client, auth_holder):
        auth_holder["ctx"] = USER_AUTH
        assert client.get("/api_keys").status_code == 403
        assert client.post("/api_keys", json={"kind": "service", "name": "x"}).status_code == 403
        assert client.delete("/api_keys/10").status_code == 403

    def test_list_keys(self, client, fake_session):
        fake_session.execute.return_value.scalars.return_value.all.return_value = [_make_key_row()]
        data = client.get("/api_keys").get_json()
        key = data["api_keys"][0]
        assert key["name"] == "frontend-krzysztof"
        assert key["key_prefix"] == "lk_usr_abcde"
        assert "key_hash" not in key
        assert "plaintext" not in key

    def test_create_key_returns_plaintext_once(self, client):
        resp = client.post("/api_keys", json={"kind": "user", "name": "reader-k", "user_id": 1})
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["plaintext"].startswith("lk_usr_")
        assert data["api_key"]["name"] == "reader-k"
        assert "key_hash" not in data["api_key"]

    def test_create_key_validation_400(self, client):
        assert client.post("/api_keys", json={"kind": "admin", "name": "x"}).status_code == 400
        assert client.post(
            "/api_keys", json={"kind": "user", "name": "x", "user_id": "1"},
        ).status_code == 400  # user_id must be an int, not a string

    def test_deactivate_key(self, client, fake_session):
        row = _make_key_row()
        fake_session.get.side_effect = lambda model, pk: row if (model is ApiKey and pk == 10) else None
        resp = client.delete("/api_keys/10")
        assert resp.status_code == 200
        assert resp.get_json()["api_key"]["active"] is False

    def test_deactivate_missing_404(self, client, fake_session):
        fake_session.get.side_effect = lambda model, pk: None
        assert client.delete("/api_keys/999").status_code == 404
