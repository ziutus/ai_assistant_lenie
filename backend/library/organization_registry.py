"""Global organization registry — canonical orgName resolution (NER).

docs/organization-ner-alias-plan.md: a one-off manual merge of two orgName
spellings (e.g. "Interia"/"Interii") must apply globally — in the current
document, in already-saved documents, and on future NER runs. Deliberately
simpler than library/person_registry.py: exact-match resolution only, no
Wikidata/LLM disambiguation, no fuzzy auto-merge. A merge decision made once
(manually, via merge()) must never silently reverse itself.
"""

import logging

from sqlalchemy import func, select

from library.db.models import DocumentOrganization, Organization, OrganizationAlias
from library.ner_normalization import normalize_ner_text

logger = logging.getLogger(__name__)

CONFIDENCE_ALIAS_MATCHED = "alias_matched"
CONFIDENCE_CANONICAL_MATCHED = "canonical_matched"
CONFIDENCE_MANUAL_CONFIRMED = "manual_confirmed"
CONFIDENCE_NEEDS_REVIEW = "needs_review"


class AliasConflictError(Exception):
    """The alias already belongs to a different organization (maps to HTTP 409)."""

    def __init__(self, alias: str, existing_organization_id: int):
        super().__init__(f"alias {alias!r} already belongs to organization {existing_organization_id}")
        self.alias = alias
        self.existing_organization_id = existing_organization_id


def normalize_alias(value: str) -> str:
    """NFC + strip + casefold — no diacritic stripping, no fuzzy folding."""
    return normalize_ner_text(value).casefold()


def resolve_alias(session, name: str) -> Organization | None:
    """Exact match: first organization_aliases.normalized_alias, then canonical_name.

    No fuzzy matching, no LLM — an unresolved name simply creates a new
    Organization (see get_or_create()).
    """
    normalized = normalize_alias(name)
    if not normalized:
        return None
    alias = session.execute(
        select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized)
    ).scalars().first()
    if alias is not None:
        return alias.organization
    # canonical_name has no functional normalized index (small table, exact
    # NFC+casefold match only matters here) — compare in Python like the
    # rest of the NER pipeline (entity_service.is_excluded, filter_entities_to_text).
    for org in session.execute(select(Organization)).scalars().all():
        if normalize_alias(org.canonical_name) == normalized:
            return org
    return None


def _observe_variant(session, organization: Organization, alias: str) -> None:
    """Silently record a surface variant seen for an already-resolved organization.

    Never raises: a variant colliding with a different organization's alias is
    a sign of ambiguity the automatic pipeline must not resolve on its own, so
    it is skipped (unlike add_alias(), which is the explicit/manual path and
    does raise on conflict).
    """
    normalized = normalize_alias(alias)
    if not normalized or normalized == normalize_alias(organization.canonical_name):
        return
    existing = session.execute(
        select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized)
    ).scalars().first()
    if existing is not None:
        if existing.organization_id != organization.id:
            logger.info(
                "organization_registry: skipping ambiguous auto-alias %r (belongs to org %s, not %s)",
                alias, existing.organization_id, organization.id,
            )
        return
    session.add(OrganizationAlias(
        organization=organization, alias=alias, normalized_alias=normalized,
        alias_kind="ner_observed", created_by="ner",
    ))


def get_or_create(session, canonical_name: str, variants: list[str] | None = None) -> Organization:
    """Resolve a (already NER-group-merged) organization name to a registry row.

    Thin wrapper over resolve_or_create() for callers that don't need the
    match-confidence classification.
    """
    organization, _confidence = resolve_or_create(session, canonical_name, variants)
    return organization


def resolve_or_create(session, canonical_name: str, variants: list[str] | None = None) -> tuple[Organization, str]:
    """Like get_or_create(), but also reports how the match was made.

    Returns (organization, confidence) where confidence is
    CONFIDENCE_ALIAS_MATCHED (found via organization_aliases), or
    CONFIDENCE_CANONICAL_MATCHED (found via a direct canonical_name compare,
    or a brand-new organization whose canonical name IS this mention).
    Matched organizations get their new surface variants recorded as
    ner_observed aliases (audit/removable); a genuinely new name creates a
    fresh Organization with no aliases beyond what's passed in — canonical_name
    itself needs no alias row (resolve_alias() checks canonical_name directly).
    """
    variants = variants or []
    names_to_try = [canonical_name, *variants]
    organization: Organization | None = None
    confidence = CONFIDENCE_CANONICAL_MATCHED
    for name in names_to_try:
        normalized = normalize_alias(name)
        if not normalized:
            continue
        alias = session.execute(
            select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized)
        ).scalars().first()
        if alias is not None:
            organization = alias.organization
            confidence = CONFIDENCE_ALIAS_MATCHED
            break
    if organization is None:
        organization = resolve_alias(session, canonical_name)
        if organization is None:
            for variant in variants:
                organization = resolve_alias(session, variant)
                if organization is not None:
                    break
        confidence = CONFIDENCE_CANONICAL_MATCHED

    if organization is None:
        organization = Organization(canonical_name=canonical_name)
        session.add(organization)
        session.flush()
        for variant in variants:
            _observe_variant(session, organization, variant)
        return organization, CONFIDENCE_CANONICAL_MATCHED

    for name in names_to_try:
        _observe_variant(session, organization, name)
    return organization, confidence


def add_alias(session, organization: Organization, alias: str, *,
              alias_kind: str = "manual", created_by: str = "manual") -> OrganizationAlias:
    """Register a global alias. Idempotent for the same organization, 409-worthy otherwise."""
    normalized = normalize_alias(alias)
    existing = session.execute(
        select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized)
    ).scalars().first()
    if existing is not None:
        if existing.organization_id != organization.id:
            raise AliasConflictError(alias, existing.organization_id)
        return existing
    row = OrganizationAlias(
        organization=organization, alias=alias, normalized_alias=normalized,
        alias_kind=alias_kind, created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row


def _delete_organization_if_orphaned(session, organization_id: int) -> bool:
    """Delete the Organization row when no document_organizations links point at it."""
    remaining = session.execute(
        select(func.count()).select_from(DocumentOrganization)
        .where(DocumentOrganization.organization_id == organization_id)
    ).scalar()
    if remaining:
        return False
    organization = session.get(Organization, organization_id)
    if organization is None:
        return False
    session.delete(organization)
    return True


def merge(session, source_organization_id: int, target_organization_id: int, *,
          make_global_alias: bool = True) -> dict:
    """Merge source organization into target: re-point links, keep or drop the global alias.

    Re-points every document_organizations row from source to target (merging
    duplicates on unique(document_id, organization_id) instead of violating
    it), transfers source's aliases to target, and — when make_global_alias is
    True — registers the source's own canonical_name as a target alias so
    future NER runs resolve it automatically. Source is deleted once orphaned.
    """
    if source_organization_id == target_organization_id:
        raise ValueError("source_organization_id points at the same organization as target")

    source = session.get(Organization, source_organization_id)
    target = session.get(Organization, target_organization_id)
    if source is None or target is None:
        raise LookupError("organization not found")

    if make_global_alias:
        add_alias(session, target, source.canonical_name, alias_kind="manual", created_by="manual")

    for alias in list(source.aliases):
        normalized = alias.normalized_alias
        already_on_target = session.execute(
            select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized)
        ).scalars().first()
        if already_on_target is not None and already_on_target.organization_id == target.id:
            session.delete(alias)
        else:
            alias.organization_id = target.id

    source_links = session.execute(
        select(DocumentOrganization).where(DocumentOrganization.organization_id == source.id)
    ).scalars().all()
    for link in source_links:
        existing = session.execute(
            select(DocumentOrganization).where(
                DocumentOrganization.document_id == link.document_id,
                DocumentOrganization.organization_id == target.id,
            )
        ).scalars().first()
        if existing is not None:
            session.delete(link)
        else:
            link.organization_id = target.id
    session.flush()

    organization_deleted = _delete_organization_if_orphaned(session, source.id)
    return {
        "organization_id": target.id,
        "canonical_name": target.canonical_name,
        "source_organization_id": source.id,
        "source_organization_deleted": organization_deleted,
    }


def merge_ner_groups(org_groups: dict[str, dict]) -> dict[str, dict]:
    """Merge orgName groups from one NER extraction when they refer to the same name.

    org_groups: {entity_text: {"count": int, "variants": list[str]}}, orgName
    only. When one group's canonical name shows up as a variant of another
    group (or vice versa), they are the same organization mis-split by
    lemmatization (docs/organization-ner-alias-plan.md reference case:
    "Interia"/"Interii"). Uses union-find so three-or-more-way overlaps merge
    transitively. The surviving display name is whichever original group has
    the richer variant set (ties: higher mention count, then name) — the
    actual canonical spelling is decided later by organization_registry.get_or_create().
    """
    names = list(org_groups.keys())
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    key_to_name: dict[str, str] = {}
    for name, group in org_groups.items():
        for key in {name.casefold(), *(v.casefold() for v in group.get("variants", []))}:
            if key in key_to_name:
                union(name, key_to_name[key])
            else:
                key_to_name[key] = name

    clusters: dict[str, list[str]] = {}
    for name in names:
        clusters.setdefault(find(name), []).append(name)

    merged: dict[str, dict] = {}
    for members in clusters.values():
        def sort_key(member_name: str) -> tuple:
            group = org_groups[member_name]
            return (len(set(group.get("variants", []))), group.get("count", 0), member_name)

        canonical_member = max(members, key=sort_key)
        total_count = sum(org_groups[m].get("count", 0) for m in members)
        variant_set: dict[str, str] = {}
        for member_name in members:
            group = org_groups[member_name]
            for value in [member_name, *group.get("variants", [])]:
                variant_set.setdefault(value.casefold(), value)
        canonical_key = canonical_member.casefold()
        variant_set.pop(canonical_key, None)
        merged[canonical_member] = {"count": total_count, "variants": list(variant_set.values())}
    return merged
