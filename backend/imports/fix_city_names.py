#!/usr/bin/env python3
"""One-off backfill: canonicalize geogName/placeName entity_text for known
single/hyphenated-word foreign cities (library/city_gazetteer.py).

Same story as fix_geo_feature_names.py, but for cities: before this
gazetteer existed, a rare foreign city name mentioned only in an inflected
case ("Omdurmanie", "Port Sudanu") had nothing to recover the nominative
form from — NOMINATIVE_PREFERENCE_TYPES never applies to single-word
surfaces. entity_text ended up stored inflected, which then also broke
geocoding (the geocoder got the inflected string). ner_client.py now avoids
this for every future NER run; this script fixes the document_entities rows
that were written before that fix shipped (found via the doc #9394
investigation — "Omdurmanie" verified=false, "Port Sudanu"/"Port Sudanem"
similarly leaked their case into entity_text).

Renames entity_text to the gazetteer's canonical spelling. When a document
already has a separate row already spelled canonically (or another
differently-inflected row that also resolves to the same canonical name), the
duplicates are merged into one row (mention_count summed, variants unioned,
geocode_id kept from whichever row has one) instead of violating the
(document_id, entity_type, entity_text) unique constraint. Old entity_text
values are preserved in variants. geocode_id is left untouched — a broken
"resolved=false" geocode_cache link stays broken (a correct canonical name
CAN geocode successfully, but re-verifying is a separate, LLM-touching step
outside this backfill's scope — re-run POST /website_entities for a document
afterwards to pick up a fresh geocode against the corrected name).

Usage:
    cd backend
    .venv/Scripts/python imports/fix_city_names.py            # dry-run (default)
    .venv/Scripts/python imports/fix_city_names.py --apply
    .venv/Scripts/python imports/fix_city_names.py --id 9394  # single document
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.city_gazetteer import canonical_city_name  # noqa: E402
from library.db.engine import get_session  # noqa: E402
from library.db.models import DocumentEntity  # noqa: E402
from library.entity_service import merge_document_entities  # noqa: E402

logger = logging.getLogger(__name__)

PLACE_TYPES = ("geogName", "placeName")


def plan_document(rows: list[DocumentEntity]) -> list[tuple[DocumentEntity, list[DocumentEntity], str]]:
    """Group a document's place rows by (entity_type, canonical city name).

    Returns one (target, duplicates, canonical_name) tuple per group that
    actually needs a change — target is the row to keep (existing canonical
    spelling preferred, else highest mention_count), duplicates are the rows
    to merge into it and delete. Rows with no gazetteer match, or already
    correctly spelled with nothing to merge, are omitted.
    """
    groups: dict[tuple[str, str], list[DocumentEntity]] = {}
    for row in rows:
        canonical = canonical_city_name(row.entity_text)
        if canonical is None:
            continue
        groups.setdefault((row.entity_type, canonical), []).append(row)

    plan = []
    for (entity_type, canonical), group_rows in groups.items():
        already_correct = [r for r in group_rows if r.entity_text == canonical]
        if len(group_rows) == 1 and already_correct:
            continue  # nothing to do
        target = already_correct[0] if already_correct else max(group_rows, key=lambda r: r.mention_count)
        duplicates = [r for r in group_rows if r is not target]
        if not duplicates and target.entity_text == canonical:
            continue
        plan.append((target, duplicates, canonical))
    return plan


def main():
    parser = argparse.ArgumentParser(description="Canonicalize known city entity_text values.")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        query = session.query(DocumentEntity).filter(DocumentEntity.entity_type.in_(PLACE_TYPES))
        if args.id:
            query = query.filter(DocumentEntity.document_id == args.id)
        rows = query.order_by(DocumentEntity.document_id).all()

        by_document: dict[int, list[DocumentEntity]] = {}
        for row in rows:
            by_document.setdefault(row.document_id, []).append(row)
        logger.info("Scanning %d place entities across %d documents", len(rows), len(by_document))

        changed_docs = 0
        changed_rows = 0
        for doc_id, doc_rows in by_document.items():
            plan = plan_document(doc_rows)
            if not plan:
                continue
            changed_docs += 1
            for target, duplicates, canonical in plan:
                old_text = target.entity_text
                logger.info(
                    "doc #%s [%s]: %r -> %r%s",
                    doc_id, target.entity_type, old_text, canonical,
                    f" (merging {[d.entity_text for d in duplicates]})" if duplicates else "",
                )
                if not args.apply:
                    continue
                for dup in duplicates:
                    merge_document_entities(dup, target, target_source="geocoded")
                    session.delete(dup)
                if target.entity_text != canonical:
                    if old_text not in (target.variants or []):
                        target.variants = [*(target.variants or []), old_text]
                    target.entity_text = canonical
                changed_rows += 1

        if args.apply:
            session.commit()
            logger.info("Done. Updated %d rows across %d of %d documents.", changed_rows, changed_docs, len(by_document))
        else:
            logger.info(
                "Dry-run: %d documents would change. Re-run with --apply to save.", changed_docs,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
