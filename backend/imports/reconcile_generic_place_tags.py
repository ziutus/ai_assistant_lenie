#!/usr/bin/env python3
"""Review generic place proposals and remove unsupported tags (dry-run by default)."""

import argparse
import logging

from library.db.models import Document, DocumentEntity
from library.generic_place_names import match_generic_place_name
from library.locationiq_client import canonical_place_name
from library.place_verification import PLACE_ENTITY_TYPES, _slugify, place_needs_review


def reconcile_document(session, document) -> dict:
    """Queue changes in the caller's transaction without modifying geocode_cache."""
    entities = session.query(DocumentEntity).filter(
        DocumentEntity.document_id == document.id,
        DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
    ).all()
    blocked_tags, supported_tags = set(), set()
    reviewed = []
    for entity in entities:
        geo = entity.geocode
        canonical = canonical_place_name(entity.entity_text, geo.display_name or "") if geo else None
        rule = match_generic_place_name(entity.entity_text, entity.variants, canonical)
        blocked = place_needs_review(entity)
        if rule is not None and blocked:
            reviewed.append(entity.id)
            if canonical:
                blocked_tags.add(f"miejsce-{_slugify(canonical)}")
        elif not blocked and geo is not None and geo.resolved:
            supported_tags.add(f"miejsce-{_slugify(canonical)}")
    removed = blocked_tags - supported_tags
    tags = [t.strip() for t in (document.tags or "").split(",") if t.strip()]
    removed &= set(tags)
    if removed:
        document.tags = ",".join(t for t in tags if t not in removed)
    return {"reviewed": reviewed, "removed_tags": sorted(removed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report changes and roll back (default)")
    mode.add_argument("--apply", action="store_true", help="Commit changes")
    parser.add_argument("--document-id", type=int)
    args = parser.parse_args()

    from library.config_loader import load_config
    load_config()
    from library.db.engine import get_session

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = get_session()
    # Dry-run must not emit UPDATEs through query-triggered autoflush either.
    if not args.apply:
        session.autoflush = False
    try:
        query = session.query(Document).filter(Document.id.in_(
            session.query(DocumentEntity.document_id).filter(DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES))
        ))
        if args.document_id is not None:
            query = query.filter(Document.id == args.document_id)
        for document in query.order_by(Document.id).yield_per(100):
            result = reconcile_document(session, document)
            if result["reviewed"] or result["removed_tags"]:
                logging.info("doc #%s: %s", document.id, result)
        if args.apply:
            session.commit()
        else:
            session.rollback()
            logging.info("Dry-run: all changes rolled back.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
