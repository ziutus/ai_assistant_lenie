"""In-memory SQLite harness for the world-events registry tests.

The registry tables are portable enough for SQLite; ``organizations``, ``persons``, ``document_events`` and
``document_entities`` use PostgreSQL types (JSONB, ARRAY, ``gen_random_uuid()``), so they are created here with
the real column names but no types or constraints. What SQLite cannot check (the partial unique index, trigram
search, row locks, foreign-key enforcement) is covered by the Postgres run of the migration, see ADR-034.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from library import geopolitics_service as svc
from library.db.engine import Base
from library.geo_event_kind_store import SEED_KINDS
from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    DocumentEntity,
    DocumentEvent,
    GeoEvent,
    GeoEventAlias,
    GeoEventKind,
    GeoEventMentionLink,
    GeoEventOrganization,
    GeoEventParticipant,
    GeoEventPerson,
    GeoEventRole,
    GeoEventSource,
    Organization,
    Person,
)

PORTABLE = (
    Country,
    GeoEventKind,
    GeoEventRole,
    GeoEvent,
    GeoEventParticipant,
    GeoEventOrganization,
    GeoEventPerson,
    GeoEventAlias,
    GeoEventSource,
    GeoEventMentionLink,
    CountryRelationAssessment,
    CountryRelationEvidence,
)
UNTYPED = (Organization, Person, DocumentEvent, DocumentEntity)


def make_engine():
    return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def create_schema(engine) -> None:
    Base.metadata.create_all(engine, tables=[model.__table__ for model in PORTABLE])
    with engine.begin() as conn:
        for model in UNTYPED:
            columns = ["id INTEGER PRIMARY KEY"] + [c.name for c in model.__table__.columns if c.name != "id"]
            conn.execute(text(f"CREATE TABLE {model.__tablename__} ({', '.join(columns)})"))
        for kind in SEED_KINDS:
            conn.execute(
                text("INSERT INTO geo_event_kinds (code, label, sort_order) VALUES (:c, :l, :o)"),
                {"c": kind.code, "l": kind.label, "o": kind.sort_order},
            )
        for code in svc.ROLES:
            conn.execute(text("INSERT INTO geo_event_roles (code, label) VALUES (:c, :c)"), {"c": code})


def add_organization(session, org_id: int, name: str) -> None:
    session.execute(text("INSERT INTO organizations (id, canonical_name) VALUES (:i, :n)"), {"i": org_id, "n": name})


def add_person(session, person_id: int, name: str) -> None:
    session.execute(text("INSERT INTO persons (id, canonical_name) VALUES (:i, :n)"), {"i": person_id, "n": name})


def add_document_event(session, row_id: int, document_id: int, description: str, date: str | None, precision="day"):
    session.execute(
        text(
            "INSERT INTO document_events (id, document_id, event_date, date_precision, date_text, description, "
            "anchor_quote) VALUES (:i, :d, :dt, :p, :t, :desc, :q)"
        ),
        {
            "i": row_id,
            "d": document_id,
            "dt": date,
            "p": precision,
            "t": date or "",
            "desc": description,
            "q": description,
        },
    )


def add_event_mention(session, row_id: int, document_id: int, name: str, description=None, mentions: int = 1) -> None:
    session.execute(
        text(
            "INSERT INTO document_entities (id, document_id, entity_type, entity_text, mention_count, description) "
            "VALUES (:i, :d, 'eventName', :n, :m, :desc)"
        ),
        {"i": row_id, "d": document_id, "n": name, "m": mentions, "desc": description},
    )
