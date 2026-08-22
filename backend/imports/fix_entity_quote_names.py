#!/usr/bin/env python3
"""One-off backfill: strip stray quotation marks from NER entity names.

Before ner_normalization.strip_wrapping_quotes() existed, spaCy kept source-
text quotation marks inside entity spans (live case, doc 9394:
'jako "sudańskie Bractwo Muzułmańskie", zostali' -> orgName span
'Bractwo Muzułmańskie"', mangled lemma 'bractwo Muzułmański"'). Those spans
reached organizations.canonical_name, organization_aliases and
document_entities.entity_text/variants verbatim. ner_client.py now cleans
every future mention; this script fixes the rows written before that fix.

Three layers, in dependency order:
  1. organizations — clean canonical_name; when the cleaned name matches an
     existing organization (its canonical name or an alias), the dirty one is
     merged into it (library/organization_registry.merge(), WITHOUT keeping
     the dirty name as a global alias). Otherwise renamed in place.
  2. organization_aliases — clean alias/normalized_alias; delete rows that
     become empty, redundant (equal to their org's canonical name) or
     same-org duplicates; SKIP (with a warning) aliases that would collide
     with a different organization — ambiguity is never auto-resolved.
  3. document_entities — clean entity_text and variants in place; when two
     rows of the same document+type converge on one name after cleaning,
     they are merged (mention_count summed, variants unioned via
     library/entity_service.merge_document_entities()) instead of violating
     the (document_id, entity_type, entity_text) unique constraint;
     document_organizations.document_entity_id references are re-pointed to
     the surviving row.

Balanced inner quotations are deliberately preserved ('Aleksander „Rocky”',
'CBRE "European data Centres"') — see strip_wrapping_quotes() for the exact
rules. Mid-span non-quote junk ('Donald Trump,"szejk' keeps its comma) is out
of scope. Rows are NOT protected from a later NER refresh (source stays
'ner') — a re-run rebuilds them cleanly anyway.

Usage:
    cd backend
    .venv/Scripts/python imports/fix_entity_quote_names.py            # dry-run (default)
    .venv/Scripts/python imports/fix_entity_quote_names.py --apply
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from sqlalchemy import func  # noqa: E402

from library.db.engine import get_session  # noqa: E402
from library.db.models import (  # noqa: E402
    DocumentEntity,
    DocumentOrganization,
    Organization,
    OrganizationAlias,
)
from library.entity_service import merge_document_entities  # noqa: E402
from library.ner_normalization import normalize_ner_text, strip_wrapping_quotes  # noqa: E402
from library.organization_registry import merge as merge_organizations  # noqa: E402
from library.organization_registry import normalize_alias  # noqa: E402

logger = logging.getLogger(__name__)

QUOTE_CHARS = "\"\u201e\u201d\u00ab\u00bb"


def _has_quote(value: str | None) -> bool:
    return bool(value) and any(char in value for char in QUOTE_CHARS)


def clean_name(value: str | None) -> str:
    """Full cleaning pipeline applied to every stored name/variant."""
    return normalize_ner_text(strip_wrapping_quotes(value or ""))


def fix_organizations(session, apply: bool) -> tuple[int, int]:
    """Clean organizations.canonical_name; returns (changed, skipped_empty)."""
    changed = 0
    skipped = 0
    for org in session.query(Organization).order_by(Organization.id).all():
        if not _has_quote(org.canonical_name):
            continue
        cleaned = clean_name(org.canonical_name)
        if not cleaned:
            logger.warning("org #%s %r cleans to empty — skipped", org.id, org.canonical_name)
            skipped += 1
            continue
        target = session.query(Organization).filter(
            Organization.id != org.id,
            func.lower(Organization.canonical_name) == cleaned.lower(),
        ).first()
        if target is None:
            target = session.query(Organization).join(OrganizationAlias).filter(
                Organization.id != org.id,
                OrganizationAlias.normalized_alias == normalize_alias(cleaned),
            ).first()
        if target is not None:
            logger.info(
                "org #%s %r -> merge into org #%s %r",
                org.id, org.canonical_name, target.id, target.canonical_name,
            )
            if apply:
                merge_organizations(session, org.id, target.id, make_global_alias=False)
            changed += 1
            continue
        if cleaned == org.canonical_name:
            continue  # balanced inner quotations etc. — nothing to strip
        logger.info("org #%s %r -> %r", org.id, org.canonical_name, cleaned)
        if apply:
            org.canonical_name = cleaned
        changed += 1
    return changed, skipped


def fix_organization_aliases(session, apply: bool) -> dict[str, int]:
    """Clean organization_aliases rows; returns counters by action."""
    counts = {"cleaned": 0, "deleted_redundant": 0, "deleted_duplicate": 0, "skipped_conflict": 0}
    for alias in session.query(OrganizationAlias).order_by(OrganizationAlias.id).all():
        if not _has_quote(alias.alias) and not _has_quote(alias.normalized_alias):
            continue
        cleaned = clean_name(alias.alias)
        normalized = normalize_alias(cleaned)
        own_canonical = normalize_alias(alias.organization.canonical_name)
        if not cleaned or normalized == own_canonical:
            logger.info("alias #%s %r -> delete (%s)",
                        alias.id, alias.alias, "empty" if not cleaned else "equals canonical")
            if apply:
                session.delete(alias)
            counts["deleted_redundant"] += 1
            continue
        clash_same_org = session.query(OrganizationAlias).filter(
            OrganizationAlias.normalized_alias == normalized,
            OrganizationAlias.organization_id == alias.organization_id,
            OrganizationAlias.id != alias.id,
        ).first()
        if clash_same_org is not None:
            logger.info("alias #%s %r -> delete (duplicate of #%s)",
                        alias.id, alias.alias, clash_same_org.id)
            if apply:
                session.delete(alias)
            counts["deleted_duplicate"] += 1
            continue
        clash_other_org = session.query(OrganizationAlias).filter(
            OrganizationAlias.normalized_alias == normalized,
            OrganizationAlias.organization_id != alias.organization_id,
        ).first()
        if clash_other_org is not None or any(
            normalize_alias(other.canonical_name) == normalized
            for other in session.query(Organization).all()
            if other.id != alias.organization_id
        ):
            logger.warning(
                "alias #%s %r -> cleaned %r belongs to another organization — skipped",
                alias.id, alias.alias, cleaned,
            )
            counts["skipped_conflict"] += 1
            continue
        logger.info("alias #%s %r -> %r", alias.id, alias.alias, cleaned)
        if apply:
            alias.alias = cleaned
            alias.normalized_alias = normalized
        counts["cleaned"] += 1
    return counts


def _variant_cleanup(row: DocumentEntity) -> tuple[str, list[str]] | None:
    """Cleaned (entity_text, variants) for a quote-polluted row, else None."""
    if not _has_quote(row.entity_text) and not any(
        _has_quote(value) for value in row.variants or []
    ):
        return None  # not this script's scope (e.g. duplicate-variant dedup)
    cleaned_text = clean_name(row.entity_text)
    if not cleaned_text:
        logger.warning(
            "doc #%s [%s] entity_text %r cleans to empty — skipped",
            row.document_id, row.entity_type, row.entity_text,
        )
        return None
    variants: dict[str, str] = {}
    for value in row.variants or []:
        cleaned_variant = clean_name(value)
        if cleaned_variant and cleaned_variant.casefold() != cleaned_text.casefold():
            variants.setdefault(cleaned_variant.casefold(), cleaned_variant)
    cleaned_variant_list = list(variants.values())
    if cleaned_text == row.entity_text and cleaned_variant_list == list(row.variants or []):
        return None
    return cleaned_text, cleaned_variant_list


def fix_document_entities(session, apply: bool) -> int:
    """Clean document_entities.entity_text/variants; merges converged duplicates."""
    changed = 0
    rows = (
        session.query(DocumentEntity)
        .order_by(DocumentEntity.document_id, DocumentEntity.entity_type, DocumentEntity.id)
        .all()
    )
    for row in rows:
        planned = _variant_cleanup(row)
        if planned is None:
            continue
        cleaned_text, cleaned_variants = planned
        twin = session.query(DocumentEntity).filter(
            DocumentEntity.document_id == row.document_id,
            DocumentEntity.entity_type == row.entity_type,
            DocumentEntity.id != row.id,
        ).all()
        target = next((t for t in twin if t.entity_text == cleaned_text), None)
        if target is None:
            target = next(
                (t for t in twin if t.entity_text.casefold() == cleaned_text.casefold()), None
            )
        if target is not None:
            logger.info(
                "doc #%s [%s] %r -> merge into existing %r",
                row.document_id, row.entity_type, row.entity_text, target.entity_text,
            )
            if apply:
                # merge_document_entities() folds the dirty source text/variants
                # into target.variants — overwrite with the precomputed clean set.
                final_variants: dict[str, str] = {}
                for value in [*(target.variants or []), *cleaned_variants]:
                    value = clean_name(value)
                    if value and value.casefold() != target.entity_text.casefold():
                        final_variants.setdefault(value.casefold(), value)
                for link in session.query(DocumentOrganization).filter(
                    DocumentOrganization.document_entity_id == row.id
                ).all():
                    link.document_entity_id = target.id
                merge_document_entities(row, target, target_source="ner")
                target.variants = list(final_variants.values())
                session.delete(row)
            changed += 1
            continue
        logger.info(
            "doc #%s [%s] %r -> %r%s",
            row.document_id, row.entity_type, row.entity_text, cleaned_text,
            f" (variants: {cleaned_variants})" if cleaned_variants else "",
        )
        if apply:
            row.entity_text = cleaned_text
            row.variants = cleaned_variants
        changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Strip stray quotation marks from stored NER entity names."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        org_changed, org_skipped = fix_organizations(session, args.apply)
        alias_counts = fix_organization_aliases(session, args.apply)
        entity_changed = fix_document_entities(session, args.apply)

        if args.apply:
            session.commit()
            logger.info(
                "Done. organizations: %d changed (%d skipped), aliases: %s, document_entities: %d rows.",
                org_changed, org_skipped, alias_counts, entity_changed,
            )
        else:
            logger.info(
                "Dry-run: organizations %d (%d skipped), aliases %s, document_entities %d rows."
                " Re-run with --apply to save.",
                org_changed, org_skipped, alias_counts, entity_changed,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
