"""Database-backed review reasons with a process-local TTL cache and offline seed."""

import logging
import re
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)
TTL_SECONDS = 60


@dataclass(frozen=True)
class ReasonEntry:
    code: str
    label: str
    sort_order: int = 100
    system: bool = False
    selectable: bool = True
    active: bool = True


SEED_REASONS = (
    ReasonEntry("not_interested", "Nie interesuje mnie temat", 10),
    ReasonEntry("duplicate", "Duplikat / już widziałem", 20),
    ReasonEntry("interesting_no_time", "Ciekawe, ale nie mam czasu", 25),
    ReasonEntry("already_known", "Już to znam", 30),
    ReasonEntry("too_long", "Za długie", 40),
    ReasonEntry("other", "Inny powód", 50),
    ReasonEntry("sent_to_radar", "Przeniesiono do radaru", 900, system=True, selectable=False),
    ReasonEntry("expired", "Wygasło (Może kiedyś)", 910, system=True, selectable=False),
)
_lock = threading.RLock()
_reasons = SEED_REASONS
_expires_at = 0.0


def _fetch_rows(session=None):
    from sqlalchemy import select

    from library.db.engine import get_session
    from library.db.models import FeedReviewReason

    own_session = session is None
    if own_session:
        session = get_session()
    try:
        return tuple(
            ReasonEntry(row.code, row.label, row.sort_order, row.system, row.selectable, row.active)
            for row in session.scalars(
                select(FeedReviewReason).order_by(
                    FeedReviewReason.sort_order,
                    FeedReviewReason.code,
                )
            )
        )
    finally:
        if own_session:
            session.close()


def list_reasons(session=None, include_inactive=True):
    """Read all reasons, including retired codes needed for undo; never raise on DB failure.

    An explicit session bypasses the shared cache, so uncommitted data cannot leak into it.
    """
    global _reasons, _expires_at
    with _lock:
        if session is not None:
            try:
                rows = _fetch_rows(session)
            except (Exception, SystemExit):
                logger.warning("Cannot load feed review reasons; using seed", exc_info=True)
                rows = SEED_REASONS
        else:
            if time.monotonic() >= _expires_at:
                try:
                    _reasons = _fetch_rows()
                except (Exception, SystemExit):
                    logger.warning("Cannot load feed review reasons; using seed", exc_info=True)
                    _reasons = SEED_REASONS
                _expires_at = time.monotonic() + TTL_SECONDS
            rows = _reasons
        return tuple(
            sorted(
                (row for row in rows if include_inactive or row.active),
                key=lambda row: (row.sort_order, row.code),
            )
        )


def selectable_reasons():
    return tuple(row for row in list_reasons(include_inactive=False) if row.selectable)


def is_valid_reason(code):
    return any(row.code == code for row in list_reasons())


def label_for(code):
    return next((row.label for row in list_reasons() if row.code == code), code)


def bust_cache():
    global _expires_at
    with _lock:
        _expires_at = 0.0


def check_reason(*, code, label, sort_order=100, active=True, selectable=True):
    if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9_]{1,39}", code) is None:
        return None, "Kod musi mieć 2–40 znaków: małe litery, cyfry i podkreślenia, zaczynając od litery"
    if not isinstance(label, str):
        return None, "Etykieta musi mieć od 1 do 120 znaków"
    label = " ".join(label.split())
    if not 1 <= len(label) <= 120:
        return None, "Etykieta musi mieć od 1 do 120 znaków"
    if type(sort_order) is not int or not 0 <= sort_order <= 10000:
        return None, "Kolejność musi być liczbą całkowitą od 0 do 10000"
    if not isinstance(active, bool) or not isinstance(selectable, bool):
        return None, "Aktywny i wybieralny muszą być wartościami logicznymi"
    return dict(code=code, label=label, sort_order=sort_order, active=active, selectable=selectable), None
