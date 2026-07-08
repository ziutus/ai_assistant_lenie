"""API-key authentication with an in-process cache (Etap 8).

Keys live in the api_keys table (only SHA-256 hashes; plaintext is shown once
at creation). Two kinds:
  - service — full access, no reader identity (reader endpoints reject it),
  - user    — full access + carries the reader identity (users.id).
The legacy shared STALKER_API_KEY is still accepted as a service key during
the client-migration period (is_legacy=True in the resolved context).

The per-request hash→context lookup MUST NOT hit the database: results
(including unknown keys — negative entries) are cached in the process. The
cache is defined as a small get/set/invalidate protocol so the in-process
dict can later be swapped for a Redis-backed implementation shared between
workers, without touching the resolve logic.
"""

import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, update

from library.db.models import ApiKey, User

logger = logging.getLogger(__name__)

KEY_PREFIX_LEN = 12
POSITIVE_TTL_SECONDS = 300
NEGATIVE_TTL_SECONDS = 30
# last_used_at is written at most this often per key, so steady traffic on a
# cached key does not turn into a DB write per request.
LAST_USED_WRITE_INTERVAL_SECONDS = 300

VALID_KINDS = ("user", "service")


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity of a request; stored in flask.g.auth by the middleware."""

    kind: str  # "user" | "service"
    key_id: int | None  # None for the legacy STALKER_API_KEY fallback
    key_name: str
    user_id: int | None  # only for kind="user"
    is_legacy: bool = False


@dataclass(frozen=True)
class CacheEntry:
    context: AuthContext | None  # None = known-bad key (negative entry)
    expires_at: float  # time.monotonic() deadline


class ApiKeyCache(Protocol):
    """Swap point for a future Redis-backed cache (values are dataclasses,
    trivially serializable to dicts)."""

    def get(self, key_hash: str) -> CacheEntry | None: ...

    def set(self, key_hash: str, entry: CacheEntry) -> None: ...

    def invalidate(self, key_hash: str | None = None) -> None: ...


class InProcessApiKeyCache:
    """Dict + TTL cache; sufficient for the single Flask process on the NAS."""

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key_hash: str) -> CacheEntry | None:
        with self._lock:
            entry = self._entries.get(key_hash)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                del self._entries[key_hash]
                return None
            return entry

    def set(self, key_hash: str, entry: CacheEntry) -> None:
        with self._lock:
            self._entries[key_hash] = entry

    def invalidate(self, key_hash: str | None = None) -> None:
        with self._lock:
            if key_hash is None:
                self._entries.clear()
            else:
                self._entries.pop(key_hash, None)


_cache: ApiKeyCache = InProcessApiKeyCache()
_last_used_written: dict[int, float] = {}
_last_used_lock = threading.Lock()


def get_cache() -> ApiKeyCache:
    return _cache


def invalidate_cache(key_hash: str | None = None) -> None:
    """Call after any api_keys change (create/deactivate)."""
    _cache.invalidate(key_hash)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key(kind: str) -> tuple[str, str, str]:
    """Return (plaintext, key_hash, key_prefix) for a new key.

    Format: lk_<usr|svc>_<token_urlsafe(32)> — the prefix makes the key kind
    recognizable in configs and logs without revealing the secret.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}, got {kind!r}")
    plaintext = f"lk_{'usr' if kind == 'user' else 'svc'}_{secrets.token_urlsafe(32)}"
    return plaintext, hash_api_key(plaintext), plaintext[:KEY_PREFIX_LEN]


def create_api_key(session, kind: str, name: str, user_id: int | None = None) -> tuple[ApiKey, str]:
    """Create a key and return (row, plaintext). The plaintext is not stored
    anywhere — this is the only moment it exists server-side."""
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}, got {kind!r}")
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > 100:
        raise ValueError("name too long (max 100)")
    if kind == "user":
        if user_id is None:
            raise ValueError("user_id is required for kind=user")
        if session.get(User, user_id) is None:
            raise ValueError(f"User {user_id} not found")
    elif user_id is not None:
        raise ValueError("user_id is only allowed for kind=user")
    existing = session.execute(select(ApiKey).where(ApiKey.name == name)).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"API key named '{name}' already exists")

    plaintext, key_hash, key_prefix = generate_api_key(kind)
    row = ApiKey(kind=kind, user_id=user_id, name=name, key_hash=key_hash, key_prefix=key_prefix, active=True)
    session.add(row)
    session.commit()
    invalidate_cache()
    return row, plaintext


def deactivate_api_key(session, key_id: int) -> ApiKey:
    row = session.get(ApiKey, key_id)
    if row is None:
        raise ValueError(f"API key {key_id} not found")
    row.active = False
    session.commit()
    invalidate_cache()
    return row


def resolve_api_key(session_factory, raw_key: str, legacy_key: str | None = None) -> AuthContext | None:
    """Resolve a raw x-api-key value to an AuthContext (None = invalid key).

    session_factory is a zero-arg callable (e.g. get_scoped_session) invoked
    ONLY when the database is actually needed: cache hits and the legacy-key
    compare resolve without opening a session, so legacy clients keep working
    even if the api_keys table (or the whole DB) is unreachable.
    """
    key_hash = hash_api_key(raw_key)
    entry = _cache.get(key_hash)
    if entry is not None:
        if entry.context is not None:
            _touch_last_used(session_factory, entry.context)
        return entry.context

    if legacy_key and raw_key == legacy_key:
        context = AuthContext(kind="service", key_id=None, key_name="legacy", user_id=None, is_legacy=True)
        _cache.set(key_hash, CacheEntry(context, time.monotonic() + POSITIVE_TTL_SECONDS))
        return context

    row = session_factory().execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
    ).scalar_one_or_none()
    if row is not None:
        context = AuthContext(kind=row.kind, key_id=row.id, key_name=row.name, user_id=row.user_id)
        _cache.set(key_hash, CacheEntry(context, time.monotonic() + POSITIVE_TTL_SECONDS))
        _touch_last_used(session_factory, context)
        return context

    _cache.set(key_hash, CacheEntry(None, time.monotonic() + NEGATIVE_TTL_SECONDS))
    return None


def _touch_last_used(session_factory, context: AuthContext) -> None:
    if context.key_id is None:
        return
    now = time.monotonic()
    with _last_used_lock:
        last = _last_used_written.get(context.key_id)
        if last is not None and now - last < LAST_USED_WRITE_INTERVAL_SECONDS:
            return
        _last_used_written[context.key_id] = now
    session = session_factory()
    try:
        session.execute(
            update(ApiKey).where(ApiKey.id == context.key_id).values(last_used_at=datetime.now())
        )
        session.commit()
    except Exception:  # noqa: BLE001 — telemetry only, must never fail the request
        logger.warning("Failed to update last_used_at for api key %s", context.key_id, exc_info=True)
        session.rollback()
