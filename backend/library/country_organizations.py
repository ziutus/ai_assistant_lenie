"""Plan and apply one registry organization per country (organization_type='country').

The pure ``plan_country_organizations()`` decides, for every country of the gazetteer,
whether to create an organization, promote an existing one, or report a conflict, and
which imported ``Kraje/…/<country>.md`` note to link; ``apply_plan()`` writes it. Used by
``imports/create_country_organizations.py`` (dry-run by default).
"""

from dataclasses import dataclass, field

from unidecode import unidecode

from library.country_gazetteer import _slug_to_name_map
from library.organization_location import COUNTRY_ORGANIZATION_TYPE, add_country
from library.organization_registry import normalize_alias


@dataclass
class OrgInfo:
    id: int
    canonical_name: str
    organization_type: str | None
    aliases: list[str]
    primary_note_document_id: int | None
    country_ties: set[tuple[str, str]]  # (country_slug, relation)


@dataclass
class CountryAction:
    slug: str
    name: str
    action: str  # create | promote | conflict
    organization_id: int | None = None
    note_document_id: int | None = None
    note_issue: str | None = None  # missing | ambiguous
    needs_type: bool = False
    needs_tie: bool = True
    reason: str = ""
    details: list[str] = field(default_factory=list)


def note_index(notes: list[tuple[int, str]]) -> dict[str, list[int]]:
    """normalized file stem -> document ids, for urls like obsidian://…/Kraje/<region>/<Country>.md."""
    index: dict[str, list[int]] = {}
    for document_id, url in notes:
        stem = url.rsplit("/", 1)[-1]
        if stem.lower().endswith(".md"):
            stem = stem[:-3]
        index.setdefault(_note_key(stem), []).append(document_id)
    return index


def _note_key(name: str) -> str:
    """Case- and diacritic-insensitive key: vault file names are not always typed with Polish letters."""
    return normalize_alias(unidecode(name))


def plan_country_organizations(countries: dict[str, str], organizations: list[OrgInfo],
                               notes: list[tuple[int, str]]) -> list[CountryAction]:
    by_canonical: dict[str, list[OrgInfo]] = {}
    by_alias: dict[str, list[OrgInfo]] = {}
    for organization in organizations:
        by_canonical.setdefault(normalize_alias(organization.canonical_name), []).append(organization)
        for alias in organization.aliases:
            by_alias.setdefault(normalize_alias(alias), []).append(organization)
    notes_by_stem = note_index(notes)

    actions: list[CountryAction] = []
    claimed: dict[int, str] = {}
    for slug, name in sorted(countries.items(), key=lambda item: item[1]):
        key = normalize_alias(name)
        action = CountryAction(slug=slug, name=name, action="create")

        candidates = by_canonical.get(key) or by_alias.get(key) or []
        distinct = {o.id: o for o in candidates}
        if key not in by_canonical and len(distinct) == 1:
            # Only an alias matches: the organization may be an NER lemma of another entity
            # ("Male" with alias "Mali"), so a human renames or merges it first.
            organization = next(iter(distinct.values()))
            action.action = "conflict"
            action.organization_id = organization.id
            action.reason = (f"organization {organization.id} {organization.canonical_name!r} matches only by alias — "
                             f"rename it to {name!r} or merge it, then re-run")
        elif len(distinct) > 1:
            action.action = "conflict"
            action.reason = "several organizations match: " + ", ".join(str(i) for i in sorted(distinct))
        elif len(distinct) == 1:
            organization = next(iter(distinct.values()))
            action.organization_id = organization.id
            if organization.id in claimed:
                action.action = "conflict"
                action.reason = f"organization {organization.id} already matched {claimed[organization.id]}"
            elif organization.organization_type not in (None, "", COUNTRY_ORGANIZATION_TYPE):
                action.action = "conflict"
                action.reason = f"organization {organization.id} has type {organization.organization_type!r}"
            else:
                action.action = "promote"
                claimed[organization.id] = name
                action.needs_type = organization.organization_type != COUNTRY_ORGANIZATION_TYPE
                action.needs_tie = (slug, "based_in") not in organization.country_ties

        if action.action != "conflict":
            note_ids = notes_by_stem.get(_note_key(name), [])
            current = None
            if action.organization_id is not None:
                current = distinct[action.organization_id].primary_note_document_id
            if current is not None:
                action.details.append(f"already linked to note {current}")
            elif len(note_ids) == 1:
                action.note_document_id = note_ids[0]
            elif len(note_ids) > 1:
                action.note_issue = "ambiguous"
                action.details.append("notes: " + ", ".join(str(i) for i in note_ids))
            else:
                action.note_issue = "missing"
        actions.append(action)
    return actions


def load_organizations(session) -> list[OrgInfo]:
    from sqlalchemy import select

    from library.db.models import Organization, OrganizationCountry

    ties: dict[int, set[tuple[str, str]]] = {}
    for organization_id, slug, relation in session.execute(
        select(OrganizationCountry.organization_id, OrganizationCountry.country_slug, OrganizationCountry.relation)
    ).all():
        ties.setdefault(organization_id, set()).add((slug, relation))
    return [
        OrgInfo(
            id=o.id, canonical_name=o.canonical_name, organization_type=o.organization_type,
            aliases=[a.alias for a in o.aliases], primary_note_document_id=o.primary_note_document_id,
            country_ties=ties.get(o.id, set()),
        )
        for o in session.execute(select(Organization)).scalars().all()
    ]


def load_notes(session) -> list[tuple[int, str]]:
    from sqlalchemy import select

    from library.db.models import Document

    return list(session.execute(
        select(Document.id, Document.url).where(
            Document.document_type == "obsidian_note", Document.url.ilike("%/Kraje/%"),
        )
    ).all())


def gazetteer_countries() -> dict[str, str]:
    return dict(_slug_to_name_map())


def apply_plan(session, actions: list[CountryAction]) -> dict[str, int]:
    """Write the plan; never commits. Conflicts are skipped."""
    from library.db.models import Organization

    counts = {"created": 0, "promoted": 0, "ties": 0, "notes": 0}
    for action in actions:
        if action.action == "conflict":
            continue
        if action.action == "create":
            organization = Organization(canonical_name=action.name, organization_type=COUNTRY_ORGANIZATION_TYPE)
            session.add(organization)
            session.flush()
            counts["created"] += 1
        else:
            organization = session.get(Organization, action.organization_id)
            if action.needs_type:
                organization.organization_type = COUNTRY_ORGANIZATION_TYPE
            counts["promoted"] += 1
        if action.note_document_id is not None and organization.primary_note_document_id is None:
            organization.primary_note_document_id = action.note_document_id
            counts["notes"] += 1
        _, created = add_country(session, organization.id, action.slug, "based_in")
        counts["ties"] += int(created)
    return counts
