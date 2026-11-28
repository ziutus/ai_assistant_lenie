"""Global relations and owned projections. The caller owns the transaction."""

import datetime
import hashlib
import json

from sqlalchemy import or_, select

from library.country_gazetteer import slug_to_name
from library.db.models import (
    Document, DocumentOrganization, DocumentPerson, EntityRelation, EntityRelationEvidence,
    Organization, OrganizationCountry, Person, PersonTerritory,
)
from library.entity_relation_vocabulary import SYMMETRIC, VOCABULARY, allowed

PROJECTIONS = {"siedziba": "based_in", "funkcja_publiczna": "holds_office_in", "obywatel": "citizen_of"}


class RelationError(ValueError):
    pass


def endpoint(session, value):
    if not isinstance(value, dict):
        raise RelationError("Invalid endpoint")
    kind = value.get("type")
    if kind == "country":
        slug = value.get("slug")
        if not isinstance(slug, str) or not slug_to_name(slug):
            raise RelationError("Unknown country")
        return {"type": kind, "slug": slug, "name": slug_to_name(slug)}
    identifier = value.get("id")
    if kind not in ("person", "organization") or type(identifier) is not int or identifier <= 0:
        raise RelationError("Invalid endpoint")
    row = session.get(Person if kind == "person" else Organization, identifier)
    if row is None:
        raise RelationError("Unknown endpoint")
    return {"type": kind, "id": identifier, "name": row.canonical_name}


def ends(row):
    subject = ({"type": "person", "id": row.subject_person_id} if row.subject_person_id is not None else
               {"type": "organization", "id": row.subject_organization_id})
    obj = ({"type": "person", "id": row.object_person_id} if row.object_person_id is not None else
           {"type": "organization", "id": row.object_organization_id} if row.object_organization_id is not None else
           {"type": "country", "slug": row.object_country_slug})
    return subject, obj


def key(end):
    return end["type"], end.get("id", end.get("slug"))


def _columns(subject, obj):
    values = dict.fromkeys(("subject_person_id", "subject_organization_id", "object_person_id",
                           "object_organization_id", "object_country_slug"))
    for prefix, end in (("subject", subject), ("object", obj)):
        values[f"{prefix}_{end['type']}_{'slug' if end['type'] == 'country' else 'id'}"] = end.get("id", end.get("slug"))
    return values


def _period(start, end):
    try:
        start, end = (datetime.date.fromisoformat(v) if isinstance(v, str) else v for v in (start, end))
    except ValueError as exc:
        raise RelationError("Invalid date") from exc
    if any(v is not None and type(v) is not datetime.date for v in (start, end)):
        raise RelationError("Invalid date")
    if start and end and start > end:
        raise RelationError("Invalid period")
    return start, end


def compatible(row, start, end):
    return not ((row.valid_to and start and row.valid_to < start) or
                (end and row.valid_from and end < row.valid_from))


def _title(value):
    if value is not None and (not isinstance(value, str) or len(value) > 200):
        raise RelationError("Invalid title")
    return value.strip() or None if value is not None else None


def add_evidence(session, row, evidence):
    if not evidence:
        return False
    values = {k: evidence.get(k) for k in ("document_id", "quote", "claim", "source_url", "model", "prompt_version")}
    from library.relation_extraction import CLAIMS
    if values["claim"] is not None and values["claim"] not in CLAIMS:
        raise RelationError("Invalid claim")
    # The passage is the identity, regardless of which model rediscovered it.
    digest = hashlib.sha256(json.dumps({k: values[k] for k in ("document_id", "quote", "claim", "source_url")},
                                      sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    if any(e.content_hash == digest for e in row.evidence):
        return False
    row.evidence.append(EntityRelationEvidence(content_hash=digest, **values))
    session.flush()
    return True


def upsert_relation(session, subject, relation, object, *, title=None, valid_from=None, valid_to=None,
                    detection_method="llm", evidence=None):
    subject, obj = endpoint(session, subject), endpoint(session, object)
    if not isinstance(relation, str) or not allowed(relation, subject["type"], obj["type"]):
        raise RelationError("Invalid relation")
    if key(subject) == key(obj):
        raise RelationError("Self relation")
    if detection_method not in ("llm", "wikidata", "manual"):
        raise RelationError("Invalid method")
    title = _title(title)
    start, end = _period(valid_from, valid_to)
    if relation in SYMMETRIC and (subject["type"] != obj["type"] and subject["type"] == "organization" or
                                  subject["type"] == obj["type"] and key(subject) > key(obj)):
        subject, obj = obj, subject
    values = _columns(subject, obj)
    rows = session.scalars(select(EntityRelation).filter_by(relation=relation, **values).order_by(EntityRelation.id)).all()
    row = next((r for r in rows if compatible(r, start, end)), None)
    created = row is None
    if created:
        row = EntityRelation(**values, relation=relation, title=title, valid_from=start, valid_to=end,
                             status="proposed", detection_method=detection_method)
        model, filters = _projection(session, row)
        known = session.scalars(select(model).filter_by(**filters)).first() if model is not None else None
        if known is not None and compatible(row, getattr(known, "valid_from", None), getattr(known, "valid_to", None)):
            # The country tables already state this tie: a rediscovery adds evidence, it is not a new proposal.
            row.status = "confirmed"
        session.add(row)
        session.flush()
    elif row.status == "proposed":
        new_start, new_end = row.valid_from or start, row.valid_to or end
        _period(new_start, new_end)
        row.title = row.title or title
        row.valid_from, row.valid_to = new_start, new_end
    added = add_evidence(session, row, evidence)
    return row, created, added


def _projection(session, row):
    if not row.object_country_slug:
        return None, None
    if row.subject_person_id:
        model = PersonTerritory
        filters = dict(person_id=row.subject_person_id, kind="country", slug=row.object_country_slug,
                       relation=PROJECTIONS[row.relation])
    else:
        model = OrganizationCountry
        filters = dict(organization_id=row.subject_organization_id, country_slug=row.object_country_slug,
                       relation="based_in")
    return model, filters


def project(session, row):
    model, filters = _projection(session, row)
    if model is None:
        return
    existing = session.scalars(select(model).filter_by(**filters)).first()
    if existing is None:
        existing = model(**filters)
        if model is PersonTerritory:
            existing.valid_from, existing.valid_to = row.valid_from, row.valid_to
        session.add(existing)
        session.flush()
        row.projected_table, row.projected_row_id = model.__tablename__, existing.id
    elif row.projected_table == model.__tablename__ and row.projected_row_id == existing.id and model is PersonTerritory:
        existing.valid_from, existing.valid_to = row.valid_from, row.valid_to


def unproject(session, row):
    if not row.projected_table:
        return
    model, filters = _projection(session, row)
    owned_id = row.projected_row_id
    row.projected_table, row.projected_row_id = None, None
    if model is None:
        return
    # Transfer ownership when another confirmed term still relies on this truth row.
    candidates = session.scalars(select(EntityRelation).where(
        EntityRelation.id != row.id, EntityRelation.status == "confirmed",
        EntityRelation.object_country_slug == row.object_country_slug)).all()
    successor = next((r for r in candidates if _projection(session, r) == (model, filters)), None)
    if successor:
        successor.projected_table, successor.projected_row_id = model.__tablename__, owned_id
        project(session, successor)
        return
    projected = session.get(model, owned_id)
    if projected is not None and all(getattr(projected, k) == v for k, v in filters.items()):
        session.delete(projected)
        session.flush()


def decide_relation(session, row, status, user_id=None):
    if status not in ("confirmed", "rejected"):
        raise RelationError("Invalid status")
    row.status = status
    row.decided_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    row.decided_by_user_id = user_id
    if status == "confirmed":
        project(session, row)
    else:
        unproject(session, row)
    session.flush()
    return row


def manual_create(session, subject, relation, object, *, user_id=None, **fields):
    row, created, _ = upsert_relation(session, subject, relation, object, detection_method="manual", **fields)
    edit_relation(session, row, **fields)
    decide_relation(session, row, "confirmed", user_id)
    return row, created


def edit_relation(session, row, **fields):
    if set(fields) - {"title", "valid_from", "valid_to"}:
        raise RelationError("Invalid fields")
    start, end = _period(fields.get("valid_from", row.valid_from), fields.get("valid_to", row.valid_to))
    if "title" in fields:
        row.title = _title(fields["title"])
    row.valid_from, row.valid_to = start, end
    if row.status == "confirmed":
        project(session, row)
    session.flush()


def delete_relation(session, row):
    unproject(session, row)
    session.delete(row)
    session.flush()


def touching(kind, identifier):
    return or_(getattr(EntityRelation, f"subject_{kind}_id") == identifier,
               getattr(EntityRelation, f"object_{kind}_id") == identifier)


def has_relations(session, kind, identifier):
    return session.scalar(select(EntityRelation.id).where(touching(kind, identifier),
                                                        EntityRelation.status != "rejected").limit(1)) is not None


def relation_dict(session, row, perspective=None):
    subject, obj = (endpoint(session, e) for e in ends(row))
    result = {"id": row.id, "subject": subject, "object": obj, "relation": row.relation, "title": row.title,
              "valid_from": row.valid_from.isoformat() if row.valid_from else None,
              "valid_to": row.valid_to.isoformat() if row.valid_to else None,
              "status": row.status, "detection_method": row.detection_method,
              "source": "entity_relations", "editable": True, "evidence": []}
    for evidence in row.evidence:
        doc = session.get(Document, evidence.document_id) if evidence.document_id else None
        result["evidence"].append({"id": evidence.id, "document_id": evidence.document_id,
                                   "document_title": doc.title if doc else None, "quote": evidence.quote,
                                   "claim": evidence.claim, "source_url": evidence.source_url, "model": evidence.model,
                                   "prompt_version": evidence.prompt_version, "content_hash": evidence.content_hash})
    reverse = perspective is not None and key(perspective) == key(obj)
    result.update(direction="incoming" if reverse else "outgoing",
                  label=VOCABULARY[row.relation][int(reverse)], other=subject if reverse else obj)
    return result


def relations_for(session, kind, identifier, include_rejected=False):
    perspective = endpoint(session, {"type": kind, "id": identifier})
    rows = session.scalars(select(EntityRelation).where(touching(kind, identifier)).order_by(EntityRelation.id)).all()
    result = [relation_dict(session, r, perspective) for r in rows if include_rejected or r.status != "rejected"]
    # A rejected proposal must not hide an independently established truth row.
    counterparts = {(r.object_country_slug, PROJECTIONS.get(r.relation)) for r in rows
                    if r.status != "rejected" and key(ends(r)[0]) == key(perspective)}
    if kind == "person":
        from library.person_territories import RELATIONS
        truth = session.scalars(select(PersonTerritory).filter_by(person_id=identifier, kind="country")).all()
    else:
        from library.organization_location import COUNTRY_RELATIONS as RELATIONS
        truth = session.scalars(select(OrganizationCountry).filter_by(organization_id=identifier)).all()
    for row in truth:
        slug = row.slug if kind == "person" else row.country_slug
        if (slug, row.relation) in counterparts:
            continue
        obj = {"type": "country", "slug": slug, "name": slug_to_name(slug) or slug}
        start, end = getattr(row, "valid_from", None), getattr(row, "valid_to", None)
        result.append({"id": row.id, "subject": perspective, "object": obj, "relation": row.relation,
                       "title": None, "label": RELATIONS[row.relation], "direction": "outgoing", "other": obj,
                       "valid_from": start.isoformat() if start else None, "valid_to": end.isoformat() if end else None,
                       "status": "confirmed", "source": row.__tablename__, "editable": False,
                       "detection_method": None, "evidence": []})
    return result


def relations_for_person(session, identifier, include_rejected=False):
    return relations_for(session, "person", identifier, include_rejected)


def relations_for_organization(session, identifier, include_rejected=False):
    return relations_for(session, "organization", identifier, include_rejected)


def document_endpoints(session, document_id):
    return ([{"type": "person", "id": i} for i in session.scalars(
        select(DocumentPerson.person_id).where(DocumentPerson.document_id == document_id))] +
        [{"type": "organization", "id": i} for i in session.scalars(
            select(DocumentOrganization.organization_id).where(DocumentOrganization.document_id == document_id))])


def relations_for_document(session, document_id, include_rejected=False):
    result = {}
    for end in document_endpoints(session, document_id):
        for row in relations_for(session, end["type"], end["id"], include_rejected):
            result[row["source"], row["id"]] = row
    rows = session.scalars(select(EntityRelation).join(EntityRelationEvidence).where(
        EntityRelationEvidence.document_id == document_id)).unique().all()
    for row in rows:
        if include_rejected or row.status != "rejected":
            result["entity_relations", row.id] = relation_dict(session, row)
    return list(result.values())


def absorb_relations(session, kind, source_id, target_id):
    """Move both ends, fold compatible terms and evidence, preserve strongest decisions."""
    rows = session.scalars(select(EntityRelation).where(touching(kind, source_id))).all()
    for row in rows:
        # Release while the old endpoints still identify the owned projection.
        unproject(session, row)
        subject, obj = ends(row)
        for end in (subject, obj):
            if end == {"type": kind, "id": source_id}:
                end["id"] = target_id
        if key(subject) == key(obj):
            session.delete(row)
            session.flush()
            continue
        if row.relation in SYMMETRIC and (subject["type"] != obj["type"] and subject["type"] == "organization" or
                                  subject["type"] == obj["type"] and key(subject) > key(obj)):
            subject, obj = obj, subject
        values = _columns(subject, obj)
        for name, value in values.items():
            setattr(row, name, value)
        session.flush()
        duplicates = session.scalars(select(EntityRelation).filter_by(relation=row.relation, **values).where(
            EntityRelation.id != row.id)).all()
        duplicate = next((r for r in duplicates if compatible(r, row.valid_from, row.valid_to)), None)
        if duplicate:
            rank = {"confirmed": 2, "proposed": 1, "rejected": 0}
            if rank[row.status] > rank[duplicate.status]:
                for name in ("status", "title", "valid_from", "valid_to", "decided_at", "decided_by_user_id"):
                    setattr(duplicate, name, getattr(row, name))
            hashes = {e.content_hash for e in duplicate.evidence}
            for evidence in list(row.evidence):
                if evidence.content_hash not in hashes:
                    row.evidence.remove(evidence)
                    duplicate.evidence.append(evidence)
                    hashes.add(evidence.content_hash)
            session.delete(row)
            row = duplicate
        if row.status == "confirmed":
            project(session, row)
        session.flush()
