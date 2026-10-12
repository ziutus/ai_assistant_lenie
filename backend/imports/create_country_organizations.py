#!/usr/bin/env python3
"""Create / promote one registry organization per country and link its Obsidian note.

For each country of the gazetteer (library/country_gazetteer.py):
- an existing organization with that canonical name (or alias) is promoted to
  organization_type='country' (conflicts — another type, several candidates — are only reported);
- otherwise a new organization is created;
- a based_in tie to the country's kraj-<slug> is added;
- primary_note_document_id points at the imported Kraje/…/<Country>.md note when exactly one matches.

No aliases are generated and description stays empty (the note holds the text).

Usage:
    cd backend
    .venv/Scripts/python imports/create_country_organizations.py            # dry-run (default)
    .venv/Scripts/python imports/create_country_organizations.py --apply
"""

import argparse
import logging

from library.config_loader import load_config

cfg = load_config()  # noqa: F841 — side effect: populates os.environ for library modules

from library.country_organizations import (  # noqa: E402
    apply_plan,
    gazetteer_countries,
    load_notes,
    load_organizations,
    plan_country_organizations,
)
from library.db.engine import get_session  # noqa: E402

logger = logging.getLogger(__name__)


def _print_report(actions) -> None:
    created = [a for a in actions if a.action == "create"]
    promoted = [a for a in actions if a.action == "promote"]
    conflicts = [a for a in actions if a.action == "conflict"]
    print(f"countries: {len(actions)}  create: {len(created)}  promote: {len(promoted)}  conflict: {len(conflicts)}")
    print(f"note linked: {sum(1 for a in actions if a.note_document_id)}  "
          f"missing: {sum(1 for a in actions if a.note_issue == 'missing')}  "
          f"ambiguous: {sum(1 for a in actions if a.note_issue == 'ambiguous')}")
    for label, group in (("PROMOTE", promoted), ("CONFLICT", conflicts)):
        for action in group:
            extra = "; ".join(filter(None, [action.reason, *action.details]))
            print(f"  {label:8} {action.name} (org {action.organization_id}) {extra}")
    for action in actions:
        if action.note_issue:
            print(f"  NOTE {action.note_issue:9} {action.name} ({action.action})"
                  + (f" {'; '.join(action.details)}" if action.details else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = get_session()
    try:
        actions = plan_country_organizations(gazetteer_countries(), load_organizations(session), load_notes(session))
        _print_report(actions)
        if not args.apply:
            print("dry-run: nothing written (use --apply)")
            session.rollback()
            return 0
        counts = apply_plan(session, actions)
        session.commit()
        print(f"applied: {counts}")
        return 0
    except Exception:
        session.rollback()
        logger.exception("create_country_organizations failed")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
