"""REST API for public persons (course authors, channel hosts...) kept in the person registry.

A public person is an ordinary ``persons`` row with ``kind='public'`` and a ``role``; it is not a
contact (the private contact book is untouched). ``source_persons`` ties the person to the knowledge
sources they stand behind, so a source shows its people and a person shows their sources.
"""

from flask import Blueprint, abort, g, jsonify, request

from library import knowledge_sources
from library.db.engine import get_scoped_session
from library.db.models import DiscoverySource, Person

bp = Blueprint("public_persons", __name__)

MAX_NAME_LENGTH = 500


def _writer():
    if getattr(g, "auth", None) is None or g.auth.kind not in {"user", "service"}:
        abort(403, "user or service API key required")


def _person_dict(session, person: Person) -> dict:
    return {
        "id": person.id, "uuid": person.uuid, "canonical_name": person.canonical_name,
        "wikidata_qid": person.wikidata_qid, "description": person.description,
        "long_description": person.long_description, "links": person.links or [],
        "aliases": [alias.alias for alias in person.aliases],
        **knowledge_sources.person_fields(person),
        "sources": knowledge_sources.sources_for_persons(session, [person.id]).get(person.id, []),
    }


@bp.post("/persons")
def create_person():
    """Add a person to the registry by hand (a public figure the NER has never met).

    Body: ``canonical_name`` (required), ``kind`` (``public``), ``role``, ``description``, ``long_description``,
    ``links`` (``[{url, label}]``), ``aliases`` and ``obsidian_note_path``. A name or alias that already
    belongs to somebody answers 409 with ``existing_person_id`` - edit that person instead.
    """
    _writer()
    from library.person_registry import add_person_alias, normalize_person_links

    body = request.get_json(silent=True) or {}
    name = body.get("canonical_name")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_LENGTH:
        abort(400, "canonical_name is required")
    session = get_scoped_session()
    existing = knowledge_sources.find_person(session, name)
    if existing is not None:
        return jsonify({"status": "error", "message": f"„{existing.canonical_name}” już jest w rejestrze.",
                        "existing_person_id": existing.id}), 409
    try:
        fields = knowledge_sources.validate_person_fields(body)
        links = normalize_person_links(body["links"]) if "links" in body else []
    except ValueError as exc:
        abort(400, str(exc))
    aliases = body.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
        abort(400, "aliases must be a list of strings")
    for text_field in ("description", "long_description"):
        if body.get(text_field) is not None and not isinstance(body[text_field], str):
            abort(400, f"{text_field} must be a string")
    person = Person(
        canonical_name=name.strip(), description=(body.get("description") or "").strip() or None,
        long_description=(body.get("long_description") or "").strip() or None, links=links, **fields,
    )
    session.add(person)
    session.flush()
    for alias in aliases:
        if alias.strip() and knowledge_sources.normalize_name(alias) != knowledge_sources.normalize_name(name):
            add_person_alias(session, person, alias.strip())
    session.commit()
    return jsonify({"status": "success", "person": _person_dict(session, person)}), 201


def _resolve_person(session, body: dict) -> Person:
    if body.get("person_id") is not None:
        person = session.get(Person, body["person_id"]) if isinstance(body["person_id"], int) else None
    else:
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            abort(400, "person_id or name is required")
        person = knowledge_sources.find_person(session, name)
    if person is None:
        abort(404, "person not found in the registry - add them on the Osoby page first")
    return person


@bp.post("/sources/<int:source_id>/persons")
def add_source_person(source_id):
    """Say who stands behind a source. Body: ``{person_id | name, role?}`` (role: author/host/instructor/guest/other)."""
    _writer()
    body = request.get_json(silent=True) or {}
    session = get_scoped_session()
    source = session.get(DiscoverySource, source_id)
    if source is None:
        abort(404, "source not found")
    person = _resolve_person(session, body)
    try:
        link, created = knowledge_sources.link_person(session, source, person, body.get("role") or "author")
    except ValueError as exc:
        abort(400, str(exc))
    session.commit()
    persons = knowledge_sources.persons_for_sources(session).get(source_id, [])
    return jsonify({"persons": persons, "linked": created}), 201 if created else 200


@bp.delete("/sources/<int:source_id>/persons/<int:person_id>")
def remove_source_person(source_id, person_id):
    """Detach a person from a source (both stay in their registries)."""
    _writer()
    session = get_scoped_session()
    if not knowledge_sources.unlink_person(session, source_id, person_id):
        abort(404, "the person is not linked to this source")
    session.commit()
    return jsonify({"persons": knowledge_sources.persons_for_sources(session).get(source_id, [])})
