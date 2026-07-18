"""Read-only exact name resolution used to surface 0/1/N search matches."""

from dataclasses import dataclass

from sqlalchemy import func, select

from library.db.models import Person, PersonAlias, Source


@dataclass(frozen=True)
class NameMatch:
    id: int
    canonical_name: str


@dataclass(frozen=True)
class NameResolution:
    matches: tuple[NameMatch, ...]

    @property
    def count(self) -> int:
        return len(self.matches)

    @property
    def id(self) -> int | None:
        return self.matches[0].id if self.count == 1 else None


def resolve_author_name(session, name: str | None) -> NameResolution:
    """Return every person whose canonical name or alias exactly matches."""
    name = " ".join((name or "").strip().split()).lower()
    if not name:
        return NameResolution(())
    stmt = (
        select(Person)
        .outerjoin(PersonAlias, PersonAlias.person_id == Person.id)
        .where(
            (func.unaccent(func.lower(Person.canonical_name)) == func.unaccent(name))
            | (func.unaccent(func.lower(PersonAlias.alias)) == func.unaccent(name)),
        )
        .distinct()
        .order_by(Person.id)
    )
    rows = session.scalars(stmt).all()
    return NameResolution(tuple(NameMatch(row.id, row.canonical_name) for row in rows))


def resolve_discovery_source_name(session, name: str | None) -> NameResolution:
    """Resolve physical ``sources`` rows under their discovery-source meaning."""
    name = " ".join((name or "").strip().split()).lower()
    if not name:
        return NameResolution(())
    rows = session.scalars(
        select(Source)
        .where(func.unaccent(func.lower(Source.name)) == func.unaccent(name))
        .order_by(Source.id)
    ).all()
    return NameResolution(tuple(NameMatch(row.id, row.name) for row in rows))
