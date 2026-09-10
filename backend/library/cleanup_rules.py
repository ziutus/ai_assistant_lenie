"""Reguły usuwania linii: walidacja, krótki cache i zapis statystyk best-effort."""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import regex
from sqlalchemy import select, text

from library.db.engine import get_session
from library.db.models import CleanupRule
from library.publisher_domain import normalize_publisher_domain, registrable_domain

logger = logging.getLogger(__name__)
MIN_CONTAINS_LENGTH = 12
REGEX_TIMEOUT = 0.02


class CleanupRuleValidationError(ValueError):
    """Reguła nie spełnia warunków bezpiecznego usuwania linii."""


@dataclass(frozen=True)
class CleanupRuleRow:
    id: int
    scope: str
    domain: str | None
    match_type: str
    pattern: str


@dataclass
class _RuleCache:
    rules: list[CleanupRuleRow] = field(default_factory=list)
    expires_at: float = 0
    ttl: float = 60


_cache = _RuleCache()
_cache_lock = threading.RLock()


def bust_cache() -> None:
    with _cache_lock:
        _cache.expires_at = 0
        _cache.rules = []


def _session_cleanup(session, method: str) -> None:
    if session is not None:
        try:
            getattr(session, method)()
        except (SystemExit, Exception):
            logger.exception("Nie udało się wykonać %s sesji cleanup_rules", method)


def load_active_rules() -> list[CleanupRuleRow]:
    """Pobierz snapshot; także awarię buforuj przez TTL, aby nie przeciążać bazy."""
    with _cache_lock:
        if time.monotonic() < _cache.expires_at:
            return list(_cache.rules)
        session = None
        rows = []
        try:
            session = get_session()
            records = session.scalars(select(CleanupRule).where(CleanupRule.active.is_(True)).order_by(CleanupRule.id))
            rows = [CleanupRuleRow(r.id, r.scope, r.domain, r.match_type, r.pattern) for r in records]
        except (SystemExit, Exception):
            logger.exception("Nie można załadować cleanup_rules; czyszczenie bez reguł z bazy")
            _session_cleanup(session, "rollback")
        finally:
            _session_cleanup(session, "close")
        _cache.rules = rows
        _cache.expires_at = time.monotonic() + _cache.ttl
        return list(rows)


def host_from_url(url: str) -> str | None:
    try:
        return normalize_publisher_domain(urlparse(url).netloc)
    except ValueError:
        return None


def normalize_literal_line(value: str) -> str:
    """Zdejmij emfazy markdown, końcową interpunkcję i otaczające białe znaki."""
    value = value.strip()
    previous = None
    while value != previous:
        previous = value
        value = value.rstrip(".:").strip()
        if len(value) >= 2 and value[0] in "*_" and value[-1] == value[0]:
            value = value[1:-1].strip()
    return value.casefold()


@lru_cache(maxsize=1)
def load_known_good_corpus() -> list[str]:
    path = Path(__file__).resolve().parents[1] / "data" / "cleanup_rules_known_good.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@lru_cache(maxsize=512)
def _validated_regex(pattern: str):
    """Limit 200 znaków ogranicza kompilację; każde search ma budżet 20 ms.

    Składnia standardowego re wyklucza rekursję i rozszerzenia silnika regex.
    Budżet dopasowania obowiązuje zarówno korpus walidacyjny, jak i runtime.
    """
    if len(pattern) > 200:
        raise CleanupRuleValidationError("Regex może mieć najwyżej 200 znaków")
    if not (pattern.startswith("^") or pattern.endswith("$") or r"\b" in pattern):
        raise CleanupRuleValidationError("Regex wymaga kotwicy ^, $ lub \\b")
    try:
        re.compile(pattern)
        compiled = regex.compile(pattern)
        for index, paragraph in enumerate(load_known_good_corpus(), 1):
            if compiled.search(paragraph, timeout=REGEX_TIMEOUT):
                raise CleanupRuleValidationError(f"Regex usuwa poprawny akapit {index}: {paragraph}")
    except (re.error, regex.error, OverflowError, TimeoutError, OSError) as exc:
        raise CleanupRuleValidationError(f"Niebezpieczny lub niepoprawny regex: {exc}") from exc
    return compiled


def validate_rule(*, scope, domain, match_type, pattern) -> None:
    if scope not in ("global", "domain"):
        raise CleanupRuleValidationError("scope musi być global lub domain")
    if domain is not None and not isinstance(domain, str):
        raise CleanupRuleValidationError("domain musi być tekstem")
    if scope == "domain" or domain:
        normalized = normalize_publisher_domain(domain)
        if not normalized or len(normalized) > 255 or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}", normalized,
        ):
            raise CleanupRuleValidationError("Dla scope=domain wymagana jest poprawna domena bez URL")
    if match_type not in ("literal_line", "contains", "regex"):
        raise CleanupRuleValidationError("Nieznany match_type")
    if not isinstance(pattern, str) or not pattern.strip():
        raise CleanupRuleValidationError("pattern nie może być pusty")
    if "\n" in pattern or "\r" in pattern:
        raise CleanupRuleValidationError("pattern musi dotyczyć jednej linii")
    if match_type == "literal_line" and not normalize_literal_line(pattern):
        raise CleanupRuleValidationError("pattern po normalizacji nie może być pusty")
    if match_type == "contains" and len(pattern.strip()) < MIN_CONTAINS_LENGTH:
        raise CleanupRuleValidationError(f"contains wymaga co najmniej {MIN_CONTAINS_LENGTH} znaków")
    if match_type == "regex":
        _validated_regex(pattern)


def rule_matches(stripped_line: str, host: str | None, rule: CleanupRuleRow) -> bool:
    if rule.scope == "domain":
        domain = normalize_publisher_domain(rule.domain)
        host = normalize_publisher_domain(host)
        if not domain or not host:
            return False
        if host != domain and not (domain == registrable_domain(domain) and host.endswith("." + domain)):
            return False
    elif rule.scope != "global":
        return False
    if rule.match_type == "literal_line":
        pattern = normalize_literal_line(rule.pattern)
        return bool(pattern) and normalize_literal_line(stripped_line) == pattern
    if rule.match_type == "contains":
        return len(rule.pattern.strip()) >= MIN_CONTAINS_LENGTH and rule.pattern.casefold() in stripped_line.casefold()
    if rule.match_type == "regex":
        try:
            return _validated_regex(rule.pattern).search(stripped_line, timeout=REGEX_TIMEOUT) is not None
        except (CleanupRuleValidationError, regex.error, TimeoutError):
            logger.warning("Pominięto niebezpieczny regex cleanup_rules:%s", rule.id, exc_info=True)
    return False


def match_line_rules(stripped_line, host, rules) -> CleanupRuleRow | None:
    return next((rule for rule in rules if rule_matches(stripped_line, host, rule)), None)


def _bump_hit_counts(hit_ids) -> None:
    """Jedno zwiększenie licznika reguły na wywołanie cleanera, w osobnej sesji."""
    if not hit_ids:
        return
    session = None
    try:
        session = get_session()
        session.execute(text(
            "UPDATE cleanup_rules SET hit_count = hit_count + 1, last_hit_at = now() WHERE id = ANY(:ids)"
        ), {"ids": sorted(set(hit_ids))})
        session.commit()
    except (SystemExit, Exception):
        logger.exception("Nie można zapisać trafień cleanup_rules")
        _session_cleanup(session, "rollback")
    finally:
        _session_cleanup(session, "close")
