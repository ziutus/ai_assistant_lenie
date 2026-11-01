"""Geopolitics: source-backed world events and versioned, directed country-relation assessments.

ADR-033. A *geo event* is something that happened (with cited documents). A *relation
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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    Document,
    GeoEvent,
    GeoEventParticipant,
    GeoEventSource,
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
ROLES = ("actor", "target", "affected", "location")
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


def event_dedup_key(title: str, event_date: datetime.date, country_ids: list[int]) -> str:
    base = f"{normalize_text(title).casefold()}|{event_date.isoformat()}|{','.join(map(str, sorted(set(country_ids))))}"
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


def create_event(
    session,
    *,
    title: str,
    event_date,
    participants: list[tuple[object, str]],
    description: str | None = None,
    date_precision: str | None = None,
    source: dict | None = None,
    status: str = "proposed",
    detection_method: str = "manual",
    model: str | None = None,
    prompt_version: str | None = None,
    user_id: int | None = None,
) -> tuple[GeoEvent, bool]:
    """Create an event, or attach a source to the equivalent one. Returns (event, created).

    A rejected equivalent is never revived: the same report cannot re-propose a decision
    the reader already refused. A repeated report adds a source instead of a second event.
    """
    title = normalize_text(title)
    if not title:
        raise GeopoliticsError("title is required")
    if status not in STATUSES:
        raise GeopoliticsError("invalid status")
    date_value, precision = parse_event_date(event_date)
    precision = date_precision or precision
    if not participants:
        raise GeopoliticsError("at least one participant is required")
    resolved: list[tuple[Country, str]] = []
    for ref, role in participants:
        if role not in ROLES:
            raise GeopoliticsError(f"participant role must be one of: {', '.join(ROLES)}")
        resolved.append((resolve_country(session, ref), role))

    key = event_dedup_key(title, date_value, [country.id for country, _ in resolved])
    existing = session.scalar(select(GeoEvent).where(GeoEvent.dedup_key == key).order_by(GeoEvent.id))
    if existing is not None:
        if source:
            _add_source(session, existing, source)
        return existing, False

    event = GeoEvent(
        title=title,
        description=normalize_text(description) if description else None,
        event_date=date_value,
        date_precision=precision,
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
    for country, role in dict.fromkeys((c.id, r) for c, r in resolved):
        event.participants.append(GeoEventParticipant(country_id=country, role=role))
    session.add(event)
    session.flush()
    if source:
        _add_source(session, event, source)
    return event, True


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
    )
    session.add(row)
    session.flush()
    session.refresh(event)
    return row


def set_event_status(session, event: GeoEvent, status: str, user_id: int | None) -> GeoEvent:
    if status not in ("confirmed", "rejected"):
        raise GeopoliticsError("status must be confirmed or rejected")
    event.status = status
    event.decided_at = datetime.datetime.now()
    event.decided_by_user_id = user_id
    session.flush()
    return event


def event_to_dict(event: GeoEvent, *, with_documents: bool = True) -> dict:
    data = {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "event_date": event.event_date.isoformat(),
        "date_precision": event.date_precision,
        "status": event.status,
        "detection_method": event.detection_method,
        "model": event.model,
        "prompt_version": event.prompt_version,
        "participants": [
            {"country": country_to_dict(p.country), "role": p.role}
            for p in sorted(event.participants, key=lambda p: (ROLES.index(p.role), p.country.name_pl))
        ],
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
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[GeoEvent], int]:
    from sqlalchemy import func

    query = select(GeoEvent)
    if status:
        if status not in STATUSES:
            raise GeopoliticsError("invalid status")
        query = query.where(GeoEvent.status == status)
    if country_id is not None:
        query = query.where(
            GeoEvent.id.in_(select(GeoEventParticipant.event_id).where(GeoEventParticipant.country_id == country_id))
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(GeoEvent.event_date.desc(), GeoEvent.id.desc()).limit(limit).offset(offset)
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
            {"event": event_to_dict(ev.event), "stance": ev.stance}
            for ev in sorted(row.evidence, key=lambda e: e.event.event_date)
        ]
    return data


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
    status: str = "proposed",
    detection_method: str = "manual",
    model: str | None = None,
    prompt_version: str | None = None,
    user_id: int | None = None,
) -> CountryRelationAssessment:
    """Create a PROPOSED assessment (or a confirmed one right away for a manual decision)."""
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
        if session.get(GeoEvent, event_id) is None:
            raise GeopoliticsError(f"Unknown event: {event_id}", 404)
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
        row.evidence.append(CountryRelationEvidence(event_id=event_id))
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
    known = {evidence.event_id for evidence in existing.evidence}
    for event_id in dict.fromkeys(kwargs.get("event_ids") or []):
        if event_id not in known:
            if session.get(GeoEvent, event_id) is None:
                raise GeopoliticsError(f"Unknown event: {event_id}", 404)
            existing.evidence.append(CountryRelationEvidence(event_id=event_id))
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
