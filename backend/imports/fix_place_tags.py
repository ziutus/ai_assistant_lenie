#!/usr/bin/env python3
"""One-off cleanup: merge duplicate miejsce-* tags created from inflected NER variants.

Before place_verification built tags from the geocoder's canonical name, each
inflected NER variant produced its own tag (miejsce-kijowa + miejsce-kijow,
miejsce-moskwy + miejsce-moskwa). This script recomputes each document's
miejsce-* tags via the same canonical_place_name() the pipeline now uses
(geocode_cache.display_name) and rewrites doc.tags. A miejsce-* tag with no
matching resolved place entity is left untouched — no geocoder calls are made,
only cached results are used.

Usage:
    cd backend
    .venv/Scripts/python imports/fix_place_tags.py            # dry-run (default)
    .venv/Scripts/python imports/fix_place_tags.py --apply
    .venv/Scripts/python imports/fix_place_tags.py --id 9216  # single document
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import DocumentEntity, WebDocument  # noqa: E402
from library.locationiq_client import canonical_place_name  # noqa: E402
from library.place_verification import PLACE_ENTITY_TYPES, _slugify  # noqa: E402

logger = logging.getLogger(__name__)

PREFIX = "miejsce-"


def slug_corrections(session, doc_id: int) -> dict[str, str]:
    """Map old tag slug (from NER surface form) -> canonical slug, per document.

    Only entities with a resolved geocode contribute — for those, the old
    pipeline created a tag from the surface form and the canonical spelling is
    known from geocode_cache.display_name.
    """
    entities = (
        session.query(DocumentEntity)
        .filter(
            DocumentEntity.document_id == doc_id,
            DocumentEntity.entity_type.in_(PLACE_ENTITY_TYPES),
        )
        .all()
    )
    corrections: dict[str, str] = {}
    for ent in entities:
        if ent.geocode is None or not ent.geocode.resolved:
            continue
        old_slug = _slugify(ent.entity_text)
        canonical = canonical_place_name(ent.entity_text, ent.geocode.display_name or "")
        new_slug = _slugify(canonical)
        if old_slug and new_slug:
            corrections[old_slug] = new_slug
    return corrections


def rewrite_tags(tags: str, corrections: dict[str, str]) -> str:
    """Apply slug corrections to miejsce-* tags and drop resulting duplicates."""
    result: list[str] = []
    seen: set[str] = set()
    for tag in (t.strip() for t in tags.split(",")):
        if not tag:
            continue
        if tag.startswith(PREFIX):
            slug = tag[len(PREFIX):]
            tag = PREFIX + corrections.get(slug, slug)
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return ",".join(result)


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate miejsce-* tags (inflected NER variants).")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        query = session.query(WebDocument).filter(WebDocument.tags.like(f"%{PREFIX}%"))
        if args.id:
            query = query.filter(WebDocument.id == args.id)
        docs = query.order_by(WebDocument.id).all()
        logging.info("Found %d documents with %s* tags", len(docs), PREFIX)

        changed = 0
        for doc in docs:
            corrections = slug_corrections(session, doc.id)
            new_tags = rewrite_tags(doc.tags, corrections)
            if new_tags == doc.tags:
                continue
            changed += 1
            logging.info("doc #%s:\n  old: %s\n  new: %s", doc.id, doc.tags, new_tags)
            if args.apply:
                doc.tags = new_tags

        if args.apply:
            session.commit()
            logging.info("Done. Updated %d of %d documents.", changed, len(docs))
        else:
            logging.info("Dry-run: %d of %d documents would change. Re-run with --apply to save.", changed, len(docs))
    finally:
        session.close()


if __name__ == "__main__":
    main()
