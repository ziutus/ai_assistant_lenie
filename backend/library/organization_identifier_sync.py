"""Store the KRS and REGON that official registers report for an organization's number.

The human decision is attaching the first number to an organization. The numbers that follow from it are
saved without another click, unless something does not fit: the registry name differs from the organization,
registers disagree, the organization already has another number of that type, or another organization owns it.
Only identifiers are stored - never beneficiaries, shareholders or any other registry content.
"""

from library import organization_identifiers as identifiers
from library.company_registry_service import check_company, normalize_name
from library.db.models import Organization

AUTO_TYPES = ("krs", "regon")

REASONS = {
    "name_mismatch": "Nazwa w rejestrze nie pasuje do nazwy ani aliasów organizacji. Dodaj ręcznie, jeśli to ta firma.",
    "sources_disagree": "Rejestry podają różne numery. Wybierz właściwy ręcznie.",
    "has_other": "Organizacja ma już inny numer tego typu. Sprawdź, który jest właściwy.",
    "owned_by_other": "Ten numer jest przypisany do innej organizacji (być może to duplikat).",
    "manual": "Ten typ numeru dodajesz ręcznie.",
}


def _registry_records(result):
    """(registry name, record with numbers) for every source that answered about the company."""
    vat = result.get("vat", {}).get("subject") or {}
    krs = result.get("krs", {})
    records = [(vat.get("name"), vat), (krs.get("name"), krs)]
    records.extend((filing.get("name"), filing) for filing in result.get("crbr", {}).get("filings", [])
                   if filing.get("is_current"))
    return records


def _normalized(kind, value):
    try:
        return identifiers.normalize_identifier("PL", kind, value)[2]
    except ValueError:
        return None


def _reason(kind, value, records, own_names, stored, nip):
    reported = {}
    for name, record in records:
        number = _normalized(kind, record.get(kind))
        if number:
            reported.setdefault(number, []).append(name)
    reported_nips = {_normalized("nip", record.get("nip")) for _, record in records} - {None}
    if len(reported) > 1 or (nip and reported_nips - {nip}):
        return "sources_disagree"
    if any(row["country_code"] == "PL" and row["identifier_type"] == kind and row["value"] != value for row in stored):
        return "has_other"
    names = reported.get(value)
    if not names or not all(name and normalize_name(name) in own_names for name in names):
        return "name_mismatch"
    return None


def check_and_store(session, organization_id):
    """Run the registry check for one organization and save the safe KRS / REGON suggestions.

    Returns the check result with ``identifier_sync.added`` and, on each remaining suggestion, why it was
    left for the human (``reason``, ``reason_message``). Queues rows without committing.
    """
    result = check_company(organization_id=organization_id)
    organization_id = result["query"]["organization_id"]
    organization = session.get(Organization, organization_id)
    own_names = {normalize_name(name) for name in
                 [organization.canonical_name, *(alias.alias for alias in organization.aliases)]} - {""}
    stored = identifiers.list_identifiers(session, organization_id)
    records = _registry_records(result)
    nip = result["query"].get("nip")

    added, remaining = [], []
    for suggestion in result.get("suggested_identifiers", []):
        kind = suggestion["identifier_type"]
        reason = "manual" if kind not in AUTO_TYPES else _reason(
            kind, suggestion["value"], records, own_names, stored, nip)
        conflict = None
        if reason is None:
            try:
                row, created = identifiers.add_identifier(session, organization_id, {
                    **suggestion, "note": "Dodane automatycznie z rejestru"})
                if created:
                    added.append(row)
                continue
            except identifiers.IdentifierConflict as exc:
                reason, conflict = "owned_by_other", exc.conflict_organization
        remaining.append({**suggestion, "reason": reason, "reason_message": REASONS[reason],
                          **({"conflict_organization": conflict} if conflict else {})})
    result["suggested_identifiers"] = remaining
    result["identifier_sync"] = {"added": added}
    return result
