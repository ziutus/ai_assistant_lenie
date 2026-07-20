"""Deterministic publisher name/domain resolution for search stage 7A."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from sqlalchemy import func, select

from library.db.models import Publisher, PublisherDomain
from library.publisher_domain import normalize_publisher_domain


@dataclass(frozen=True)
class PublisherMatch:
    publisher_id: int
    canonical_name: str
    domains: tuple[str, ...]


@dataclass(frozen=True)
class PublisherResolution:
    """All deterministic matches; cardinality is intentionally preserved."""

    matches: tuple[PublisherMatch, ...]

    @property
    def count(self) -> int:
        return len(self.matches)

    @property
    def publisher_id(self) -> int | None:
        return self.matches[0].publisher_id if self.count == 1 else None


def _fold_name(value: str | None) -> str:
    value = " ".join((value or "").strip().split()).casefold().translate(str.maketrans({"ł": "l"}))
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def resolve_publisher(session, *, name: str | None = None,
                      domain: str | None = None) -> PublisherResolution:
    """Return zero, one or every matching publisher, ordered by id.

    Supplying both criteria applies AND semantics. Empty criteria safely
    resolve to zero rows. No ``first()``/``limit(1)`` is used.
    """
    folded_name = _fold_name(name)
    normalized_domain = normalize_publisher_domain(domain)
    if not folded_name and not normalized_domain:
        return PublisherResolution(())

    stmt = select(Publisher).order_by(Publisher.id)
    if folded_name:
        stmt = stmt.where(func.unaccent(func.lower(Publisher.canonical_name)) == folded_name)
    if normalized_domain:
        stmt = stmt.where(Publisher.id.in_(
            select(PublisherDomain.publisher_id).where(
                func.lower(PublisherDomain.domain) == normalized_domain,
            ),
        ))
    publishers = session.scalars(stmt).unique().all()
    return PublisherResolution(tuple(
        PublisherMatch(row.id, row.canonical_name, tuple(sorted(d.domain for d in row.domains)))
        for row in publishers
    ))
