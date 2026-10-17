"""Database additions to the curated NER gazetteers (ADR-029): cached read + write validation.

The seed lists stay in code (city_gazetteer._CITY_DATA, geocode_aliases.GEOCODE_ALIASES); rows
in ``ner_gazetteer_entries`` only *extend* them, so a new entry needs no code change or deploy.
Same safety model as cleanup_rules.py: a short TTL cache (REST writes bust it) and a hard rule
that NER never fails because of the database — any DB error, including the SystemExit that
config_loader.require() raises when config is missing, yields an empty list (the seed alone).
"""

import logging
import re
import threading
import time
from dataclasses import dataclass, field

from unidecode import unidecode

logger = logging.getLogger(__name__)

KIND_CITY = "city"
KIND_GEOCODE_ALIAS = "geocode_alias"
KINDS = (KIND_CITY, KIND_GEOCODE_ALIAS)
TTL_SECONDS = 60
MAX_NAME_LENGTH = 200
MAX_PATTERNS = 8
MIN_STEM_LENGTH = 3

_PATTERN_RE = re.compile(r"[a-z0-9*\- ]+")


class GazetteerValidationError(ValueError):
    """A gazetteer entry does not meet the closed-list safety rules."""


@dataclass(frozen=True)
class GazetteerEntry:
    kind: str
    name_pl: str
    patterns: tuple[str, ...] = ()
    geocode_alias: str | None = None


@dataclass
class _Cache:
    entries: dict[str, tuple[GazetteerEntry, ...]] = field(default_factory=dict)
    expires_at: float = 0.0
    version: int = 0


_cache = _Cache()
_lock = threading.RLock()


def _fetch_rows() -> list[GazetteerEntry]:
    """Read every row through a short own session; patched in unit tests."""
    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import NerGazetteerEntry

    session = get_session()
    try:
        records = session.scalars(select(NerGazetteerEntry).order_by(NerGazetteerEntry.id))
        return [
            GazetteerEntry(r.kind, r.name_pl, tuple(r.patterns or ()), r.geocode_alias) for r in records
        ]
    finally:
        session.close()


def _refresh_locked() -> None:
    try:
        rows = _fetch_rows()
    except (SystemExit, Exception):
        logger.warning("NER gazetteer: cannot load database entries; using code seed only", exc_info=True)
        rows = []
    grouped: dict[str, list[GazetteerEntry]] = {}
    for row in rows:
        grouped.setdefault(row.kind, []).append(row)
    _cache.entries = {kind: tuple(items) for kind, items in grouped.items()}
    _cache.expires_at = time.monotonic() + TTL_SECONDS
    _cache.version += 1


def get_entries(kind: str) -> tuple[GazetteerEntry, ...]:
    """Database entries of one kind (empty when the DB is unavailable). Never raises."""
    with _lock:
        if time.monotonic() >= _cache.expires_at:
            _refresh_locked()
        return _cache.entries.get(kind, ())


def cache_version() -> int:
    """Changes whenever the cache was refreshed; lets dependants invalidate compiled data."""
    with _lock:
        if time.monotonic() >= _cache.expires_at:
            _refresh_locked()
        return _cache.version


def invalidate_cache() -> None:
    with _lock:
        _cache.expires_at = 0.0


def validate_entry(*, kind, name_pl, patterns=None, geocode_alias=None) -> dict:
    """Return the normalized entry fields or raise GazetteerValidationError."""
    if kind not in KINDS:
        raise GazetteerValidationError(f"kind musi być jednym z: {', '.join(KINDS)}")
    if not isinstance(name_pl, str) or not name_pl.strip() or len(name_pl.strip()) > MAX_NAME_LENGTH:
        raise GazetteerValidationError(f"name_pl musi mieć od 1 do {MAX_NAME_LENGTH} znaków")
    name_pl = name_pl.strip()
    if kind == KIND_GEOCODE_ALIAS:
        if not isinstance(geocode_alias, str) or not geocode_alias.strip() or len(geocode_alias.strip()) > MAX_NAME_LENGTH:
            raise GazetteerValidationError(f"geocode_alias musi mieć od 1 do {MAX_NAME_LENGTH} znaków")
        return {"kind": kind, "name_pl": name_pl, "patterns": [], "geocode_alias": geocode_alias.strip()}
    if not isinstance(patterns, list) or not 1 <= len(patterns) <= MAX_PATTERNS:
        raise GazetteerValidationError(f"patterns musi być listą od 1 do {MAX_PATTERNS} wzorców")
    normalized = []
    for raw in patterns:
        if not isinstance(raw, str):
            raise GazetteerValidationError("Wzorzec musi być tekstem")
        pattern = unidecode(raw).strip().lower()
        if not pattern or _PATTERN_RE.fullmatch(pattern) is None:
            raise GazetteerValidationError(f"Wzorzec {raw!r}: dozwolone tylko a-z, 0-9, spacja, '-' i '*'")
        for token in pattern.split():
            if "*" in token[:-1] or token == "*":
                raise GazetteerValidationError(f"Wzorzec {raw!r}: '*' może stać tylko na końcu członu")
            if len(token.rstrip("*")) < MIN_STEM_LENGTH:
                raise GazetteerValidationError(
                    f"Wzorzec {raw!r}: człon musi mieć co najmniej {MIN_STEM_LENGTH} znaki przed '*'"
                )
        normalized.append(pattern)
    from library.city_gazetteer import compile_variant

    for pattern in normalized:
        try:
            compile_variant(pattern)
        except re.error as exc:
            raise GazetteerValidationError(f"Wzorzec {pattern!r} nie kompiluje się: {exc}") from exc
    return {"kind": kind, "name_pl": name_pl, "patterns": normalized, "geocode_alias": None}
