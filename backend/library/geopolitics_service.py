"""World events (ADR-034) and versioned, directed country-relation assessments (ADR-033).

A *world event* is something that happened, with cited documents; it may involve countries, organizations and
persons, or none of them (an outage, a product launch). ADR-033. A *geo event* is something that happened (with cited documents). A *relation
assessment* says how country A stands toward country B on one axis over a validity
period. Events never change the map on their own: they back a PROPOSED assessment, a
human confirms it, and only ``confirmed`` assessments are drawn. Confirming a new
assessment closes the previous open period of the same (from, to, axis) in the same
transaction; the exclusion constraint of migration d7e1a4b9c205 is the concurrency
backstop.
"""

import datetime
import hashlib
import re
import unicodedata

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from unidecode import unidecode

from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    Document,
    DocumentEvent,
    GeoEvent,
    GeoEventAlias,
    GeoEventOrganization,
    GeoEventParticipant,
    GeoEventPerson,
    GeoEventSource,
    Organization,
    Person,
)

# axis -> (label, what -2 and +2 mean). Scores are -2..+2 on every axis.
AXES: dict[str, dict] = {
    "political": {
        "label": "Polityczna",
        "scale": {
            -2: "wroga: otwarte działania przeciw rządowi lub interesom kraju docelowego",
            -1: "napięta: spory, sankcje, wrogie deklaracje, brak zaufania",
            0: "neutralna lub mieszana",
            1: "przyjazna: współpraca polityczna, wspólne stanowiska",
            2: "sojusznicza: formalny sojusz lub bliski bezpośredni patronat",
        },
    },
    "security": {
        "label": "Bezpieczeństwo",
        "scale": {
            -2: "zagrożenie: wojsko lub służby działają przeciw krajowi docelowemu",
            -1: "rywalizacja: wrogie manewry, szpiegostwo, sankcje zbrojeniowe",
            0: "brak istotnej współpracy",
            1: "współpraca: ćwiczenia, wymiana danych, dostawy uzbrojenia",
            2: "sojusz obronny lub stałe bazy i gwarancje",
        },
    },
}
# Dictionaries (tables geo_event_roles / geo_event_kinds, seeded by migration c7e2b5a9d814); kept in step by a test.
ROLES = ("actor", "target", "affected", "location", "host", "organizer", "winner", "subject")
PERSON_FORBIDDEN_ROLES = ("location",)
EVENT_KINDS = (
    "election",
    "summit",
    "diplomatic",
    "agreement",
    "sanctions",
    "conflict",
    "terror_attack",
    "exercise",
    "protest",
    "disaster",
    "health",
    "outage",
    "cyber",
    "product_launch",
    "corporate",
    "market",
    "other",
)
PARTICIPANT_TYPES = ("country", "organization", "person")
DATE_PRECISIONS = ("day", "month", "year")
STATUSES = ("proposed", "confirmed", "rejected")
# One event is circumstantial; LLM/manual proposals backed by a single event never claim more.
SINGLE_EVENT_CONFIDENCE_CAP = 0.7
DEFAULT_REVIEW_MONTHS = 6


class GeopoliticsError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# --- helpers -----------------------------------------------------------------


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def content_hash(value: str) -> str:
    return hashlib.sha256(normalize_text(value).casefold().encode("utf-8")).hexdigest()


def parse_event_date(raw) -> tuple[datetime.date, str]:
    """Accept YYYY-MM-DD, YYYY-MM or YYYY; returns the first day plus the precision."""
    if isinstance(raw, datetime.date):
        return raw, "day"
    text = str(raw or "").strip()
    for pattern, precision in (
        (r"^(\d{4})-(\d{2})-(\d{2})$", "day"),
        (r"^(\d{4})-(\d{2})$", "month"),
        (r"^(\d{4})$", "year"),
    ):
        match = re.match(pattern, text)
        if match:
            parts = [int(p) for p in match.groups()]
            parts += [1] * (3 - len(parts))
            try:
                return datetime.date(*parts), precision
            except ValueError:
                break
    raise GeopoliticsError("event_date must be YYYY-MM-DD, YYYY-MM or YYYY")


def _parse_date_only(raw, field: str) -> datetime.date:
    try:
        return parse_event_date(raw)[0]
    except GeopoliticsError as exc:
        raise GeopoliticsError(f"{field}: {exc.message}") from exc


def name_key(value) -> str:
    """Identity of a name: NFC, collapsed spaces, casefold. Accents are kept ('Łódź' is not 'Lodz')."""
    return normalize_text(unicodedata.normalize("NFC", str(value or ""))).casefold()


def search_key(value) -> str:
    """Search form of a name: accents and punctuation folded. Never an identity."""
    folded = unidecode(unicodedata.normalize("NFC", str(value or ""))).lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def parse_optional_date(raw) -> tuple[datetime.date | None, str]:
    """Like ``parse_event_date`` but a missing date is allowed: ``(None, 'unknown')``."""
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "unknown", "nieznana")):
        return None, "unknown"
    return parse_event_date(raw)


def event_dedup_key(
    title: str,
    event_date: datetime.date | None,
    country_ids: list[int],
    organization_ids: list[int] = (),
    person_ids: list[int] = (),
) -> str:
    """Identity of a REPORT of an event, not of the event: the same title, date and participants.

    A dated, countries-only event keeps the formula of ADR-033, so keys of existing rows stay valid.
    """
    date_part = event_date.isoformat() if event_date else "undated"
    base = f"{normalize_text(title).casefold()}|{date_part}|{','.join(map(str, sorted(set(country_ids))))}"
    if organization_ids or person_ids:
        base += (
            f"|o:{','.join(map(str, sorted(set(organization_ids))))}|p:{','.join(map(str, sorted(set(person_ids))))}"
        )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def validate_axis(axis) -> str:
    if axis not in AXES:
        raise GeopoliticsError(f"axis must be one of: {', '.join(AXES)}")
    return axis


def validate_score(score) -> int:
    if isinstance(score, bool) or not isinstance(score, int) or not -2 <= score <= 2:
        raise GeopoliticsError("score must be an integer from -2 to 2")
    return score


def validate_confidence(confidence) -> float:
    if confidence is None:
        return 0.5
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise GeopoliticsError("confidence must be a number from 0 to 1") from exc
    if not 0 <= value <= 1:
        raise GeopoliticsError("confidence must be a number from 0 to 1")
    return round(value, 2)


# --- countries ---------------------------------------------------------------


def list_countries(session) -> list[dict]:
    rows = session.scalars(select(Country).where(Country.active.is_(True)).order_by(Country.name_pl)).all()
    return [country_to_dict(row) for row in rows]


def country_to_dict(country: Country) -> dict:
    return {
        "id": country.id,
        "slug": country.slug,
        "name_pl": country.name_pl,
        "iso3": country.iso3,
        "map_code": country.map_code,
        "entity_kind": country.entity_kind,
    }


def resolve_country(session, ref) -> Country:
    """A country by id or slug (``kraj-`` prefix tolerated)."""
    country = None
    if isinstance(ref, int) and not isinstance(ref, bool):
        country = session.get(Country, ref)
    elif isinstance(ref, str) and ref.strip():
        slug = ref.strip().removeprefix("kraj-")
        country = session.scalar(select(Country).where(Country.slug == slug))
    if country is None:
        raise GeopoliticsError(f"Unknown country: {ref!r}", 404)
    return country


# --- events ------------------------------------------------------------------


def validate_kind(kind) -> str:
    if kind not in EVENT_KINDS:
        raise GeopoliticsError(f"kind must be one of: {', '.join(EVENT_KINDS)}")
    return kind


def _check_dates(start: datetime.date | None, end: datetime.date | None, is_ongoing: bool) -> None:
    if end is not None and start is None:
        raise GeopoliticsError("an event with an end date needs a start date")
    if end is not None and start is not None and end < start:
        raise GeopoliticsError("event_date_end must not be before event_date")
    if is_ongoing and end is not None:
        raise GeopoliticsError("an ongoing event has no end date")


def _resolve_registry_row(session, model, ref, label: str):
    """An organization or person by id, or by exact canonical name (ignoring case)."""
    row = None
    if isinstance(ref, int) and not isinstance(ref, bool):
        row = session.get(model, ref)
    elif isinstance(ref, str) and ref.strip():
        matches = session.scalars(
            select(model).where(func.lower(model.canonical_name) == ref.strip().lower()).limit(2)
        ).all()
        if len(matches) > 1:
            raise GeopoliticsError(f"More than one {label} is called {ref!r}; use the id", 409)
        row = matches[0] if matches else None
    if row is None:
        raise GeopoliticsError(f"Unknown {label}: {ref!r}", 404)
    return row


def resolve_participant(session, spec) -> tuple[str, object, str]:
    """``(type, row, role)`` from ``(country, role)`` or ``{type, ref|id|name|country, role}``."""
    if isinstance(spec, (tuple, list)) and len(spec) == 2:
        ptype, ref, role = "country", spec[0], spec[1]
    elif isinstance(spec, dict):
        ptype = spec.get("type") or ("country" if "country" in spec else None)
        ref = spec.get("ref", spec.get("id", spec.get("country", spec.get("name"))))
        role = spec.get("role")
    else:
        raise GeopoliticsError("a participant needs a type, a reference and a role")
    if ptype not in PARTICIPANT_TYPES:
        raise GeopoliticsError(f"participant type must be one of: {', '.join(PARTICIPANT_TYPES)}")
    if role not in ROLES:
        raise GeopoliticsError(f"participant role must be one of: {', '.join(ROLES)}")
    if ptype == "person" and role in PERSON_FORBIDDEN_ROLES:
        raise GeopoliticsError(f"a person cannot have the role {role!r}")
    if ptype == "country":
        row = resolve_country(session, ref)
    elif ptype == "organization":
        row = _resolve_registry_row(session, Organization, ref, "organization")
    else:
        row = _resolve_registry_row(session, Person, ref, "person")
    return ptype, row, role


def _attach_participants(event: GeoEvent, resolved: list[tuple[str, object, str]]) -> None:
    seen = set()
    for ptype, row, role in resolved:
        if (ptype, row.id, role) in seen:
            continue
        seen.add((ptype, row.id, role))
        if ptype == "country":
            event.participants.append(GeoEventParticipant(country_id=row.id, role=role))
        elif ptype == "organization":
            event.organizations.append(GeoEventOrganization(organization_id=row.id, role=role))
        else:
            event.persons.append(GeoEventPerson(person_id=row.id, role=role))


def _ensure_aliases(event: GeoEvent, names) -> None:
    known = {alias.name_key for alias in event.aliases}
    for name in names:
        alias = normalize_text(name)
        key = name_key(alias)
        if not key or key in known:
            continue
        known.add(key)
        event.aliases.append(GeoEventAlias(alias=alias, name_key=key, search_key=search_key(alias)))


def _attach_to_existing(session, existing: GeoEvent, source, aliases) -> None:
    if source:
        _add_source(session, existing, source)
    if aliases:
        _ensure_aliases(existing, aliases)
        session.flush()


def create_event(
    session,
    *,
    title: str,
    event_date=None,
    participants=(),
    description: str | None = None,
    date_precision: str | None = None,
    event_date_end=None,
    end_date_precision: str | None = None,
    is_ongoing: bool = False,
    kind: str = "other",
    aliases=(),
    source: dict | None = None,
    status: str = "proposed",
    detection_method: str = "manual",
    model: str | None = None,
    prompt_version: str | None = None,
    user_id: int | None = None,
) -> tuple[GeoEvent, bool]:
    """Create an event, or attach a source to the equivalent one. Returns (event, created).

    Neither a date nor a participant is required. A rejected equivalent is never revived: the same report
    cannot re-propose a decision the reader already refused. A repeated report adds a source instead of a
    second event; two analyses racing for the same report end up with one row (unique ``dedup_key``).
    """
    title = normalize_text(title)
    if not title:
        raise GeopoliticsError("title is required")
    if status not in STATUSES:
        raise GeopoliticsError("invalid status")
    kind = validate_kind(kind)
    date_value, precision = parse_optional_date(event_date)
    if date_precision and date_value is not None:
        if date_precision not in DATE_PRECISIONS:
            raise GeopoliticsError("date_precision must be day, month or year")
        precision = date_precision
    end_value, end_precision = (None, None)
    if event_date_end not in (None, ""):
        end_value, end_precision = parse_event_date(event_date_end)
        end_precision = end_date_precision or end_precision
    _check_dates(date_value, end_value, bool(is_ongoing))
    resolved = [resolve_participant(session, spec) for spec in participants or ()]

    key = event_dedup_key(
        title,
        date_value,
        [row.id for ptype, row, _ in resolved if ptype == "country"],
        [row.id for ptype, row, _ in resolved if ptype == "organization"],
        [row.id for ptype, row, _ in resolved if ptype == "person"],
    )
    existing = session.scalar(select(GeoEvent).where(GeoEvent.dedup_key == key).order_by(GeoEvent.id))
    if existing is not None:
        _attach_to_existing(session, existing, source, aliases)
        return existing, False

    event = GeoEvent(
        title=title,
        description=normalize_text(description) if description else None,
        event_date=date_value,
        date_precision=precision,
        event_date_end=end_value,
        end_date_precision=end_precision,
        is_ongoing=bool(is_ongoing),
        kind=kind,
        status=status,
        detection_method=detection_method,
        model=model,
        prompt_version=prompt_version,
        dedup_key=key,
        created_by_user_id=user_id,
    )
    if status != "proposed":
        event.decided_at = datetime.datetime.now()
        event.decided_by_user_id = user_id
    _attach_participants(event, resolved)
    _ensure_aliases(event, [title, *aliases])
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        # Lost a race with an equal report: keep the winner instead of failing the whole request.
        existing = session.scalar(select(GeoEvent).where(GeoEvent.dedup_key == key).order_by(GeoEvent.id))
        if existing is None:
            raise
        _attach_to_existing(session, existing, source, aliases)
        return existing, False
    if source:
        _add_source(session, event, source)
    return event, True


def update_event(session, event: GeoEvent, *, expected_version: int | None = None, **changes) -> GeoEvent:
    """Edit descriptive fields: title, description, kind, event_date, event_date_end, is_ongoing.

    A stale ``expected_version`` is a conflict (409). The identity key is not recomputed: an edited event is
    still the event the first report created. A new title keeps the old one as an alias.
    """
    allowed = {"title", "description", "kind", "event_date", "event_date_end", "is_ongoing"}
    unknown = set(changes) - allowed
    if unknown:
        raise GeopoliticsError(f"cannot change: {', '.join(sorted(unknown))}")
    if expected_version is not None and event.version != expected_version:
        raise GeopoliticsError("The event changed since you loaded it; reload", 409)
    if "title" in changes:
        title = normalize_text(changes["title"])
        if not title:
            raise GeopoliticsError("title is required")
        event.title = title
        _ensure_aliases(event, [title])
    if "description" in changes:
        event.description = normalize_text(changes["description"]) or None
    if "kind" in changes:
        event.kind = validate_kind(changes["kind"])
    if "event_date" in changes:
        event.event_date, event.date_precision = parse_optional_date(changes["event_date"])
    if "event_date_end" in changes:
        raw = changes["event_date_end"]
        if raw in (None, ""):
            event.event_date_end, event.end_date_precision = None, None
        else:
            event.event_date_end, event.end_date_precision = parse_event_date(raw)
    if "is_ongoing" in changes:
        event.is_ongoing = bool(changes["is_ongoing"])
    _check_dates(event.event_date, event.event_date_end, event.is_ongoing)
    event.version += 1
    session.flush()
    return event


def add_participant(session, event: GeoEvent, spec) -> GeoEvent:
    ptype, row, role = resolve_participant(session, spec)
    _attach_participants(event, [(ptype, row, role)])
    session.flush()
    session.refresh(event)
    return event


def remove_participant(session, event: GeoEvent, ptype: str, participant_id: int, role: str) -> GeoEvent:
    """Remove one participant row; a country that a CONFIRMED assessment's direct evidence needs stays."""
    if ptype == "country":
        grounded = session.scalar(
            select(func.count())
            .select_from(CountryRelationEvidence)
            .join(CountryRelationAssessment, CountryRelationAssessment.id == CountryRelationEvidence.assessment_id)
            .where(
                CountryRelationEvidence.event_id == event.id,
                CountryRelationEvidence.evidence_kind == "direct",
                CountryRelationAssessment.status == "confirmed",
                or_(
                    CountryRelationAssessment.from_country_id == participant_id,
                    CountryRelationAssessment.to_country_id == participant_id,
                ),
            )
        )
        if grounded:
            raise GeopoliticsError("A confirmed assessment relies on this country in this event", 409)
        rows = [p for p in event.participants if p.country_id == participant_id and p.role == role]
    elif ptype == "organization":
        rows = [p for p in event.organizations if p.organization_id == participant_id and p.role == role]
    elif ptype == "person":
        rows = [p for p in event.persons if p.person_id == participant_id and p.role == role]
    else:
        raise GeopoliticsError(f"participant type must be one of: {', '.join(PARTICIPANT_TYPES)}")
    if not rows:
        raise GeopoliticsError("No such participant in this event", 404)
    for row in rows:
        session.delete(row)
    session.flush()
    session.refresh(event)
    return event


def add_alias(session, event: GeoEvent, alias: str) -> GeoEventAlias:
    alias = normalize_text(alias)
    key = name_key(alias)
    if not key:
        raise GeopoliticsError("alias is required")
    if any(existing.name_key == key for existing in event.aliases):
        raise GeopoliticsError("The event already has this name", 409)
    row = GeoEventAlias(alias=alias, name_key=key, search_key=search_key(alias))
    event.aliases.append(row)
    session.flush()
    return row


def remove_alias(session, event: GeoEvent, alias_id: int) -> None:
    row = next((a for a in event.aliases if a.id == alias_id), None)
    if row is None:
        raise GeopoliticsError("No such alias in this event", 404)
    if row.name_key == name_key(event.title):
        raise GeopoliticsError("The canonical title cannot be removed; rename the event first", 400)
    event.aliases.remove(row)
    session.flush()


def _add_source(session, event: GeoEvent, source: dict) -> GeoEventSource | None:
    document_id = source.get("document_id")
    quote = normalize_text(source.get("quote") or source.get("anchor_quote") or "")
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        raise GeopoliticsError("source.document_id must be an integer")
    if not quote:
        raise GeopoliticsError("source.quote is required")
    if session.get(Document, document_id) is None:
        raise GeopoliticsError("Source document not found", 404)
    stance = source.get("stance") or "supports"
    if stance not in ("supports", "disputes"):
        raise GeopoliticsError("source.stance must be supports or disputes")
    document_event_id = source.get("document_event_id")
    if document_event_id is not None:
        timeline_row = session.get(DocumentEvent, document_event_id)
        if timeline_row is None or timeline_row.document_id != document_id:
            raise GeopoliticsError("source.document_event_id does not belong to that document", 400)
    digest = content_hash(quote)
    for existing in event.sources:
        if existing.document_id == document_id and existing.content_hash == digest:
            return existing
    row = GeoEventSource(
        event_id=event.id,
        document_id=document_id,
        anchor_quote=quote,
        content_hash=digest,
        stance=stance,
        document_event_id=document_event_id,
    )
    session.add(row)
    session.flush()
    session.refresh(event)
    return row


def add_source(session, event: GeoEvent, source: dict) -> GeoEventSource:
    """Cite one more document passage for an existing event (idempotent per document + quote)."""
    if not isinstance(source, dict):
        raise GeopoliticsError("source must be an object")
    return _add_source(session, event, source)


def set_event_status(session, event: GeoEvent, status: str, user_id: int | None) -> GeoEvent:
    if status not in ("confirmed", "rejected"):
        raise GeopoliticsError("status must be confirmed or rejected")
    event.status = status
    event.decided_at = datetime.datetime.now()
    event.decided_by_user_id = user_id
    session.flush()
    return event


def _participant_dicts(event: GeoEvent) -> list[dict]:
    order = {role: index for index, role in enumerate(ROLES)}
    items: list[tuple[tuple, dict]] = []
    for p in event.participants:
        items.append(
            (
                (0, order[p.role], p.country.name_pl),
                {"type": "country", "role": p.role, "country": country_to_dict(p.country)},
            )
        )
    for p in event.organizations:
        item = {
            "type": "organization",
            "role": p.role,
            "organization": {"id": p.organization.id, "name": p.organization.canonical_name},
        }
        items.append(((1, order[p.role], p.organization.canonical_name), item))
    for p in event.persons:
        item = {"type": "person", "role": p.role, "person": {"id": p.person.id, "name": p.person.canonical_name}}
        items.append(((2, order[p.role], p.person.canonical_name), item))
    return [item for _, item in sorted(items, key=lambda pair: pair[0])]


def event_to_dict(event: GeoEvent, *, with_documents: bool = True) -> dict:
    data = {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "kind": event.kind,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "date_precision": event.date_precision,
        "event_date_end": event.event_date_end.isoformat() if event.event_date_end else None,
        "end_date_precision": event.end_date_precision,
        "is_ongoing": event.is_ongoing,
        "status": event.status,
        "version": event.version,
        "detection_method": event.detection_method,
        "model": event.model,
        "prompt_version": event.prompt_version,
        "aliases": [{"id": a.id, "alias": a.alias} for a in sorted(event.aliases, key=lambda a: a.id)],
        "participants": _participant_dicts(event),
    }
    if with_documents:
        data["sources"] = [
            {
                "id": s.id,
                "document_id": s.document_id,
                "quote": s.anchor_quote,
                "stance": s.stance,
            }
            for s in event.sources
        ]
    return data


def list_events(
    session,
    *,
    status: str | None = None,
    country_id: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    with_countries: bool | None = None,
    undated: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[GeoEvent], int]:
    query = select(GeoEvent)
    if status:
        if status not in STATUSES:
            raise GeopoliticsError("invalid status")
        query = query.where(GeoEvent.status == status)
    if kind:
        query = query.where(GeoEvent.kind == validate_kind(kind))
    if country_id is not None:
        query = query.where(
            GeoEvent.id.in_(select(GeoEventParticipant.event_id).where(GeoEventParticipant.country_id == country_id))
        )
    has_country = GeoEvent.id.in_(select(GeoEventParticipant.event_id))
    if with_countries is True:
        query = query.where(has_country)
    elif with_countries is False:
        query = query.where(~has_country)
    if undated is True:
        query = query.where(GeoEvent.event_date.is_(None))
    elif undated is False:
        query = query.where(GeoEvent.event_date.is_not(None))
    if q and search_key(q):
        needle = f"%{search_key(q)}%"
        query = query.where(
            GeoEvent.id.in_(select(GeoEventAlias.event_id).where(GeoEventAlias.search_key.like(needle)))
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(GeoEvent.event_date.desc().nulls_last(), GeoEvent.id.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), total


# --- assessments -------------------------------------------------------------


def assessment_to_dict(
    row: CountryRelationAssessment, *, today: datetime.date | None = None, with_evidence=False
) -> dict:
    today = today or datetime.date.today()
    data = {
        "id": row.id,
        "from_country": country_to_dict(row.from_country),
        "to_country": country_to_dict(row.to_country),
        "axis": row.axis,
        "score": row.score,
        "confidence": float(row.confidence),
        "valid_from": row.valid_from.isoformat(),
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "review_due_at": row.review_due_at.isoformat() if row.review_due_at else None,
        "overdue": bool(row.status == "confirmed" and row.review_due_at and row.review_due_at < today),
        "rationale": row.rationale,
        "status": row.status,
        "detection_method": row.detection_method,
        "model": row.model,
        "prompt_version": row.prompt_version,
        "supersedes_id": row.supersedes_id,
        "version": row.version,
    }
    if with_evidence:
        data["evidence"] = [
            {"event": event_to_dict(ev.event), "stance": ev.stance, "kind": ev.evidence_kind}
            for ev in sorted(row.evidence, key=lambda e: (e.event.event_date or datetime.date.max, e.event_id))
        ]
    return data


def _check_direct_evidence(session, source: Country, target: Country, event_id: int) -> None:
    """A direct piece of evidence names both countries of the assessment; anything less is context."""
    event = session.get(GeoEvent, event_id)
    if event is None:
        raise GeopoliticsError(f"Unknown event: {event_id}", 404)
    covered = {p.country_id for p in event.participants}
    if not {source.id, target.id} <= covered:
        raise GeopoliticsError(
            f"Direct evidence must name both {source.name_pl} and {target.name_pl}; event {event_id} does not "
            "(attach it as context evidence instead)",
            400,
        )


def _check_context_event(session, event_id: int) -> None:
    if session.get(GeoEvent, event_id) is None:
        raise GeopoliticsError(f"Unknown event: {event_id}", 404)


def create_assessment(
    session,
    *,
    from_country,
    to_country,
    axis,
    score,
    valid_from,
    confidence=None,
    rationale: str | None = None,
    event_ids: list[int] | None = None,
    context_event_ids: list[int] | None = None,
    status: str = "proposed",
    detection_method: str = "manual",
    model: str | None = None,
    prompt_version: str | None = None,
    user_id: int | None = None,
) -> CountryRelationAssessment:
    """Create a PROPOSED assessment (or a confirmed one right away for a manual decision).

    ``event_ids`` are DIRECT evidence: every such event names both countries. ``context_event_ids`` are
    background (an election in one of them, an outage) and never justify the score; they need a rationale.
    """
    source = resolve_country(session, from_country)
    target = resolve_country(session, to_country)
    if source.id == target.id:
        raise GeopoliticsError("from and to must be different countries")
    validate_axis(axis)
    validate_score(score)
    conf = validate_confidence(confidence)
    start = _parse_date_only(valid_from, "valid_from")
    event_ids = list(dict.fromkeys(event_ids or []))
    for event_id in event_ids:
        _check_direct_evidence(session, source, target, event_id)
    context_ids = [i for i in dict.fromkeys(context_event_ids or []) if i not in event_ids]
    for event_id in context_ids:
        _check_context_event(session, event_id)
    if context_ids and not normalize_text(rationale or ""):
        raise GeopoliticsError("A rationale is required when context events are attached")
    if independent_document_count(session, event_ids) < 2:
        conf = min(conf, SINGLE_EVENT_CONFIDENCE_CAP)
    if status not in ("proposed", "confirmed"):
        raise GeopoliticsError("status must be proposed or confirmed")

    row = CountryRelationAssessment(
        from_country_id=source.id,
        to_country_id=target.id,
        axis=axis,
        score=score,
        confidence=conf,
        valid_from=start,
        rationale=normalize_text(rationale) if rationale else None,
        status="proposed",
        detection_method=detection_method,
        model=model,
        prompt_version=prompt_version,
        created_by_user_id=user_id,
    )
    for event_id in event_ids:
        row.evidence.append(CountryRelationEvidence(event_id=event_id, evidence_kind="direct"))
    for event_id in context_ids:
        row.evidence.append(CountryRelationEvidence(event_id=event_id, evidence_kind="context"))
    session.add(row)
    session.flush()
    if status == "confirmed":
        confirm_assessment(session, row, user_id=user_id)
    return row


def independent_document_count(session, event_ids: list[int]) -> int:
    """How many distinct documents report the given events.

    Several events from one article are still ONE source, so they do not lift the
    confidence cap that a single report gets.
    """
    if not event_ids:
        return 0
    rows = session.scalars(
        select(GeoEventSource.document_id).where(GeoEventSource.event_id.in_(event_ids)).distinct()
    ).all()
    return len(set(rows))


def propose_assessment(session, **kwargs) -> tuple[CountryRelationAssessment, bool]:
    """Like ``create_assessment`` for a PROPOSAL, but a repeat of an open proposal adds evidence.

    Several events of one article usually point at the same relation (US-Laos, -1, same
    day). They become one proposal with several pieces of evidence instead of a queue of
    identical cards, of which only the first could ever be confirmed. A proposal with a
    different score for the same pair, axis and start stays separate so the disagreement
    is visible. Returns (assessment, created).
    """
    source = resolve_country(session, kwargs["from_country"])
    target = resolve_country(session, kwargs["to_country"])
    start = _parse_date_only(kwargs["valid_from"], "valid_from")
    score = validate_score(kwargs["score"])
    axis = validate_axis(kwargs["axis"])
    existing = session.scalar(
        select(CountryRelationAssessment).where(
            CountryRelationAssessment.from_country_id == source.id,
            CountryRelationAssessment.to_country_id == target.id,
            CountryRelationAssessment.axis == axis,
            CountryRelationAssessment.valid_from == start,
            CountryRelationAssessment.score == score,
            CountryRelationAssessment.status == "proposed",
        )
    )
    if existing is None:
        return create_assessment(session, **kwargs), True
    known = {evidence.event_id: evidence for evidence in existing.evidence}
    for event_id in dict.fromkeys(kwargs.get("event_ids") or []):
        row = known.get(event_id)
        if row is not None and row.evidence_kind == "direct":
            continue
        _check_direct_evidence(session, source, target, event_id)  # also guards a context -> direct promotion
        if row is not None:
            row.evidence_kind = "direct"
        else:
            known[event_id] = CountryRelationEvidence(event_id=event_id, evidence_kind="direct")
            existing.evidence.append(known[event_id])
    for event_id in dict.fromkeys(kwargs.get("context_event_ids") or []):
        if event_id not in known:  # never downgrades direct evidence
            _check_context_event(session, event_id)
            known[event_id] = CountryRelationEvidence(event_id=event_id, evidence_kind="context")
            existing.evidence.append(known[event_id])
    session.flush()
    return existing, False


def confirm_assessment(
    session,
    row: CountryRelationAssessment,
    *,
    user_id: int | None,
    today: datetime.date | None = None,
) -> CountryRelationAssessment:
    """Make a proposal the current assessment, closing the previous open period.

    A change dated before an already confirmed period starts would need that period split,
    which the MVP refuses (409) instead of rewriting history.
    """
    if row.status != "proposed":
        raise GeopoliticsError(f"Assessment is already {row.status}", 409)
    today = today or datetime.date.today()
    siblings = session.scalars(
        select(CountryRelationAssessment)
        .where(
            CountryRelationAssessment.from_country_id == row.from_country_id,
            CountryRelationAssessment.to_country_id == row.to_country_id,
            CountryRelationAssessment.axis == row.axis,
            CountryRelationAssessment.status == "confirmed",
            CountryRelationAssessment.id != row.id,
        )
        .with_for_update(of=CountryRelationAssessment)
    ).all()
    previous = None
    for other in siblings:
        if other.valid_from >= row.valid_from:
            raise GeopoliticsError(
                "A confirmed assessment of this pair and axis already starts on or after "
                f"{row.valid_from.isoformat()}; correcting the past is not supported yet",
                409,
            )
        if other.valid_to is None or other.valid_to > row.valid_from:
            previous = other
    if previous is not None:
        previous.valid_to = row.valid_from
        row.supersedes_id = previous.id
        session.flush()
    row.status = "confirmed"
    row.decided_at = datetime.datetime.now()
    row.decided_by_user_id = user_id
    row.version += 1
    if row.review_due_at is None:
        row.review_due_at = _add_months(max(today, row.valid_from), DEFAULT_REVIEW_MONTHS)
    try:
        session.flush()
    except IntegrityError as exc:  # exclusion constraint: a concurrent confirmation won the race
        session.rollback()
        raise GeopoliticsError("The relation was changed concurrently; reload and decide again", 409) from exc
    return row


def _add_months(day: datetime.date, months: int) -> datetime.date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last = [
        31,
        29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    return datetime.date(year, month, min(day.day, last))


def decide_assessment(
    session,
    assessment_id: int,
    *,
    decision: str,
    expected_version: int | None,
    user_id: int | None,
    approve_events: bool = True,
) -> CountryRelationAssessment:
    row = session.scalar(
        select(CountryRelationAssessment)
        .where(CountryRelationAssessment.id == assessment_id)
        .with_for_update(of=CountryRelationAssessment)
    )
    if row is None:
        raise GeopoliticsError("Assessment not found", 404)
    if expected_version is not None and row.version != expected_version:
        raise GeopoliticsError("The assessment changed since you loaded it; reload", 409)
    if decision == "approve":
        confirm_assessment(session, row, user_id=user_id)
        if approve_events:
            for evidence in row.evidence:
                if evidence.event.status == "proposed":
                    set_event_status(session, evidence.event, "confirmed", user_id)
    elif decision == "reject":
        if row.status != "proposed":
            raise GeopoliticsError(f"Assessment is already {row.status}", 409)
        row.status = "rejected"
        row.decided_at = datetime.datetime.now()
        row.decided_by_user_id = user_id
        row.version += 1
        session.flush()
    else:
        raise GeopoliticsError("decision must be approve or reject")
    return row


def list_proposals(session, *, limit: int = 50) -> list[dict]:
    """Pending assessments with the current confirmed one they would replace."""
    rows = session.scalars(
        select(CountryRelationAssessment)
        .where(CountryRelationAssessment.status == "proposed")
        .order_by(CountryRelationAssessment.created_at.desc())
        .limit(limit)
    ).all()
    out = []
    for row in rows:
        current = session.scalar(
            select(CountryRelationAssessment).where(
                CountryRelationAssessment.from_country_id == row.from_country_id,
                CountryRelationAssessment.to_country_id == row.to_country_id,
                CountryRelationAssessment.axis == row.axis,
                CountryRelationAssessment.status == "confirmed",
                CountryRelationAssessment.valid_from <= row.valid_from,
                (CountryRelationAssessment.valid_to.is_(None)) | (CountryRelationAssessment.valid_to > row.valid_from),
            )
        )
        item = assessment_to_dict(row, with_evidence=True)
        item["current"] = assessment_to_dict(current) if current else None
        out.append(item)
    return out


def relations_at(
    session,
    *,
    country: Country,
    at: datetime.date,
    axis: str,
    direction: str,
) -> list[dict]:
    """Confirmed assessments valid on ``at``: what ``country`` thinks of others (``from``) or the reverse (``to``)."""
    validate_axis(axis)
    if direction not in ("from", "to"):
        raise GeopoliticsError("direction must be from or to")
    column = (
        CountryRelationAssessment.from_country_id if direction == "from" else CountryRelationAssessment.to_country_id
    )
    rows = session.scalars(
        select(CountryRelationAssessment).where(
            column == country.id,
            CountryRelationAssessment.axis == axis,
            CountryRelationAssessment.status == "confirmed",
            CountryRelationAssessment.valid_from <= at,
            (CountryRelationAssessment.valid_to.is_(None)) | (CountryRelationAssessment.valid_to > at),
        )
    ).all()
    out = []
    for row in rows:
        item = assessment_to_dict(row, today=at, with_evidence=True)
        other = row.to_country if direction == "from" else row.from_country
        item["other_country"] = country_to_dict(other)
        out.append(item)
    return sorted(out, key=lambda i: i["other_country"]["name_pl"])


def assessment_history(session, assessment_id: int) -> list[dict]:
    row = session.get(CountryRelationAssessment, assessment_id)
    if row is None:
        raise GeopoliticsError("Assessment not found", 404)
    rows = session.scalars(
        select(CountryRelationAssessment)
        .where(
            CountryRelationAssessment.from_country_id == row.from_country_id,
            CountryRelationAssessment.to_country_id == row.to_country_id,
            CountryRelationAssessment.axis == row.axis,
        )
        .order_by(CountryRelationAssessment.valid_from, CountryRelationAssessment.id)
    ).all()
    return [assessment_to_dict(r, with_evidence=True) for r in rows]
