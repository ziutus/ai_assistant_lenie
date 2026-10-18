"""REST for the per-channel NER glossary (names expected on one channel, library/ner_channel_glossary.py)."""

import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from library.db.engine import get_scoped_session
from library.db.models import Document, NerChannelGlossaryEntry, NerGlossaryApplication

bp = Blueprint("ner_channel_glossary", __name__)

MAX_TEXT_LENGTH = 200
MAX_ALIASES = 20


def _serialize(entry) -> dict:
    return {
        column.name: (value.isoformat() if isinstance(value, datetime.datetime) else value)
        for column in NerChannelGlossaryEntry.__table__.columns
        for value in [getattr(entry, column.name)]
    }


def _clean_text(value, field: str, *, required: bool = True) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            abort(400, f"{field} jest wymagane")
        return None
    if not isinstance(value, str) or len(value.strip()) > MAX_TEXT_LENGTH:
        abort(400, f"{field} musi być tekstem do {MAX_TEXT_LENGTH} znaków")
    return value.strip()


def _clean_aliases(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ALIASES:
        abort(400, f"aliases musi być listą do {MAX_ALIASES} fraz")
    cleaned = []
    for alias in value:
        text = _clean_text(alias, "alias")
        if len(text) < 3:
            abort(400, "Alias musi mieć co najmniej 3 znaki")
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Wymagany obiekt JSON")
    if "fuzzy" in data and not isinstance(data["fuzzy"], bool):
        abort(400, "fuzzy musi być wartością logiczną")
    return data


def _author_from(data: dict, session) -> str:
    author = _clean_text(data.get("author"), "author", required=False)
    if author:
        return author
    document_id = data.get("document_id")
    if type(document_id) is int and document_id > 0:
        document = session.get(Document, document_id)
        if document is not None and (document.byline or "").strip():
            return document.byline.strip()
    abort(400, "Podaj author (kanał) albo document_id dokumentu z autorem")


@bp.get("/ner_channel_glossary")
def list_entries():
    query = select(NerChannelGlossaryEntry).order_by(NerChannelGlossaryEntry.author, NerChannelGlossaryEntry.id)
    author = request.args.get("author")
    if author:
        query = query.where(func.lower(NerChannelGlossaryEntry.author) == author.strip().lower())
    session = get_scoped_session()
    entries = session.scalars(query).all()
    authors = session.scalars(
        select(NerChannelGlossaryEntry.author).distinct().order_by(NerChannelGlossaryEntry.author)
    ).all()
    return jsonify({"status": "success", "entries": [_serialize(e) for e in entries], "authors": authors})


@bp.post("/ner_channel_glossary")
def add_entry():
    data = _body()
    session = get_scoped_session()
    author = _author_from(data, session)
    canonical = _clean_text(data.get("canonical_name"), "canonical_name")
    entry = NerChannelGlossaryEntry(
        author=author, canonical_name=canonical, aliases=_clean_aliases(data.get("aliases")),
        fuzzy=data.get("fuzzy", True), note=_clean_text(data.get("note"), "note", required=False),
        created_by=str(getattr(g.auth, "key_name", None) or getattr(g.auth, "user_id", None) or "api")[:100]
        if getattr(g, "auth", None) is not None else None,
    )
    try:
        session.add(entry)
        session.commit()
    except IntegrityError:
        session.rollback()
        return jsonify({"status": "error", "message": "Ten kanał ma już wpis o tej nazwie"}), 409
    except Exception:
        session.rollback()
        raise
    return jsonify({"status": "success", "entry": _serialize(entry)}), 201


@bp.patch("/ner_channel_glossary/<int:entry_id>")
def patch_entry(entry_id: int):
    data = _body()
    session = get_scoped_session()
    entry = session.get(NerChannelGlossaryEntry, entry_id)
    if entry is None:
        abort(404, "Nie znaleziono wpisu")
    try:
        if "canonical_name" in data:
            entry.canonical_name = _clean_text(data["canonical_name"], "canonical_name")
        if "aliases" in data:
            entry.aliases = _clean_aliases(data["aliases"])
        if "fuzzy" in data:
            entry.fuzzy = data["fuzzy"]
        if "note" in data:
            entry.note = _clean_text(data["note"], "note", required=False)
        session.commit()
    except IntegrityError:
        session.rollback()
        return jsonify({"status": "error", "message": "Ten kanał ma już wpis o tej nazwie"}), 409
    except Exception:
        session.rollback()
        raise
    return jsonify({"status": "success", "entry": _serialize(entry)})


@bp.delete("/ner_channel_glossary/<int:entry_id>")
def delete_entry(entry_id: int):
    session = get_scoped_session()
    entry = session.get(NerChannelGlossaryEntry, entry_id)
    if entry is None:
        abort(404, "Nie znaleziono wpisu")
    try:
        session.delete(entry)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return jsonify({"status": "success", "deleted_entry_id": entry_id})


@bp.get("/ner_channel_glossary/applications")
def list_applications():
    """The document channel's glossary and the replacements that fired for it (`?document_id=`)."""
    try:
        document_id = int(request.args.get("document_id", ""))
    except ValueError:
        abort(400, "document_id jest wymagane")
    session = get_scoped_session()
    document = session.get(Document, document_id)
    author = (getattr(document, "byline", None) or "").strip() or None
    entries = session.scalars(
        select(NerChannelGlossaryEntry).where(func.lower(NerChannelGlossaryEntry.author) == author.lower())
        .order_by(NerChannelGlossaryEntry.id)
    ).all() if author else []
    rows = session.execute(
        select(NerGlossaryApplication, NerChannelGlossaryEntry.canonical_name)
        .outerjoin(NerChannelGlossaryEntry, NerChannelGlossaryEntry.id == NerGlossaryApplication.glossary_id)
        .where(NerGlossaryApplication.document_id == document_id)
        .order_by(NerGlossaryApplication.occurrences.desc(), NerGlossaryApplication.id)
    ).all()
    return jsonify({"status": "success", "author": author, "entries": [
        {"id": e.id, "canonical_name": e.canonical_name, "aliases": e.aliases, "fuzzy": e.fuzzy} for e in entries
    ], "applications": [
        {"id": app.id, "glossary_id": app.glossary_id, "canonical_name": name,
         "original_text": app.original_text, "replacement_text": app.replacement_text,
         "occurrences": app.occurrences, "applied_at": app.applied_at.isoformat()}
        for app, name in rows
    ]})
