#!/usr/bin/env python3
"""One-off backfill: LLM-generated short descriptions for organizations in the
global registry (Organization.description) that don't have one yet. Shown as
a tooltip (and an ℹ️ marker) on organization chips in the reader
(EntitiesPanel.tsx / read.tsx) — e.g. "EDF — francuski operator energetyczny".

Skips an organization instead of storing a guess when the model isn't
confident (empty/"NIEZNANA" response) — a wrong description shown to every
future reader of every document mentioning that organization is worse than no
tooltip at all. Re-run later (after adding aliases, or once the org has more
document context) to retry skipped ones.

Usage:
    cd backend
    .venv/Scripts/python imports/organization_descriptions_backfill.py            # dry-run (default)
    .venv/Scripts/python imports/organization_descriptions_backfill.py --apply
    .venv/Scripts/python imports/organization_descriptions_backfill.py --apply --limit 20
    .venv/Scripts/python imports/organization_descriptions_backfill.py --apply --id 534
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.db.engine import get_session  # noqa: E402
from library.db.models import Organization  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Bielik-11B-v3.0-Instruct"
NO_ANSWER = "NIEZNANA"


def _model() -> str:
    """Model LLM — z configa (TAGGING_MODEL, ten sam co article_tagging.py) lub domyślny Bielik."""
    return load_config().get("TAGGING_MODEL") or DEFAULT_MODEL


def describe_organization(canonical_name: str, aliases: list[str]) -> str | None:
    """One short Polish sentence describing the organization, or None when the
    model isn't confident enough to avoid guessing (ambiguous/unknown name)."""
    from library.ai import ai_ask

    alias_hint = f" (znana też jako: {', '.join(aliases)})" if aliases else ""
    prompt = (
        "Podaj JEDNO krótkie, rzeczowe zdanie po polsku wyjaśniające, czym jest poniższa "
        f"organizacja, instytucja lub marka{alias_hint}. Bez wstępu, bez cudzysłowów.\n"
        f"Jeśli nie jesteś pewien, co to za organizacja, odpowiedz dokładnie: {NO_ANSWER}\n\n"
        f"Nazwa: {canonical_name}"
    )
    try:
        response = ai_ask(
            prompt, model=_model(), temperature=0.0, max_token_count=120,
            operation="organization_description_backfill",
        )
    except Exception as exc:
        logger.warning("LLM call failed for %r: %s", canonical_name, exc)
        return None
    text = (response.response_text or "").strip().strip('"')
    if not text or NO_ANSWER in text.upper():
        return None
    return text


def main():
    parser = argparse.ArgumentParser(description="Backfill Organization.description via LLM (one-off).")
    parser.add_argument("--apply", action="store_true", help="Write changes to the database (default: dry-run)")
    parser.add_argument("--id", type=int, help="Process a single organization by id")
    parser.add_argument("--limit", type=int, help="Max number of organizations to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    session = get_session()
    try:
        query = session.query(Organization).filter(Organization.description.is_(None))
        if args.id is not None:
            query = query.filter(Organization.id == args.id)
        query = query.order_by(Organization.canonical_name)
        organizations = query.all()
        if args.limit:
            organizations = organizations[: args.limit]

        logger.info("%d organization(s) without a description to process", len(organizations))

        updated = skipped = 0
        for organization in organizations:
            aliases = [a.alias for a in organization.aliases]
            description = describe_organization(organization.canonical_name, aliases)
            if description is None:
                logger.info("SKIP  #%s %s — model not confident enough", organization.id, organization.canonical_name)
                skipped += 1
                continue
            logger.info("  OK  #%s %s -> %s", organization.id, organization.canonical_name, description)
            updated += 1
            if args.apply:
                organization.description = description

        if args.apply:
            session.commit()
            logger.info("Done. Updated %d organization(s), skipped %d.", updated, skipped)
        else:
            logger.info(
                "Dry-run: %d would be updated, %d skipped. Re-run with --apply to save.",
                updated, skipped,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
