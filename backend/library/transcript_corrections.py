"""Literal STT phrase corrections, a short cache and best-effort hit statistics."""

import logging
import re
import threading
import time
from dataclasses import dataclass, field

from sqlalchemy import func, select, update

from library.db.engine import get_session
from library.db.models import TranscriptCorrection
from library.ner_normalization import normalize_ner_text

logger = logging.getLogger(__name__)


class TranscriptCorrectionValidationError(ValueError):
    """The correction is not a safe literal phrase rule."""


@dataclass(frozen=True)
class TranscriptCorrectionRow:
    id: int
    scope: str
    author: str | None
    pattern: str
    replacement: str


@dataclass
class _RuleCache:
    rules: list[TranscriptCorrectionRow] = field(default_factory=list)
    expires_at: float = 0
    ttl: float = 60


_cache = _RuleCache()
_cache_lock = threading.RLock()


def bust_cache() -> None:
    with _cache_lock:
        _cache.expires_at = 0
        _cache.rules = []


def normalize_author(author: str | None) -> str | None:
    return normalize_ner_text(author or "").casefold() or None


def validate_rule(*, pattern, replacement, scope="global", author=None) -> None:
    if not isinstance(pattern, str) or not pattern.strip():
        raise TranscriptCorrectionValidationError("pattern nie może być pusty")
    phrase = pattern.strip()
    # Long punctuation-separated phrases are allowed, but never a bare word.
    if len(re.findall(r"\w+", phrase)) < 2 or (len(phrase.split()) < 2 and len(phrase) < 12):
        raise TranscriptCorrectionValidationError("pattern musi być frazą, nie pojedynczym słowem")
    if not isinstance(replacement, str):
        raise TranscriptCorrectionValidationError("replacement musi być tekstem")
    if phrase == replacement:
        raise TranscriptCorrectionValidationError("pattern i replacement muszą się różnić")
    if scope not in ("global", "author"):
        raise TranscriptCorrectionValidationError("scope musi być global lub author")
    if author is not None and not isinstance(author, str):
        raise TranscriptCorrectionValidationError("author musi być tekstem")
    if scope == "author" and not normalize_author(author):
        raise TranscriptCorrectionValidationError("Dla scope=author wymagany jest autor")
    if scope == "global" and author is not None:
        raise TranscriptCorrectionValidationError("Dla scope=global author musi być null")


def _session_cleanup(session, method: str) -> None:
    if session is not None:
        try:
            getattr(session, method)()
        except (SystemExit, Exception):
            logger.exception("Nie udało się wykonać %s sesji transcript_corrections", method)


def _read_rules(session) -> list[TranscriptCorrectionRow]:
    records = session.scalars(
        select(TranscriptCorrection).where(TranscriptCorrection.active.is_(True)).order_by(TranscriptCorrection.id)
    )
    return [TranscriptCorrectionRow(r.id, r.scope, r.author, r.pattern, r.replacement) for r in records]


def load_active_rules(*, session=None) -> list[TranscriptCorrectionRow]:
    if session is not None:
        # An explicit transaction must see its own rules, never populate the process cache.
        return _read_rules(session)
    with _cache_lock:
        if time.monotonic() < _cache.expires_at:
            return list(_cache.rules)
        owned_session = None
        rows = []
        try:
            owned_session = get_session()
            rows = _read_rules(owned_session)
        except (SystemExit, Exception):
            logger.exception("Nie można załadować transcript_corrections; tekst bez korekt")
            _session_cleanup(owned_session, "rollback")
        finally:
            _session_cleanup(owned_session, "close")
        _cache.rules = rows
        _cache.expires_at = time.monotonic() + _cache.ttl
        return list(rows)


def validate_one_off(*, pattern, replacement) -> None:
    """A one-document replacement is never stored as a rule, so a single word is allowed."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise TranscriptCorrectionValidationError("pattern nie może być pusty")
    if not re.findall(r"\w+", pattern):
        raise TranscriptCorrectionValidationError("pattern musi zawierać słowo")
    if not isinstance(replacement, str):
        raise TranscriptCorrectionValidationError("replacement musi być tekstem")
    if pattern.strip() == replacement:
        raise TranscriptCorrectionValidationError("pattern i replacement muszą się różnić")


def replace_phrase(text: str, pattern: str, replacement: str) -> tuple[str, int]:
    """Literal, case-insensitive, whole-word replacement; the first letter follows the matched case."""
    regex = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in pattern.split()) + r"(?!\w)"

    def replace(match):
        result = replacement
        first = match.group()[0]
        if result and first.casefold() == result[0].casefold():
            result = (result[0].upper() if first.isupper() else result[0].lower()) + result[1:]
        return result

    return re.subn(regex, replace, text, flags=re.IGNORECASE)


def correct_text(text: str, author, rules) -> tuple[str, list[tuple[int, int]]]:
    """Pure preview used by the dry-run endpoint; no statistics or persistence."""
    hits = []
    for rule in sorted(rules, key=lambda r: (-len(r.pattern.strip()), r.id)):
        try:
            validate_rule(pattern=rule.pattern, replacement=rule.replacement, scope=rule.scope, author=rule.author)
        except TranscriptCorrectionValidationError:
            logger.warning("Pominięto niepoprawną regułę transcript_corrections:%s", rule.id)
            continue
        if rule.scope == "author" and normalize_author(author) != normalize_author(rule.author):
            continue
        text, count = replace_phrase(text, rule.pattern, rule.replacement)
        if count:
            hits.append((rule.id, count))
    return text, hits


def _bump_hit_counts(hits, *, session=None) -> None:
    if not hits:
        return
    owned = session is None
    try:
        if owned:
            session = get_session()
        # Isolate statistics errors from a caller-owned transaction.
        with session.begin_nested():
            for rule_id, count in hits:
                session.execute(update(TranscriptCorrection).where(TranscriptCorrection.id == rule_id).values(
                    hit_count=TranscriptCorrection.hit_count + count, last_hit_at=func.now(),
                ))
        if owned:
            session.commit()
    except (SystemExit, Exception):
        logger.exception("Nie można zapisać trafień transcript_corrections")
        if owned:
            _session_cleanup(session, "rollback")
    finally:
        if owned:
            _session_cleanup(session, "close")


def apply_transcript_corrections(text, author=None, *, session=None) -> tuple[str, list[tuple[int, int]]]:
    corrected, hits = correct_text(text, author, load_active_rules(session=session))
    _bump_hit_counts(hits, session=session)
    return corrected, hits
