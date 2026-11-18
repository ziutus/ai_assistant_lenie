"""PATCH /document/<id>/tags - add and remove single tags without replacing the whole tag list.

``Document.tags`` is one comma-separated string. The only other way to change it over REST is ``/website_save``,
which replaces the whole string: removing one stale tag (doc #11263: ``miejsce-manili`` among 85 tags) meant
resending the other 84 and risked losing them. This endpoint changes only the tags it is told about.
"""

import logging

from flask import Blueprint, abort, g, jsonify, request

from library.db.engine import get_scoped_session
from library.db.models import Document

logger = logging.getLogger(__name__)

bp = Blueprint("document_tags", __name__)

MAX_TAG_LENGTH = 100
MAX_TAGS_PER_REQUEST = 50


# A fixed text per error code: the response never carries text built from an exception (CodeQL py/stack-trace-exposure).
_MESSAGES = {
    "tag_not_text": "Tag musi być tekstem",
    "tag_empty": "Tag nie może być pusty",
    "tag_comma": "Tag nie może zawierać przecinka",
    "tag_too_long": f"Tag może mieć najwyżej {MAX_TAG_LENGTH} znaków",
    "list_not_list": "add i remove muszą być listami tagów",
    "list_too_long": f"add i remove mogą mieć najwyżej {MAX_TAGS_PER_REQUEST} tagów",
}


class _BadRequest(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require_writer() -> None:
    if getattr(getattr(g, "auth", None), "kind", None) not in ("service", "user"):
        abort(403, "Zmiana tagów wymaga klucza service lub user")


def normalize_tag(value) -> str:
    """One tag as stored: trimmed, lower case, inner whitespace collapsed; never empty, never a comma."""
    if not isinstance(value, str):
        raise _BadRequest("tag_not_text")
    tag = " ".join(value.split()).lower()
    if not tag:
        raise _BadRequest("tag_empty")
    if "," in tag:
        raise _BadRequest("tag_comma")
    if len(tag) > MAX_TAG_LENGTH:
        raise _BadRequest("tag_too_long")
    return tag


def _tag_list(data: dict, key: str) -> list[str]:
    raw = data.get(key, [])
    if not isinstance(raw, list):
        raise _BadRequest("list_not_list")
    if len(raw) > MAX_TAGS_PER_REQUEST:
        raise _BadRequest("list_too_long")
    return list(dict.fromkeys(normalize_tag(item) for item in raw))


def apply_tag_changes(current: str | None, add: list[str], remove: list[str]) -> dict:
    """Pure core: the new tag list and what really changed (matching ignores case)."""
    tags = [t.strip() for t in (current or "").split(",") if t.strip()]
    remove_keys = {t.casefold() for t in remove}
    removed = [t for t in tags if t.casefold() in remove_keys]
    kept = [t for t in tags if t.casefold() not in remove_keys]
    present = {t.casefold() for t in kept}
    added = [t for t in add if t.casefold() not in present]
    removed_keys = {t.casefold() for t in removed}
    return {
        "tags": [*kept, *added], "added": added, "removed": removed,
        "not_found": [t for t in remove if t.casefold() not in removed_keys],
        "already_present": [t for t in add if t.casefold() in present],
    }


@bp.patch("/document/<int:doc_id>/tags")
def patch_document_tags(doc_id: int):
    """Body: ``{"add": ["tag", ...], "remove": ["tag", ...]}`` (either list may be empty, not both).

    Removing runs first; a tag may not be in both lists. A tag to remove that the document does not have is reported
    in ``not_found``, not an error. Answers the document's full tag list after the change.
    """
    _require_writer()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="Wymagany obiekt JSON"), 400
    try:
        add, remove = _tag_list(data, "add"), _tag_list(data, "remove")
    except _BadRequest as exc:
        return jsonify(status="error", message=_MESSAGES.get(exc.code, "Nieprawidłowe tagi")), 400
    if not add and not remove:
        return jsonify(status="error", message="Podaj co najmniej jeden tag w add lub remove"), 400
    overlap = sorted(set(add) & set(remove))
    if overlap:
        return jsonify(status="error", message="Tag nie może być jednocześnie w add i remove", tags=overlap), 400

    session = get_scoped_session()
    doc = session.get(Document, doc_id)
    if doc is None:
        return jsonify(status="error", message="Nie znaleziono dokumentu"), 404
    result = apply_tag_changes(doc.tags, add, remove)
    if result["added"] or result["removed"]:
        doc.tags = ",".join(result["tags"])
        try:
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("tag change failed for document %s", doc_id)
            return jsonify(status="error", message="Nie udało się zapisać tagów"), 500
        logger.info("document %s tags changed by %s: +%s -%s", doc_id,
                    getattr(g.auth, "key_name", None) or getattr(g.auth, "user_id", None) or "?",
                    result["added"], result["removed"])
    return jsonify(status="success", document_id=doc_id, **result), 200
