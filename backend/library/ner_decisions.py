"""Read-only browsing of automatic NER context decisions."""

from sqlalchemy import func, select

from library.db.models import Document, NerContextClassification


def parse_decision_filters(args):
    """Validate HTTP parameters before opening a database session."""
    result = {}
    for name, default, minimum, maximum in [
        ("limit", 50, 1, 200), ("offset", 0, 0, None), ("document_id", None, 1, None),
    ]:
        value = args.get(name, default)
        if value is None:
            continue
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Nieprawidłowy parametr: {name}.") from None
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"Nieprawidłowy parametr: {name}.")
        result[name] = value
    for name, choices in {
        "entity_type": {"persName", "placeName"},
        "predicted_class": {"place", "not_place", "organization", "person", "not_person", "uncertain"},
        "confidence": {"high", "medium", "low"},
    }.items():
        if name in args:
            if args[name] not in choices:
                raise ValueError(f"Nieprawidłowy parametr: {name}.")
            result[name] = args[name]
    for name in ("dropped", "latest_only"):
        if name in args:
            if args[name] not in {"true", "false"}:
                raise ValueError(f"Nieprawidłowy parametr: {name}.")
            result[name] = args[name] == "true"
    if "q" in args:
        result["q"] = args["q"]
    return result


def list_decisions(session, *, limit=50, offset=0, latest_only=False, q=None, **filters):
    """Rank the complete history first, then filter and paginate current verdicts."""
    model = NerContextClassification
    ranked = select(*model.__table__.c, func.row_number().over(
        partition_by=(model.document_id, model.entity_type, model.entity_text),
        order_by=(model.created_at.desc(), model.id.desc()),
    ).label("position")).subquery()
    query = select(*[ranked.c[column.name] for column in model.__table__.c])
    if latest_only:
        query = query.where(ranked.c.position == 1)
    for name, value in filters.items():
        query = query.where(ranked.c[name] == value)
    if q is not None:
        query = query.where(ranked.c.entity_text.icontains(q, autoescape=True))
    filtered = query.subquery()
    counts = session.execute(select(
        filtered.c.predicted_class, filtered.c.dropped, func.count(),
    ).group_by(filtered.c.predicted_class, filtered.c.dropped)).all()
    summary = {"total": 0, "dropped": 0, "by_class": {}}
    for verdict, dropped, count in counts:
        summary["total"] += count
        summary["dropped"] += count if dropped else 0
        summary["by_class"][verdict] = summary["by_class"].get(verdict, 0) + count
    rows = session.execute(select(
        filtered, Document.title.label("document_title"), Document.document_type,
    ).outerjoin(Document, Document.id == filtered.c.document_id)
        .order_by(filtered.c.created_at.desc(), filtered.c.id.desc()).limit(limit).offset(offset)).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["created_at"] = item["created_at"].isoformat() if item["created_at"] else None
        items.append(item)
    return {"total": summary["total"], "limit": limit, "offset": offset, "items": items, "summary": summary}
