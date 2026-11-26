"""Company-only registry evidence and read-time organization resolution. Callers commit."""

from datetime import date, datetime, timezone

from sqlalchemy import select

from library.company_registry_service import normalize_name
from library.db.models import Organization, OrganizationAlias, OrganizationIdentifier, OrganizationRelation
from library.organization_identifiers import normalize_identifier


def name_candidates(session, names):
    """Shared registry normalization, including aliases and legal forms."""
    ids = set()
    if names:
        for id_column, name_column in ((Organization.id, Organization.canonical_name),
                                       (OrganizationAlias.organization_id, OrganizationAlias.alias)):
            for org_id, name in session.execute(select(id_column, name_column).execution_options(yield_per=500)):
                if normalize_name(name) in names:
                    ids.add(org_id)
    return ids


def record_company_shareholders(session, organization, result, own_names=None):
    outcome = {"added": 0, "updated": 0, "message": None}
    krs = result.get("krs") or {}
    if krs.get("status") != "ok":
        return outcome
    if own_names is not None and normalize_name(krs.get("name") or "") not in own_names:
        outcome["message"] = "Nazwa w rejestrze nie pasuje do organizacji, więc wspólników nie zapisano."
        return outcome
    subjects = [s for s in krs.get("current_shareholders", []) + krs.get("former_shareholders", [])
                if s.get("is_company") and normalize_name(s.get("name") or "")]
    if not subjects:
        return outcome
    # Serialize concurrent checks/imports for the same organization.
    session.execute(select(Organization.id).where(Organization.id == organization.id).with_for_update())
    checked = datetime.fromisoformat(result["checked_at"]) if result.get("checked_at") else datetime.now(timezone.utc)
    checked = checked.astimezone(timezone.utc).replace(tzinfo=None) if checked.tzinfo else checked
    for subject in subjects:
        try:
            number = normalize_identifier("PL", "krs", subject.get("krs"))[2]
        except ValueError:
            number = None
        key = number or normalize_name(subject["name"])
        start = date.fromisoformat(subject["added_at"]) if subject.get("added_at") else None
        end = date.fromisoformat(subject["removed_at"]) if subject.get("removed_at") else None
        row = session.scalar(select(OrganizationRelation).where(
            OrganizationRelation.organization_id == organization.id, OrganizationRelation.role == "shareholder",
            OrganizationRelation.source == "krs", OrganizationRelation.subject_key == key,
            OrganizationRelation.valid_from == start))
        if row is None:
            row = OrganizationRelation(organization_id=organization.id, subject_key=key, valid_from=start,
                                       role="shareholder", source="krs")
            session.add(row)
            outcome["added"] += 1
        elif row.checked_at and row.checked_at > checked:
            continue
        else:
            outcome["updated"] += 1
        row.subject_name, row.subject_krs = subject["name"], number
        row.details, row.valid_to = subject.get("shares"), end
        row.source_url = krs.get("source_url") or result.get("source_urls", {}).get("krs")
        row.checked_at = checked
        session.flush()
    return outcome


def _resolution(session):
    owners = dict(session.execute(select(OrganizationIdentifier.value, OrganizationIdentifier.organization_id).where(
        OrganizationIdentifier.country_code == "PL", OrganizationIdentifier.identifier_type == "krs")).all())

    def resolve(row):
        target = row.related_organization_id
        method = "manual" if target is not None else None
        if target is None and not row.link_rejected:
            target = owners.get(row.subject_krs)
            method = "krs" if target is not None else None
        if target == row.organization_id:
            return None, None
        return session.get(Organization, target) if target is not None else None, method
    return resolve


def brief(org):
    return {"id": org.id, "canonical_name": org.canonical_name} if org else None


def related_companies(session, organization_id):
    resolve = _resolution(session)
    shareholders, holdings = [], []
    rows = session.scalars(select(OrganizationRelation).where(OrganizationRelation.person_id.is_(None)).order_by(
        OrganizationRelation.valid_to.is_not(None), OrganizationRelation.valid_from.desc(), OrganizationRelation.id)).all()
    for row in rows:
        target, method = resolve(row)
        own = row.organization_id == organization_id
        if not own and (target is None or target.id != organization_id):
            continue
        item = {field: getattr(row, field) for field in
                ("id", "organization_id", "subject_name", "subject_krs", "role", "details", "source", "source_url")}
        item.update({field: getattr(row, field).isoformat() if getattr(row, field) else None
                     for field in ("valid_from", "valid_to", "checked_at")})
        item.update(organization=brief(target), link_method=method, name_candidates=[])
        if own and target is None:
            item["name_candidates"] = [brief(session.get(Organization, candidate)) for candidate in
                                       sorted(name_candidates(session, {normalize_name(row.subject_name)}) - {organization_id})]
        if not own:
            item["holding_organization"] = brief(session.get(Organization, row.organization_id))
        (shareholders if own else holdings).append(item)
    return {"shareholders": shareholders, "holdings": holdings}


def absorb_relations(session, source_id, target_id):
    """Target manual decisions win collisions; retain the newest registry evidence."""
    rows = session.scalars(select(OrganizationRelation).order_by(OrganizationRelation.organization_id == source_id)).all()
    existing = {}
    moved = []
    with session.no_autoflush:
        for row in rows:
            if row.related_organization_id == source_id:
                row.related_organization_id = target_id
            owner = target_id if row.organization_id == source_id else row.organization_id
            key = (owner, row.role, row.source, row.subject_key, row.valid_from)
            if row.related_organization_id == owner:
                session.delete(row)
            elif key in existing:
                survivor = existing[key]
                if row.checked_at > survivor.checked_at:
                    for field in ("subject_name", "subject_krs", "details", "valid_to", "source_url", "checked_at"):
                        setattr(survivor, field, getattr(row, field))
                session.delete(row)
            else:
                moved.append((row, owner))
                existing[key] = row
    # Delete collisions before moving survivors (UPDATE precedes DELETE in the unit of work).
    session.flush()
    for row, owner in moved:
        row.organization_id = owner
    session.flush()
    # Identifiers have already moved; remove newly implicit self-relations too.
    owners = {n.value for n in session.scalars(select(OrganizationIdentifier).where(
        OrganizationIdentifier.organization_id == target_id, OrganizationIdentifier.country_code == "PL",
        OrganizationIdentifier.identifier_type == "krs"))}
    for row in existing.values():
        if row.organization_id == target_id and not row.related_organization_id and not row.link_rejected \
                and row.subject_krs in owners:
            session.delete(row)
    session.flush()
