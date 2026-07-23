#!/usr/bin/env python3
"""One-off backfill for the global organization registry (docs/organization-ner-alias-plan.md).

Alembic migration e23a1b2c3d4e creates the organizations/organization_aliases/
document_organizations tables and seeds Interia (+ inflected aliases) and
Bloomberg/KCNA (replacing the old hardcoded name mapping in
library/information_provenance.py). This script covers what a schema
migration must not do on its own:

1. For every pre-existing document_entities(orgName) row whose text or any
   variant matches a seeded/registered organization alias, rewrite it to the
   organization's canonical_name and merge same-document duplicates (the
   "Interia"/"Interii" reference case) into one row + one document_organizations
   link.
2. Link pre-existing information_sources rows to the matching organization
   (by exact case-insensitive canonical_name/alias match) so the next NER
   refresh resolves Bloomberg/KCNA via organization_id instead of creating a
   second information_sources row (library/information_provenance.py now
   looks up by organization_id first, see _get_or_create_source()).

Never touches placeName/geogName/persName entities or ner_exclusions.

Usage:
    cd backend
    .venv/Scripts/python imports/backfill_organizations.py            # dry-run (default)
    .venv/Scripts/python imports/backfill_organizations.py --apply
    .venv/Scripts/python imports/backfill_organizations.py --id 9267  # single document
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import (  # noqa: E402
    Document,
    DocumentEntity,
    DocumentOrganization,
    InformationSource,
    Organization,
)
from library.organization_registry import CONFIDENCE_CANONICAL_MATCHED, normalize_alias  # noqa: E402

logger = logging.getLogger(__name__)


def _organization_alias_index(session) -> dict[str, Organization]:
    """normalized alias/canonical_name -> Organization, for every registered organization."""
    index: dict[str, Organization] = {}
    for organization in session.query(Organization).all():
        index.setdefault(normalize_alias(organization.canonical_name), organization)
        for alias in organization.aliases:
            index.setdefault(normalize_alias(alias.alias), organization)
    return index


def _resolve(entity: DocumentEntity, index: dict[str, Organization]) -> Organization | None:
    for candidate in [entity.entity_text, *(entity.variants or [])]:
        organization = index.get(normalize_alias(candidate))
        if organization is not None:
            return organization
    return None


def plan_entity_merges(session, index: dict[str, Organization], doc_id: int | None = None) -> list[dict]:
    """Group document_entities(orgName) rows by (document, resolved organization).

    Returns one plan entry per (document, organization) group that needs a
    write: either a same-document merge of 2+ rows into one, or a single row
    whose entity_text/document_organizations link is still missing/stale.
    """
    query = session.query(DocumentEntity).filter(DocumentEntity.entity_type == "orgName")
    if doc_id is not None:
        query = query.filter(DocumentEntity.document_id == doc_id)

    by_doc_org: dict[tuple[int, int], list[DocumentEntity]] = {}
    for entity in query.order_by(DocumentEntity.document_id).all():
        organization = _resolve(entity, index)
        if organization is None:
            continue
        by_doc_org.setdefault((entity.document_id, organization.id), []).append(entity)

    existing_links = {
        (link.document_id, link.organization_id): link
        for link in session.query(DocumentOrganization).all()
    }

    plans = []
    for (document_id, organization_id), entities in by_doc_org.items():
        organization = session.get(Organization, organization_id)
        surviving = max(entities, key=lambda e: (e.mention_count, e.id))
        duplicates = [e for e in entities if e.id != surviving.id]
        combined_variants = dict.fromkeys(surviving.variants or [])
        for dup in duplicates:
            for value in [dup.entity_text, *(dup.variants or [])]:
                if value.casefold() != organization.canonical_name.casefold():
                    combined_variants.setdefault(value)
        for value in list(combined_variants):
            if value.casefold() == organization.canonical_name.casefold():
                combined_variants.pop(value)
        new_mention_count = sum(e.mention_count for e in entities)
        link_exists = (document_id, organization_id) in existing_links

        needs_write = (
            bool(duplicates)
            or surviving.entity_text != organization.canonical_name
            or surviving.mention_count != new_mention_count
            or set(surviving.variants or []) != set(combined_variants)
            or not link_exists
        )
        if not needs_write:
            continue
        plans.append({
            "document_id": document_id,
            "organization_id": organization_id,
            "canonical_name": organization.canonical_name,
            "surviving_entity_id": surviving.id,
            "duplicate_entity_ids": [e.id for e in duplicates],
            "old_texts": [e.entity_text for e in entities],
            "new_mention_count": new_mention_count,
            "new_variants": list(combined_variants),
            "link_exists": link_exists,
        })
    return plans


def apply_entity_merge(session, plan: dict) -> None:
    # Delete duplicates BEFORE renaming the surviving row: the surviving row's
    # canonical_name may already belong to another row in this document (the
    # "Interia" + "Interii" reference case) — renaming first would collide
    # with unique(document_id, entity_type, entity_text) while the duplicate
    # still exists.
    for duplicate_id in plan["duplicate_entity_ids"]:
        duplicate = session.get(DocumentEntity, duplicate_id)
        if duplicate is not None:
            session.delete(duplicate)
    session.flush()

    surviving = session.get(DocumentEntity, plan["surviving_entity_id"])
    surviving.entity_text = plan["canonical_name"]
    surviving.mention_count = plan["new_mention_count"]
    surviving.variants = plan["new_variants"]
    session.flush()
    if not plan["link_exists"]:
        session.add(DocumentOrganization(
            document_id=plan["document_id"],
            organization_id=plan["organization_id"],
            document_entity_id=surviving.id,
            confidence=CONFIDENCE_CANONICAL_MATCHED,
        ))
    else:
        link = session.query(DocumentOrganization).filter(
            DocumentOrganization.document_id == plan["document_id"],
            DocumentOrganization.organization_id == plan["organization_id"],
        ).first()
        if link is not None:
            link.document_entity_id = surviving.id


def plan_information_source_links(session, index: dict[str, Organization]) -> list[dict]:
    """Pre-existing information_sources rows that match a registered organization by name."""
    plans = []
    for source in session.query(InformationSource).filter(InformationSource.organization_id.is_(None)).all():
        names = [source.canonical_name, *(a.alias for a in source.aliases)]
        organization = next((index.get(normalize_alias(n)) for n in names if index.get(normalize_alias(n))), None)
        if organization is None:
            continue
        plans.append({
            "source_id": source.id,
            "source_name": source.canonical_name,
            "organization_id": organization.id,
            "organization_name": organization.canonical_name,
        })
    return plans


def apply_information_source_link(session, plan: dict) -> None:
    source = session.get(InformationSource, plan["source_id"])
    source.organization_id = plan["organization_id"]


def main():
    parser = argparse.ArgumentParser(description="Backfill the global organization registry.")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single document by id (entity merges only)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        index = _organization_alias_index(session)
        logger.info("Loaded %d organizations (with aliases) from the registry", len(session.query(Organization).all()))

        entity_plans = plan_entity_merges(session, index, doc_id=args.id)
        for plan in entity_plans:
            doc = session.get(Document, plan["document_id"])
            logger.info(
                "doc #%s (%s): %s -> %r (mentions=%d, variants=%s)%s",
                plan["document_id"], doc.title if doc else "?",
                plan["old_texts"], plan["canonical_name"],
                plan["new_mention_count"], plan["new_variants"],
                "" if plan["link_exists"] else " [new document_organizations link]",
            )
            if args.apply:
                apply_entity_merge(session, plan)

        source_plans = []
        if args.id is None:
            source_plans = plan_information_source_links(session, index)
            for plan in source_plans:
                logger.info(
                    "information_source #%s (%s) -> organization #%s (%s)",
                    plan["source_id"], plan["source_name"], plan["organization_id"], plan["organization_name"],
                )
                if args.apply:
                    apply_information_source_link(session, plan)

        if args.apply:
            session.commit()
            logger.info(
                "Done. Merged %d document/organization group(s), linked %d information source(s).",
                len(entity_plans), len(source_plans),
            )
        else:
            logger.info(
                "Dry-run: %d document/organization group(s) and %d information source(s) would change. "
                "Re-run with --apply to save.",
                len(entity_plans), len(source_plans),
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
