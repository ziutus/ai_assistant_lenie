"""World-event kinds live in the ``geo_event_kinds`` table; this module only reads them.

The table is the single source of truth: validation (``geopolitics_service.validate_kind``), the picker
(``GET /geo_event_kinds``) and the foreign key of ``geo_events.kind`` all use it. ``SEED_KINDS`` is an OFFLINE
fallback for the moment the database cannot be reached (and the data the migrations inserted); it is never
consulted while the table can be read, so a kind added with ``POST /geo_event_kinds`` needs no deploy.
Reads without a session go through a process-local cache (60 s); a read with an explicit session bypasses it, so
uncommitted data cannot leak into the cache.
"""

import logging
import re
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)
TTL_SECONDS = 60


@dataclass(frozen=True)
class KindEntry:
    code: str
    label: str
    sort_order: int = 100


SEED_KINDS = (
    KindEntry("election", "Wybory", 10),
    KindEntry("summit", "Szczyt / spotkanie", 20),
    KindEntry("diplomatic", "Dyplomacja", 30),
    KindEntry("agreement", "Umowa / traktat", 40),
    KindEntry("sanctions", "Sankcje", 50),
    KindEntry("conflict", "Konflikt zbrojny", 60),
    KindEntry("terror_attack", "Atak terrorystyczny", 65),
    KindEntry("exercise", "Ćwiczenia wojskowe", 70),
    KindEntry("protest", "Protesty / niepokoje", 80),
    KindEntry("disaster", "Katastrofa / klęska żywiołowa", 90),
    KindEntry("health", "Zdrowie / pandemia", 100),
    KindEntry("outage", "Awaria / incydent techniczny", 110),
    KindEntry("cyber", "Cyberatak / luka w zabezpieczeniach", 120),
    KindEntry("product_launch", "Premiera produktu", 130),
    KindEntry("corporate", "Wydarzenie korporacyjne", 140),
    KindEntry("market", "Rynki / finanse", 150),
    KindEntry("other", "Inne", 9999),
)
_lock = threading.RLock()
_kinds = SEED_KINDS
_expires_at = 0.0


def _fetch_rows(session=None):
    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import GeoEventKind

    own_session = session is None
    if own_session:
        session = get_session()
    try:
        return tuple(
            KindEntry(row.code, row.label, row.sort_order)
            for row in session.scalars(select(GeoEventKind).order_by(GeoEventKind.sort_order, GeoEventKind.code))
        )
    finally:
        if own_session:
            session.close()


def list_kinds(session=None):
    """All kinds ordered by ``sort_order``; falls back to the seed when the table cannot be read."""
    global _kinds, _expires_at
    with _lock:
        if session is not None:
            try:
                return _fetch_rows(session) or SEED_KINDS
            except (Exception, SystemExit):
                logger.warning("Cannot load geo_event_kinds; using seed", exc_info=True)
                return SEED_KINDS
        if time.monotonic() >= _expires_at:
            try:
                _kinds = _fetch_rows() or SEED_KINDS
            except (Exception, SystemExit):
                logger.warning("Cannot load geo_event_kinds; using seed", exc_info=True)
                _kinds = SEED_KINDS
            _expires_at = time.monotonic() + TTL_SECONDS
        return _kinds


def kind_codes(session=None):
    return tuple(entry.code for entry in list_kinds(session))


def bust_cache():
    global _expires_at
    with _lock:
        _expires_at = 0.0


def check_kind(*, code, label, sort_order=100):
    """Validate a new kind; returns ``(values, None)`` or ``(None, message)``."""
    if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9_]{1,29}", code) is None:
        return None, "Kod musi mieć 2–30 znaków: małe litery, cyfry i podkreślenia, zaczynając od litery"
    if not isinstance(label, str):
        return None, "Etykieta musi mieć od 1 do 80 znaków"
    label = " ".join(label.split())
    if not 1 <= len(label) <= 80:
        return None, "Etykieta musi mieć od 1 do 80 znaków"
    if type(sort_order) is not int or not 0 <= sort_order <= 10000:
        return None, "Kolejność musi być liczbą całkowitą od 0 do 10000"
    return dict(code=code, label=label, sort_order=sort_order), None
