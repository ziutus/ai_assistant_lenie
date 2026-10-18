"""Re-apply a document's manual place corrections after its entities were rebuilt.

Reopening a document for editing deletes every derived row, including the
place entities a human renamed, merged or deleted. Those decisions are not lost:
each one is written to ``entity_review_decisions`` (``renamed``, ``place_merged``,
``deleted``/``rejected``) with the names involved. After the next NER run
``replay_manual_place_decisions`` replays them in order against the fresh rows,
matching by name or surface variant, so a correction survives an edit of the
text as long as the mention itself is still there. A decision whose mention is
gone simply finds nothing to act on.

Scope is places plus one organization decision: person re-pointing and organization merges already
persist through the global registry aliases, and exclusion rules live in ``ner_exclusions``. The
exception is ``organization_split`` ("NATO Moskwa" -> NATO + Moskwa): NER returns the glued span again
on every refresh, so ``replay_manual_organization_decisions`` removes it again.
"""

from __future__ import annotations

import logging

from sqlalchemy import or_, select

from library.db.models import DocumentEntity, EntityReviewDecision, GeocodeCache
from library.entity_service import MERGEABLE_PLACE_SOURCE_TYPES, PLACE_TYPES, merge_document_entities

logger = logging.getLogger(__name__)

REPLAYED_DECISIONS = (
    "renamed", "place_merged", "place_confirmed", "place_rejected", "place_to_organization", "place_split",
    "person_to_place", "organization_to_place", "organization_to_person", "deleted", "rejected",
)


def _exact(entities: list[DocumentEntity], name: str, types: tuple[str, ...]) -> DocumentEntity | None:
    key = name.casefold()
    return next((e for e in entities if e.entity_type in types and e.entity_text.casefold() == key), None)


def _by_name_or_variant(entities: list[DocumentEntity], name: str, types: tuple[str, ...]) -> DocumentEntity | None:
    exact = _exact(entities, name, types)
    if exact is not None:
        return exact
    key = name.casefold()
    return next(
        (e for e in entities
         if e.entity_type in types and key in {v.casefold() for v in (e.variants or [])}),
        None,
    )


def convert_place_to_organization(session, entity: DocumentEntity):
    """Retype a place entity as an organization of the same document.

    The mention is resolved against the global organization registry (alias or
    canonical match, else a new ``Organization``) and replaces the place row
    with a ``source='manual'`` ``orgName`` row, so it survives entity refreshes
    like any manual merge. Queues changes without committing; the caller drops
    the place's ``miejsce-*`` tag first, while the row still has its geocode.
    Returns ``(orgName entity, Organization)``.
    """
    from library.db.models import DocumentOrganization
    from library.organization_registry import resolve_or_create

    surface_forms = list(dict.fromkeys([entity.entity_text, *(entity.variants or [])]))
    organization, confidence = resolve_or_create(session, entity.entity_text, surface_forms)
    canonical = organization.canonical_name
    variants = [value for value in surface_forms if value.casefold() != canonical.casefold()]
    document_id, count = entity.document_id, entity.mention_count
    session.delete(entity)
    session.flush()

    target = session.scalar(select(DocumentEntity).where(
        DocumentEntity.document_id == document_id,
        DocumentEntity.entity_type == "orgName",
        DocumentEntity.entity_text == canonical,
    ))
    if target is not None:
        target.mention_count = (target.mention_count or 0) + (count or 0)
        target.variants = list(dict.fromkeys([*(target.variants or []), *variants]))
        target.source = "manual"
    else:
        target = DocumentEntity(
            document_id=document_id, entity_type="orgName", entity_text=canonical,
            mention_count=count, variants=variants, source="manual",
        )
        session.add(target)
    session.flush()
    link = session.scalar(select(DocumentOrganization).where(
        DocumentOrganization.document_id == document_id,
        DocumentOrganization.organization_id == organization.id,
    ))
    if link is None:
        session.add(DocumentOrganization(
            document_id=document_id, organization_id=organization.id,
            document_entity_id=target.id, confidence=confidence,
        ))
    elif link.document_entity_id is None:
        link.document_entity_id = target.id
    return target, organization


def convert_person_to_place(
    session, entity: DocumentEntity, new_text: str | None = None, entities: list[DocumentEntity] | None = None,
) -> DocumentEntity:
    """Retype a person entity as a place of the same document ("Kandaharem" tagged persName).

    The person row is replaced by a ``source='manual'`` ``placeName`` row named ``new_text`` (default: the
    mention as it stands) that keeps the mention count and surface forms, or folded into a same-named place
    the document already has. Dropping the person's ``document_persons`` link is the caller's job (it needs
    the registry); this only queues entity changes, without committing. ``entities`` is the replay list.
    """
    name = (new_text or entity.entity_text).strip()
    document_id, count = entity.document_id, entity.mention_count or 0
    forms = list(dict.fromkeys([entity.entity_text, *(entity.variants or [])]))
    variants = [form for form in forms if form.casefold() != name.casefold()]
    if entities is None:
        entities = list(session.scalars(select(DocumentEntity).where(
            DocumentEntity.document_id == document_id, DocumentEntity.entity_type.in_(PLACE_TYPES),
        )).all())
    session.delete(entity)
    if entity in entities:
        entities.remove(entity)
    session.flush()
    row = _exact(entities, name, PLACE_TYPES)
    if row is not None:
        row.mention_count = (row.mention_count or 0) + count
        row.variants = list(dict.fromkeys([*(row.variants or []), *variants]))
        row.source = "manual"
    else:
        row = DocumentEntity(
            document_id=document_id, entity_type="placeName", entity_text=name,
            mention_count=count, variants=variants, source="manual",
        )
        session.add(row)
        entities.append(row)
    session.flush()
    return row


def convert_entity_to_person(
    session, entity: DocumentEntity, entities: list[DocumentEntity] | None = None,
) -> DocumentEntity:
    """Retype an organization entity as a person of the same document.

    The org row is replaced by a ``source='manual'`` ``persName`` row with the same text, mention count
    and surface forms (or folded into a same-named person row). Dropping the organization link is the
    caller's job (``drop_organization_links``); linking the person to the registry is too
    (``person_registry.resolve_document_persons``). Queues changes without committing.
    """
    document_id, count, name = entity.document_id, entity.mention_count or 0, entity.entity_text
    forms = list(dict.fromkeys([entity.entity_text, *(entity.variants or [])]))
    variants = [form for form in forms if form.casefold() != name.casefold()]
    if entities is None:
        entities = list(session.scalars(select(DocumentEntity).where(
            DocumentEntity.document_id == document_id, DocumentEntity.entity_type == "persName",
        )).all())
    session.delete(entity)
    if entity in entities:
        entities.remove(entity)
    session.flush()
    row = _exact(entities, name, ("persName",))
    if row is not None:
        row.mention_count = (row.mention_count or 0) + count
        row.variants = list(dict.fromkeys([*(row.variants or []), *variants]))
        row.source = "manual"
    else:
        row = DocumentEntity(
            document_id=document_id, entity_type="persName", entity_text=name,
            mention_count=count, variants=variants, source="manual",
        )
        session.add(row)
        entities.append(row)
    session.flush()
    return row


def split_place_entity(
    session, entity: DocumentEntity, parts: list[str], entities: list[DocumentEntity] | None = None,
) -> list[DocumentEntity]:
    """Replace one place entity that lists several places ("Pakistanem Afganistanem") with one per part.

    Every part keeps the compound's mention count and becomes a ``source='manual'`` row of the
    same type (so entity refreshes leave it alone), or is folded into a same-named place the
    document already has. Surface forms are handed to the parts word by word when the
    compound's form has exactly as many words as there are parts, so the per-chapter
    highlighting still finds "Pakistanem" for Pakistan. Queues changes without committing.
    ``entities`` is the caller's in-memory list (replay); it is kept in step with the session.
    """
    from library.entity_service import split_place_tokens

    document_id, entity_type, count = entity.document_id, entity.entity_type, entity.mention_count or 0
    forms = list(dict.fromkeys([entity.entity_text, *(entity.variants or [])]))
    forms_by_part: dict[str, list[str]] = {part: [] for part in parts}
    for form in forms:
        tokens = split_place_tokens(form)
        if len(tokens) == len(parts):
            for part, token in zip(parts, tokens, strict=True):
                forms_by_part[part].append(token)
    if entities is None:
        entities = list(session.scalars(select(DocumentEntity).where(
            DocumentEntity.document_id == document_id, DocumentEntity.entity_type.in_(PLACE_TYPES),
        )).all())
    session.delete(entity)
    if entity in entities:
        entities.remove(entity)
    session.flush()

    rows = []
    for part in parts:
        variants = [v for v in dict.fromkeys(forms_by_part[part]) if v.casefold() != part.casefold()]
        row = _exact(entities, part, PLACE_TYPES)
        if row is not None:
            row.mention_count = (row.mention_count or 0) + count
            row.variants = list(dict.fromkeys([*(row.variants or []), *variants]))
            row.source = "manual"
        else:
            row = DocumentEntity(
                document_id=document_id, entity_type=entity_type, entity_text=part,
                mention_count=count, variants=variants, source="manual",
            )
            session.add(row)
            entities.append(row)
        rows.append(row)
    session.flush()
    return rows


def drop_organization_links(session, entity: DocumentEntity) -> None:
    """Delete the document's organization links that point at ``entity`` (the organization stays)."""
    from library.db.models import DocumentOrganization

    for link in session.scalars(select(DocumentOrganization).where(
        DocumentOrganization.document_entity_id == entity.id,
    )).all():
        session.delete(link)


_drop_organization_links = drop_organization_links


def split_organization_entity(
    session, entity: DocumentEntity, parts: list[str], entities: list[DocumentEntity] | None = None,
    *, fold_counts: bool = True,
) -> list[tuple[DocumentEntity, object]]:
    """Replace one orgName entity made of several glued mentions ("NATO Moskwa") with one per part.

    Every part is resolved through the organization registry (alias or canonical match, else a new
    ``Organization``), becomes a ``source='manual'`` ``orgName`` row named by the organization's
    canonical name with the compound's mention count (or is folded into a same-named row the document
    already has) and gets its ``DocumentOrganization`` link. Surface forms go to the parts word by word
    when the compound has exactly as many words as parts. The compound's own link is dropped; the
    organization it pointed at stays in the registry. ``fold_counts=False`` leaves the counts of rows that
    already exist alone (replay after a refresh). Queues changes without committing.
    """
    from library.db.models import DocumentOrganization
    from library.entity_service import split_place_tokens
    from library.organization_registry import resolve_or_create

    document_id, count = entity.document_id, entity.mention_count or 0
    forms = list(dict.fromkeys([entity.entity_text, *(entity.variants or [])]))
    forms_by_part: dict[str, list[str]] = {part: [] for part in parts}
    for form in forms:
        tokens = split_place_tokens(form)
        if len(tokens) == len(parts):
            for part, token in zip(parts, tokens, strict=True):
                forms_by_part[part].append(token)
    if entities is None:
        entities = list(session.scalars(select(DocumentEntity).where(
            DocumentEntity.document_id == document_id, DocumentEntity.entity_type == "orgName",
        )).all())
    _drop_organization_links(session, entity)
    session.delete(entity)
    if entity in entities:
        entities.remove(entity)
    session.flush()

    results = []
    for part in parts:
        part_forms = list(dict.fromkeys([part, *forms_by_part[part]]))
        organization, confidence = resolve_or_create(session, part, part_forms)
        canonical = organization.canonical_name
        variants = [form for form in part_forms if form.casefold() != canonical.casefold()]
        row = _exact(entities, canonical, ("orgName",))
        if row is not None:
            if fold_counts:
                row.mention_count = (row.mention_count or 0) + count
            row.variants = list(dict.fromkeys([*(row.variants or []), *variants]))
            row.source = "manual"
        else:
            row = DocumentEntity(
                document_id=document_id, entity_type="orgName", entity_text=canonical,
                mention_count=count, variants=variants, source="manual",
            )
            session.add(row)
            entities.append(row)
        session.flush()
        link = session.scalar(select(DocumentOrganization).where(
            DocumentOrganization.document_id == document_id,
            DocumentOrganization.organization_id == organization.id,
        ))
        if link is None:
            session.add(DocumentOrganization(
                document_id=document_id, organization_id=organization.id,
                document_entity_id=row.id, confidence=confidence,
            ))
        elif link.document_entity_id is None:
            link.document_entity_id = row.id
        results.append((row, organization))
    session.flush()
    return results


def replay_manual_organization_decisions(session, document_id: int) -> dict:
    """Re-apply the document's ``organization_split`` decisions after its entities were rebuilt.

    NER returns the glued span again ("NATO Moskwa"). When the manual part rows survived the refresh
    (they are ``source='manual'``), only the glued row and its link are removed — counts are not added a
    second time; when everything was rebuilt (reopen for editing) the split is performed again. A decision
    whose mention is gone finds nothing to act on. Queues changes without committing.
    """
    decisions = session.scalars(
        select(EntityReviewDecision).where(
            EntityReviewDecision.document_id == document_id,
            EntityReviewDecision.decision == "organization_split",
            EntityReviewDecision.entity_type == "orgName",
        ).order_by(EntityReviewDecision.id)
    ).all()
    if not decisions:
        return {}
    entities = list(session.scalars(select(DocumentEntity).where(
        DocumentEntity.document_id == document_id, DocumentEntity.entity_type == "orgName",
    )).all())
    replayed = 0
    for decision in decisions:
        details = decision.details or {}
        parts = [p for p in details.get("parts", []) if p]
        row = _by_name_or_variant(entities, decision.entity_text, ("orgName",))
        if row is None or len(parts) < 2:
            continue
        part_names = [n for n in details.get("part_names", []) if n]
        if part_names and all(_exact(entities, name, ("orgName",)) is not None for name in part_names):
            _drop_organization_links(session, row)
            session.delete(row)
            entities.remove(row)
            session.flush()
        else:
            split_organization_entity(session, row, parts, entities)
        replayed += 1
    if replayed:
        logger.info("Re-applied %d organization split(s) for doc %s", replayed, document_id)
    return {"organization_split": replayed} if replayed else {}


def apply_decisions(session, decisions, entities: list[DocumentEntity]) -> tuple[dict[int, DocumentEntity], dict]:
    """Replay ``decisions`` (oldest first) against ``entities``, mutating both.

    Returns (rows that were renamed or merged into and still exist, counters).
    ``entities`` is kept in step with the session so later decisions see the
    result of earlier ones.
    """
    touched: dict[int, DocumentEntity] = {}
    stats = {"renamed": 0, "merged": 0, "deleted": 0}

    def drop(row: DocumentEntity) -> None:
        session.delete(row)
        entities.remove(row)
        touched.pop(id(row), None)
        # Flush now: a later decision may rename another row into this name.
        session.flush()

    for decision in decisions:
        details = decision.details or {}
        if decision.decision == "place_confirmed":
            row = None
            for name in (decision.entity_text, *details.get("variants", [])):
                row = _by_name_or_variant(entities, name, PLACE_TYPES)
                if row is not None:
                    break
            if row is None:
                continue
            proposal = session.get(GeocodeCache, details.get("geocode_id"))
            # Never substitute a new first hit if the selected cache row disappeared.
            if proposal is None:
                row.place_verification_status = "needs_review"
                row.place_review_reason = "confirmed_geocode_missing"
                continue
            row.geocode = proposal
            row.geocode_id = proposal.id
            row.place_verification_status = "confirmed"
            row.place_review_reason = None
            row.source = "manual"
            touched[id(row)] = row
            stats["confirmed"] = stats.get("confirmed", 0) + 1
        elif decision.decision == "place_rejected":
            row = _by_name_or_variant(entities, decision.entity_text, PLACE_TYPES)
            if row is None:
                continue
            row.place_verification_status = "rejected"
            row.place_review_reason = "rejected_by_user"
            row.source = "manual"
            stats["place_rejected"] = stats.get("place_rejected", 0) + 1
        elif decision.decision == "place_to_organization":
            row = _by_name_or_variant(entities, decision.entity_text, PLACE_TYPES)
            if row is None:
                continue
            convert_place_to_organization(session, row)
            entities.remove(row)
            touched.pop(id(row), None)
            stats["to_organization"] = stats.get("to_organization", 0) + 1
        elif decision.decision == "person_to_place":
            row = _by_name_or_variant(entities, decision.entity_text, ("persName",))
            if row is None:
                continue
            touched.pop(id(row), None)
            place = convert_person_to_place(session, row, details.get("new_text"), entities)
            touched[id(place)] = place
            stats["person_to_place"] = stats.get("person_to_place", 0) + 1
        elif decision.decision in ("organization_to_place", "organization_to_person"):
            row = _by_name_or_variant(entities, decision.entity_text, ("orgName",))
            if row is None:
                continue
            touched.pop(id(row), None)
            drop_organization_links(session, row)
            if decision.decision == "organization_to_place":
                place = convert_person_to_place(session, row, details.get("new_text"), entities)
                touched[id(place)] = place
            else:
                convert_entity_to_person(session, row, entities)
            stats[decision.decision] = stats.get(decision.decision, 0) + 1
        elif decision.decision == "place_split":
            parts = [p for p in details.get("parts", []) if p]
            row = _by_name_or_variant(entities, decision.entity_text, PLACE_TYPES)
            if row is None or len(parts) < 2:
                continue
            touched.pop(id(row), None)
            for part_row in split_place_entity(session, row, parts, entities):
                touched[id(part_row)] = part_row
            stats["split"] = stats.get("split", 0) + 1
        elif decision.decision == "renamed":
            new_name = (details.get("new_text") or "").strip()
            row = _by_name_or_variant(entities, decision.entity_text, PLACE_TYPES)
            if not new_name or row is None or row.entity_text.casefold() == new_name.casefold():
                continue
            existing = _exact(entities, new_name, (row.entity_type,))
            if existing is not None and existing is not row:
                merge_document_entities(row, existing)
                drop(row)
                touched[id(existing)] = existing
            else:
                variants = dict.fromkeys(row.variants or [])
                for value in (*details.get("variants", []), row.entity_text, new_name):
                    variants.setdefault(value)
                row.entity_text = new_name
                row.variants = list(variants)
                row.source = "manual"
                row.geocode = None
                row.geocode_id = None
                session.flush()
                touched[id(row)] = row
            stats["renamed"] += 1
        elif decision.decision == "place_merged":
            target = _by_name_or_variant(entities, details.get("target_entity_text") or decision.entity_text, PLACE_TYPES)
            source = None
            for name in (details.get("source_entity_text"), *details.get("source_variants", [])):
                if name:
                    source = _by_name_or_variant(entities, name, MERGEABLE_PLACE_SOURCE_TYPES)
                    if source is not None:
                        break
            if target is None or source is None or source is target:
                continue
            merge_document_entities(source, target)
            drop(source)
            touched[id(target)] = target
            stats["merged"] += 1
        else:  # deleted / rejected: exact text only, never a merged row hiding behind a variant
            row = _exact(entities, decision.entity_text, PLACE_TYPES)
            if row is None:
                confirmed = _by_name_or_variant(list(touched.values()), decision.entity_text, PLACE_TYPES)
                if confirmed is not None and confirmed.place_verification_status == "confirmed":
                    row = confirmed
            if row is None:
                continue
            drop(row)
            stats["deleted"] += 1
    return touched, stats


def replay_manual_place_decisions(session, document_id: int, doc=None) -> dict:
    """Replay the document's manual place decisions on its current entity rows.

    Queues changes on the session without committing. Renamed/merged rows that
    ended up without a geocode are geocoded (one cached lookup each, failures
    swallowed), because the enrichment pass skips ``source='manual'`` rows.
    """
    decisions = session.scalars(
        select(EntityReviewDecision)
        .where(
            EntityReviewDecision.document_id == document_id,
            EntityReviewDecision.decision.in_(REPLAYED_DECISIONS),
            or_(
                EntityReviewDecision.entity_type.in_(PLACE_TYPES),
                (EntityReviewDecision.entity_type == "persName")
                & (EntityReviewDecision.decision == "person_to_place"),
                (EntityReviewDecision.entity_type == "orgName")
                & EntityReviewDecision.decision.in_(("organization_to_place", "organization_to_person")),
            ),
        )
        .order_by(EntityReviewDecision.id)
    ).all()
    if not decisions:
        return {}
    entities = list(session.scalars(
        select(DocumentEntity).where(
            DocumentEntity.document_id == document_id,
            DocumentEntity.entity_type.in_((*MERGEABLE_PLACE_SOURCE_TYPES, "persName", "orgName")),
        )
    ).all())
    touched, stats = apply_decisions(session, decisions, entities)

    if touched:
        from library.country_gazetteer import canonical_country_name
        from library.place_verification import add_place_tag, geocode_single_place

        for row in touched.values():
            if row.place_verification_status == "confirmed":
                add_place_tag(doc, row)
                continue
            # Countries are never geocoded (own kraj-* pipeline), same as place verification.
            if row.geocode_id is None and canonical_country_name(row.entity_text) is None:
                try:
                    geocode_single_place(session, doc, row)
                except Exception:
                    logger.exception("Geocoding replayed place %r failed for doc %s", row.entity_text, document_id)
    if any(stats.values()):
        logger.info("Re-applied manual place decisions for doc %s: %s", document_id, stats)
    return stats
