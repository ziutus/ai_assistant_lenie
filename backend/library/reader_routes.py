"""Flask blueprint: reader users, per-user reading progress and fragment notes (Etap 7).

Endpoints (all require x-api-key via the global before_request; the ones
marked [user] additionally require an x-user-id header of an existing user):
  GET    /users                                — list users
  POST   /users                                — create user {username, display_name?}
  GET    /document/<doc_id>/reading_progress   — [user] progress for this document
  PUT    /document/<doc_id>/reading_progress   — [user] upsert current chapter / read chapters
  GET    /document/<doc_id>/notes              — [user] notes (optional ?chapter=N filter)
  POST   /document/<doc_id>/notes              — [user] add a note anchored by quote
  PATCH  /note/<note_id>                       — [user] edit own note (note_text / stance)
  DELETE /note/<note_id>                       — [user] delete own note

Notes are anchored by exact quote + context (W3C TextQuoteSelector style) at
the document level, so they survive analysis-run deletion; re-anchoring in the
chapter text is the frontend's job (exact match, then whitespace-normalized).
"""

import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import select

from library.db.engine import get_scoped_session
from library.db.models import User, UserDocumentNote, UserReadingProgress, WebDocument

logger = logging.getLogger(__name__)

bp = Blueprint("reader", __name__)

ALLOWED_STANCES = {"agree", "disagree", "neutral"}


def _require_user(session) -> User:
    """Resolve the x-user-id header to a User row or abort."""
    raw = request.headers.get("x-user-id")
    if not raw:
        abort(400, "x-user-id header is missing")
    try:
        user_id = int(raw)
    except ValueError:
        abort(400, "x-user-id header must be an integer")
    user = session.get(User, user_id)
    if user is None:
        abort(404, f"User {user_id} not found")
    return user


def _get_document_or_404(session, doc_id: int) -> WebDocument:
    doc = session.get(WebDocument, doc_id)
    if doc is None:
        abort(404, f"Document {doc_id} not found")
    return doc


def _note_to_dict(note: UserDocumentNote) -> dict:
    return {
        "id": note.id,
        "user_id": note.user_id,
        "document_id": note.document_id,
        "chapter_position": note.chapter_position,
        "anchor_quote": note.anchor_quote,
        "anchor_prefix": note.anchor_prefix,
        "anchor_suffix": note.anchor_suffix,
        "run_id": note.run_id,
        "chunk_id": note.chunk_id,
        "note_text": note.note_text,
        "stance": note.stance,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@bp.route("/users", methods=["GET"])
def list_users():
    session = get_scoped_session()
    users = session.execute(select(User).order_by(User.id)).scalars().all()
    return jsonify({
        "status": "success",
        "users": [
            {"id": u.id, "username": u.username, "display_name": u.display_name}
            for u in users
        ],
    })


@bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"status": "error", "message": "username is required"}), 400
    if len(username) > 50:
        return jsonify({"status": "error", "message": "username too long (max 50)"}), 400

    session = get_scoped_session()
    existing = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing is not None:
        return jsonify({"status": "error", "message": f"username '{username}' already exists"}), 409

    user = User(username=username, display_name=(data.get("display_name") or "").strip() or None)
    session.add(user)
    session.commit()
    return jsonify({
        "status": "success",
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name},
    }), 201


# ---------------------------------------------------------------------------
# Reading progress
# ---------------------------------------------------------------------------


@bp.route("/document/<int:doc_id>/reading_progress", methods=["GET"])
def get_reading_progress(doc_id: int):
    session = get_scoped_session()
    user = _require_user(session)
    _get_document_or_404(session, doc_id)

    progress = session.execute(
        select(UserReadingProgress).where(
            UserReadingProgress.user_id == user.id,
            UserReadingProgress.document_id == doc_id,
        )
    ).scalar_one_or_none()

    if progress is None:
        return jsonify({
            "status": "success",
            "doc_id": doc_id,
            "user_id": user.id,
            "current_chapter": None,
            "current_chapter_title": None,
            "read_chapters": [],
        })
    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "user_id": user.id,
        "current_chapter": progress.current_chapter,
        "current_chapter_title": progress.current_chapter_title,
        "read_chapters": sorted(progress.read_chapters or []),
        "updated_at": progress.updated_at.isoformat() if progress.updated_at else None,
    })


@bp.route("/document/<int:doc_id>/reading_progress", methods=["PUT"])
def put_reading_progress(doc_id: int):
    """Upsert reading progress.

    Body: current_chapter (int >= 1, required), current_chapter_title (optional
    snapshot from the client — avoids re-slicing the whole book server-side),
    mark_read / unmark_read (optional lists of chapter positions).
    """
    data = request.get_json(silent=True) or {}
    current_chapter = data.get("current_chapter")
    if not isinstance(current_chapter, int) or current_chapter < 1:
        return jsonify({"status": "error", "message": "current_chapter must be a positive integer"}), 400
    for key in ("mark_read", "unmark_read"):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(p, int) and p >= 1 for p in value):
            return jsonify({"status": "error", "message": f"{key} must be a list of positive integers"}), 400

    session = get_scoped_session()
    user = _require_user(session)
    _get_document_or_404(session, doc_id)

    progress = session.execute(
        select(UserReadingProgress).where(
            UserReadingProgress.user_id == user.id,
            UserReadingProgress.document_id == doc_id,
        )
    ).scalar_one_or_none()
    if progress is None:
        progress = UserReadingProgress(
            user_id=user.id, document_id=doc_id,
            current_chapter=current_chapter, read_chapters=[],
        )
        session.add(progress)

    progress.current_chapter = current_chapter
    title = data.get("current_chapter_title")
    if title is not None:
        progress.current_chapter_title = str(title)[:500] or None

    read = set(progress.read_chapters or [])
    read.update(data.get("mark_read", []))
    read.difference_update(data.get("unmark_read", []))
    progress.read_chapters = sorted(read)

    progress.updated_at = datetime.now()
    session.commit()

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "user_id": user.id,
        "current_chapter": progress.current_chapter,
        "current_chapter_title": progress.current_chapter_title,
        "read_chapters": progress.read_chapters,
    })


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@bp.route("/document/<int:doc_id>/notes", methods=["GET"])
def list_notes(doc_id: int):
    session = get_scoped_session()
    user = _require_user(session)
    _get_document_or_404(session, doc_id)

    query = select(UserDocumentNote).where(
        UserDocumentNote.user_id == user.id,
        UserDocumentNote.document_id == doc_id,
    )
    chapter = request.args.get("chapter", type=int)
    if chapter is not None:
        query = query.where(UserDocumentNote.chapter_position == chapter)
    notes = session.execute(
        query.order_by(UserDocumentNote.chapter_position, UserDocumentNote.id)
    ).scalars().all()

    return jsonify({
        "status": "success",
        "doc_id": doc_id,
        "user_id": user.id,
        "notes": [_note_to_dict(n) for n in notes],
    })


@bp.route("/document/<int:doc_id>/notes", methods=["POST"])
def create_note(doc_id: int):
    data = request.get_json(silent=True) or {}
    anchor_quote = (data.get("anchor_quote") or "").strip()
    note_text = (data.get("note_text") or "").strip()
    if not anchor_quote:
        return jsonify({"status": "error", "message": "anchor_quote is required"}), 400
    if not note_text:
        return jsonify({"status": "error", "message": "note_text is required"}), 400
    stance = data.get("stance")
    if stance is not None and stance not in ALLOWED_STANCES:
        return jsonify({
            "status": "error",
            "message": f"stance must be one of {sorted(ALLOWED_STANCES)}",
        }), 400

    session = get_scoped_session()
    user = _require_user(session)
    _get_document_or_404(session, doc_id)

    note = UserDocumentNote(
        user_id=user.id,
        document_id=doc_id,
        chapter_position=data.get("chapter_position"),
        anchor_quote=anchor_quote,
        # prefix keeps its END (nearest the quote), suffix keeps its beginning
        anchor_prefix=str(data.get("anchor_prefix") or "")[-100:] or None,
        anchor_suffix=str(data.get("anchor_suffix") or "")[:100] or None,
        run_id=data.get("run_id"),
        chunk_id=data.get("chunk_id"),
        note_text=note_text,
        stance=stance,
    )
    session.add(note)
    session.commit()
    return jsonify({"status": "success", "note": _note_to_dict(note)}), 201


@bp.route("/note/<int:note_id>", methods=["PATCH"])
def update_note(note_id: int):
    data = request.get_json(silent=True) or {}
    session = get_scoped_session()
    user = _require_user(session)

    note = session.get(UserDocumentNote, note_id)
    if note is None:
        abort(404, f"Note {note_id} not found")
    if note.user_id != user.id:
        abort(403, "Note belongs to another user")

    if "note_text" in data:
        note_text = (data.get("note_text") or "").strip()
        if not note_text:
            return jsonify({"status": "error", "message": "note_text cannot be empty"}), 400
        note.note_text = note_text
    if "stance" in data:
        stance = data.get("stance")
        if stance is not None and stance not in ALLOWED_STANCES:
            return jsonify({
                "status": "error",
                "message": f"stance must be one of {sorted(ALLOWED_STANCES)}",
            }), 400
        note.stance = stance

    note.updated_at = datetime.now()
    session.commit()
    return jsonify({"status": "success", "note": _note_to_dict(note)})


@bp.route("/note/<int:note_id>", methods=["DELETE"])
def delete_note(note_id: int):
    session = get_scoped_session()
    user = _require_user(session)

    note = session.get(UserDocumentNote, note_id)
    if note is None:
        abort(404, f"Note {note_id} not found")
    if note.user_id != user.id:
        abort(403, "Note belongs to another user")

    session.delete(note)
    session.commit()
    return jsonify({"status": "success", "deleted_note_id": note_id})
