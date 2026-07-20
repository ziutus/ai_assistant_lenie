"""HTTP reporting API for document counts: by type, by processing state, by
discovery source, and recent daily ingestion volume — the /stats dashboard."""

from datetime import date, datetime, time, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from library.db.engine import get_scoped_session
from library.db.models import Document, DiscoverySource

bp = Blueprint("stats", __name__)

DEFAULT_DAYS = 30
MAX_DAYS = 365
RECENT_LIMIT = 20


@bp.get("/stats")
def stats():
    days = request.args.get("days", DEFAULT_DAYS, type=int)
    if days is None or days < 1 or days > MAX_DAYS:
        return jsonify({"status": "error", "message": f"days must be between 1 and {MAX_DAYS}"}), 400

    session = get_scoped_session()

    total = session.execute(select(func.count(Document.id))).scalar_one()

    by_type = session.execute(
        select(Document.document_type, func.count().label("count"))
        .group_by(Document.document_type)
        .order_by(func.count().desc())
    ).all()

    by_state = session.execute(
        select(Document.processing_status, func.count().label("count"))
        .group_by(Document.processing_status)
        .order_by(func.count().desc())
    ).all()

    source_name = func.coalesce(DiscoverySource.name, "(brak)").label("name")
    by_source = session.execute(
        select(source_name, func.count().label("count"))
        .select_from(Document)
        .outerjoin(DiscoverySource, Document.discovery_source_id == DiscoverySource.id)
        .group_by(source_name)
        .order_by(func.count().desc())
    ).all()

    today = date.today()
    date_from = today - timedelta(days=days - 1)
    start = datetime.combine(date_from, time.min)
    day = func.date(Document.ingested_at).label("day")
    daily_rows = session.execute(
        select(day, func.count().label("count"))
        .where(Document.ingested_at >= start)
        .group_by(day)
        .order_by(day)
    ).all()
    counts_by_day = {str(r.day): r.count for r in daily_rows}
    daily = [
        {"day": (date_from + timedelta(days=i)).isoformat(),
         "count": counts_by_day.get((date_from + timedelta(days=i)).isoformat(), 0)}
        for i in range(days)
    ]

    recent_rows = session.execute(
        select(Document.id, Document.title, Document.document_type, Document.processing_status,
               source_name, Document.ingested_at)
        .select_from(Document)
        .outerjoin(DiscoverySource, Document.discovery_source_id == DiscoverySource.id)
        .order_by(Document.ingested_at.desc())
        .limit(RECENT_LIMIT)
    ).all()

    return jsonify({
        "status": "success",
        "total": total,
        "by_type": [{"document_type": r.document_type, "count": r.count} for r in by_type],
        "by_state": [{"processing_status": r.processing_status, "count": r.count} for r in by_state],
        "by_source": [{"name": r.name, "count": r.count} for r in by_source],
        "daily": daily,
        "recent": [{
            "id": r.id, "title": r.title, "document_type": r.document_type,
            "processing_status": r.processing_status, "source": r.name,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
        } for r in recent_rows],
    }), 200
