"""REST for database additions to the curated NER gazetteers (ADR-029); writes need a service key."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from library.db.engine import get_scoped_session
from library.db.models import NerGazetteerEntry
from library.ner_gazetteer_store import (
    KINDS,
    GazetteerValidationError,
    invalidate_cache,
    validate_entry,
)

bp = Blueprint("ner_gazetteer", __name__)


def _require_service() -> None:
    if getattr(getattr(g, "auth", None), "kind", None) != "service":
        abort(403, "Zapis gazetteera wymaga klucza service")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    for key in ("note", "created_by"):
        if data.get(key) is not None and not isinstance(data[key], str):
            abort(400, f"{key} musi być tekstem")
    source_id = data.get("source_document_id")
    if source_id is not None and (type(source_id) is not int or source_id <= 0):
        abort(400, "source_document_id musi być dodatnią liczbą całkowitą")
    return data


def _serialize(entry) -> dict:
    return {
        column.name: (value.isoformat() if isinstance(value, datetime.datetime) else value)
        for column in NerGazetteerEntry.__table__.columns
        for value in [getattr(entry, column.name)]
    }


def _duplicate(session, kind: str, name_pl: str, exclude_id: int | None = None):
    query = select(NerGazetteerEntry.id).where(
        NerGazetteerEntry.kind == kind, func.lower(NerGazetteerEntry.name_pl) == name_pl.lower(),
    )
    if exclude_id is not None:
        query = query.where(NerGazetteerEntry.id != exclude_id)
    return session.scalars(query).first()


@bp.get("/ner_gazetteer")
def list_entries():
    query = select(NerGazetteerEntry).order_by(NerGazetteerEntry.id)
    if "kind" in request.args:
        if request.args["kind"] not in KINDS:
            abort(400, f"kind musi być jednym z: {', '.join(KINDS)}")
        query = query.where(NerGazetteerEntry.kind == request.args["kind"])
    entries = get_scoped_session().scalars(query).all()
    return jsonify({"status": "success", "entries": [_serialize(entry) for entry in entries]})


@bp.post("/ner_gazetteer")
def add_entry():
    _require_service()
    data = _body()
    try:
        values = validate_entry(
            kind=data.get("kind"), name_pl=data.get("name_pl"),
            patterns=data.get("patterns"), geocode_alias=data.get("geocode_alias"),
        )
    except GazetteerValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    session = get_scoped_session()
    if _duplicate(session, values["kind"], values["name_pl"]) is not None:
        return jsonify({"status": "error", "message": "Wpis o tej nazwie już istnieje"}), 409
    entry = NerGazetteerEntry(
        **values, note=data.get("note"), source_document_id=data.get("source_document_id"),
        created_by=str(data.get("created_by") or getattr(g.auth, "key_name", None)
                       or getattr(g.auth, "user_id", None) or "service")[:100],
    )
    try:
        session.add(entry)
        session.commit()
    except IntegrityError:
        session.rollback()
        return jsonify({"status": "error", "message": "Wpis o tej nazwie już istnieje"}), 409
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    return jsonify({"status": "success", "entry": _serialize(entry)}), 201


@bp.patch("/ner_gazetteer/<int:entry_id>")
def patch_entry(entry_id: int):
    _require_service()
    data = _body()
    session = get_scoped_session()
    entry = session.get(NerGazetteerEntry, entry_id)
    if entry is None:
        abort(404, "Nie znaleziono wpisu")
    merged = {
        "kind": entry.kind,
        "name_pl": data.get("name_pl", entry.name_pl),
        "patterns": data.get("patterns", entry.patterns),
        "geocode_alias": data.get("geocode_alias", entry.geocode_alias),
    }
    try:
        values = validate_entry(**merged)
    except GazetteerValidationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if _duplicate(session, entry.kind, values["name_pl"], exclude_id=entry.id) is not None:
        return jsonify({"status": "error", "message": "Wpis o tej nazwie już istnieje"}), 409
    try:
        entry.name_pl = values["name_pl"]
        entry.patterns = values["patterns"]
        entry.geocode_alias = values["geocode_alias"]
        for key in ("note", "source_document_id"):
            if key in data:
                setattr(entry, key, data[key])
        session.commit()
    except IntegrityError:
        session.rollback()
        return jsonify({"status": "error", "message": "Wpis o tej nazwie już istnieje"}), 409
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    return jsonify({"status": "success", "entry": _serialize(entry)})


@bp.delete("/ner_gazetteer/<int:entry_id>")
def delete_entry(entry_id: int):
    _require_service()
    session = get_scoped_session()
    entry = session.get(NerGazetteerEntry, entry_id)
    if entry is None:
        abort(404, "Nie znaleziono wpisu")
    try:
        session.delete(entry)
        session.commit()
    except Exception:
        session.rollback()
        raise
    invalidate_cache()
    return jsonify({"status": "success", "deleted_entry_id": entry_id})
