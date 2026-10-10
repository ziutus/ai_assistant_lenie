"""Re-apply a document's manual place corrections after its entities were rebuilt.

Reopening a document for editing deletes every derived row, including the
place entities a human renamed, merged or deleted. Those decisions are not lost:
each one is written to ``entity_review_decisions`` (``renamed``, ``place_merged``,
``deleted``/``rejected``) with the names involved. After the next NER run
``replay_manual_place_decisions`` replays them in order against the fresh rows,
matching by name or surface variant, so a correction survives an edit of the
text as long as the mention itself is still there. A decision whose mention is
gone simply finds nothing to act on.

Scope is deliberately places: person re-pointing and organization merges already
persist through the global registry aliases, and exclusion rules live in
``ner_exclusions``.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from library.db.models import DocumentEntity, EntityReviewDecision, GeocodeCache
from library.entity_service import MERGEABLE_PLACE_SOURCE_TYPES, PLACE_TYPES, merge_document_entities

logger = logging.getLogger(__name__)

REPLAYED_DECISIONS = ("renamed", "place_merged", "place_confirmed", "deleted", "rejected")


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
            EntityReviewDecision.entity_type.in_(PLACE_TYPES),
        )
        .order_by(EntityReviewDecision.id)
    ).all()
    if not decisions:
        return {}
    entities = list(session.scalars(
        select(DocumentEntity).where(
            DocumentEntity.document_id == document_id,
            DocumentEntity.entity_type.in_(MERGEABLE_PLACE_SOURCE_TYPES),
        )
    ).all())
    touched, stats = apply_decisions(session, decisions, entities)

    if touched:
        from library.place_verification import add_place_tag, geocode_single_place

        for row in touched.values():
            if row.place_verification_status == "confirmed":
                add_place_tag(doc, row)
                continue
            if row.geocode_id is None:
                try:
                    geocode_single_place(session, doc, row)
                except Exception:
                    logger.exception("Geocoding replayed place %r failed for doc %s", row.entity_text, document_id)
    if any(stats.values()):
        logger.info("Re-applied manual place decisions for doc %s: %s", document_id, stats)
    return stats
