#!/usr/bin/env python3
"""One-off registry repair for the ambiguous institution names "Kongres" and "Senat" (dry-run by default).

Reviewed on the NAS database on 2026-11-05 (doc #11237, the Polish/US Senate and the US Congress split over
four lemma-named organizations). What it does, each step idempotent:

1. Folds the lemma duplicates of the US Congress (#44 "Kongresu", #54 "kongres Stanów Zjednoczone",
   #1370 "Kongres Kongres") into #55 and renames #55 "Kongres Stanów Zjednoczone".
2. Moves the Polish documents that mention "Senat" (#9360, #11178) from #46 to a new organization
   "Senat Rzeczypospolitej Polskiej", then renames #46 "Senat Stanów Zjednoczonych".
3. Drops the bare inflected forms (Kongres, Kongresu, Senat, Senatu, ...) from the GLOBAL aliases, where they would
   resolve every document to the US body, and registers them as AMBIGUOUS aliases (`organization_ambiguous_aliases`)
   of every candidate meaning, with a context hint for the resolver (`entity_service`, ambiguous alias + LLM step).

Run from backend/ (see imports/CLAUDE.md for the NAS connection recipe), dry-run first:
    python -X utf8 imports/fix_ambiguous_institution_orgs.py            # everything is executed, then rolled back
    python -X utf8 imports/fix_ambiguous_institution_orgs.py --apply
"""

import argparse
import logging

from sqlalchemy import select

from library.db.models import (
    DocumentEntity,
    DocumentOrganization,
    Organization,
    OrganizationAlias,
    OrganizationAmbiguousAlias,
)
from library.organization_registry import normalize_alias
from library.organization_source_sync import merge_organizations, rename_organization

log = logging.getLogger("fix_ambiguous_institution_orgs")

US_CONGRESS_ID, US_CONGRESS_NAME = 55, "Kongres Stanów Zjednoczonych"
CONGRESS_DUPLICATES = {44: "Kongresu", 54: "kongres Stanów Zjednoczone", 1370: "Kongres Kongres"}
INDIAN_CONGRESS_ID, INDIAN_CONGRESS_NAME = 1083, "Indyjski Kongres Narodowy"
US_SENATE_ID, US_SENATE_NAME = 46, "Senat Stanów Zjednoczonych"
POLISH_SENATE_NAME = "Senat Rzeczypospolitej Polskiej"
POLISH_SENATE_DOCUMENTS = (9360, 11178)

DESCRIPTIONS = {
    US_CONGRESS_NAME: "Kongres Stanów Zjednoczonych to dwuizbowy parlament federalny USA, składający się z Senatu "
                      "i Izby Reprezentantów.",
    US_SENATE_NAME: "Senat Stanów Zjednoczonych to izba wyższa Kongresu USA: po dwóch senatorów z każdego stanu, "
                    "zatwierdza m.in. nominacje prezydenta.",
    POLISH_SENATE_NAME: "Senat Rzeczypospolitej Polskiej to izba wyższa polskiego parlamentu, obok Sejmu.",
    INDIAN_CONGRESS_NAME: "Indyjski Kongres Narodowy to partia polityczna w Indiach, główna siła opozycji "
                          "wobec rządu Narendry Modiego.",
}

# Inflected forms of the two bare names. They stay recognisable, but only as ambiguous aliases.
KONGRES_FORMS = ("Kongres", "Kongresu", "Kongresie", "Kongresem", "Kongresowi")
SENAT_FORMS = ("Senat", "Senatu", "Senacie", "Senatem", "Senatowi")
BARE_ALIAS_KEYS = {normalize_alias(form) for form in (*KONGRES_FORMS, *SENAT_FORMS)}

HINTS = {
    US_CONGRESS_NAME: "USA; Izba Reprezentantów, Senat, Waszyngton, Trump, rezolucje wojenne, midterms, ustawy federalne.",
    INDIAN_CONGRESS_NAME: "Indie; partia opozycyjna, Rahul Gandhi, Modi, Delhi, wybory w Indiach.",
    US_SENATE_NAME: "USA; senatorowie stanowi, Kongres, Izba Reprezentantów, Waszyngton, nominacje Trumpa, wybory do Senatu.",
    POLISH_SENATE_NAME: "Polska (autor czasem pisze Bulandia); Sejm, prezydent RP, polskie ustawy, PiS, KO, Warszawa.",
}


def _organization(session, org_id: int, expected_names: tuple[str, ...]) -> Organization | None:
    org = session.get(Organization, org_id)
    if org is not None and org.canonical_name not in expected_names:
        raise SystemExit(f"Organization #{org_id} is {org.canonical_name!r}, expected one of {expected_names}: "
                         "the registry changed, review the script before running it.")
    return org


def fold_congress_duplicates(session) -> None:
    for duplicate_id, expected in CONGRESS_DUPLICATES.items():
        if _organization(session, duplicate_id, (expected,)) is None:
            continue
        # make_global_alias=False: the bare "Kongresu"/"Kongres Kongres" must not become an alias again.
        log.info("merge #%s %r -> #%s: %s", duplicate_id, expected, US_CONGRESS_ID,
                 merge_organizations(session, duplicate_id, US_CONGRESS_ID, make_global_alias=False))


def move_polish_senate(session) -> Organization:
    polish = session.scalar(select(Organization).where(Organization.canonical_name == POLISH_SENATE_NAME))
    if polish is None:
        polish = Organization(canonical_name=POLISH_SENATE_NAME)
        session.add(polish)
        session.flush()
        log.info("created %r (#%s)", POLISH_SENATE_NAME, polish.id)
    links = session.scalars(select(DocumentOrganization).where(
        DocumentOrganization.organization_id == US_SENATE_ID,
        DocumentOrganization.document_id.in_(POLISH_SENATE_DOCUMENTS),
    )).all()
    for link in links:
        entity = session.get(DocumentEntity, link.document_entity_id) if link.document_entity_id else None
        link.organization_id = polish.id
        if entity is not None:
            variants = dict.fromkeys(entity.variants or [])
            variants.setdefault(entity.entity_text)
            entity.variants = list(variants)
            entity.entity_text = POLISH_SENATE_NAME
        log.info("doc #%s: Senat -> %s", link.document_id, POLISH_SENATE_NAME)
    session.flush()
    return polish


def rename_and_describe(session, organization: Organization, new_name: str) -> None:
    if organization.canonical_name != new_name:
        log.info("rename #%s %r -> %r: %s", organization.id, organization.canonical_name, new_name,
                 rename_organization(session, organization, new_name))
    if not organization.description:
        organization.description = DESCRIPTIONS[new_name]
    session.flush()


def drop_bare_global_aliases(session, organization_ids: list[int]) -> None:
    rows = session.scalars(select(OrganizationAlias).where(
        OrganizationAlias.organization_id.in_(organization_ids),
        OrganizationAlias.normalized_alias.in_(BARE_ALIAS_KEYS),
    )).all()
    for row in rows:
        log.info("drop global alias %r of #%s", row.alias, row.organization_id)
        session.delete(row)
    session.flush()


def seed_ambiguous_aliases(session, forms: tuple[str, ...], organizations: list[Organization]) -> None:
    for organization in organizations:
        for form in forms:
            exists = session.scalar(select(OrganizationAmbiguousAlias.id).where(
                OrganizationAmbiguousAlias.organization_id == organization.id,
                OrganizationAmbiguousAlias.normalized_alias == normalize_alias(form),
            ))
            if exists is not None:
                continue
            session.add(OrganizationAmbiguousAlias(
                organization_id=organization.id, alias=form, normalized_alias=normalize_alias(form),
                context_hint=HINTS[organization.canonical_name], language="pl",
                status="approved", created_by="manual",
            ))
            log.info("ambiguous alias %r -> #%s %s", form, organization.id, organization.canonical_name)
    session.flush()


def repair(session) -> None:
    us_congress = _organization(session, US_CONGRESS_ID, ("Kongresie", US_CONGRESS_NAME))
    us_senate = _organization(session, US_SENATE_ID, ("senat", US_SENATE_NAME))
    indian = _organization(session, INDIAN_CONGRESS_ID, ("Indyjskiego Kongresu Narodowego", INDIAN_CONGRESS_NAME))
    if us_congress is None or us_senate is None or indian is None:
        raise SystemExit("A core organization is missing; nothing to do or the registry changed.")

    fold_congress_duplicates(session)
    polish_senate = move_polish_senate(session)
    rename_and_describe(session, us_congress, US_CONGRESS_NAME)
    rename_and_describe(session, us_senate, US_SENATE_NAME)
    rename_and_describe(session, indian, INDIAN_CONGRESS_NAME)
    rename_and_describe(session, polish_senate, POLISH_SENATE_NAME)
    # Renames re-add the old lemma names as aliases, so drop the bare forms last.
    drop_bare_global_aliases(session, [us_congress.id, us_senate.id, indian.id, polish_senate.id])
    seed_ambiguous_aliases(session, KONGRES_FORMS, [us_congress, indian])
    seed_ambiguous_aliases(session, SENAT_FORMS, [us_senate, polish_senate])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Execute everything and roll back (default)")
    mode.add_argument("--apply", action="store_true", help="Commit the changes")
    args = parser.parse_args()

    from library.config_loader import load_config
    load_config()
    from library.db.engine import get_session

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = get_session()
    try:
        repair(session)
        if args.apply:
            session.commit()
            log.info("Applied.")
        else:
            session.rollback()
            log.info("Dry-run: all changes rolled back.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
