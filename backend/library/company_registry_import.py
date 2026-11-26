"""Explicit, atomic import of company names and identifiers; callers commit."""

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from library import organization_identifiers as identifiers
from library import organization_registry as registry
from library.company_registry_service import normalize_name
from library.db.models import Organization, OrganizationAlias
from library.organization_identifier_sync import registry_sources, reported_numbers, sources_disagree

ERRORS = {
    "input": "Podaj dokładnie jeden poprawny NIP lub KRS.",
    "unknown": "Żaden rejestr nie potwierdził firmy.",
    "disagree": "Rejestry podają różne numery NIP. Wyjaśnij rozbieżność przed zapisem.",
    "owner": "Ten numer należy już do innej organizacji.",
    "name": "Podaj nazwę organizacji od 1 do 200 znaków.",
    "name_taken": "Ta nazwa lub alias należy już do organizacji. Wybierz inną nazwę.",
    "missing": "Nie znaleziono organizacji.",
    "other": "Organizacja ma już inny polski numer tego typu.",
    "sole": "Nazwa jednoosobowej działalności zwykle zawiera imię i nazwisko właściciela. Potwierdź zapis.",
    "failed": "Nie udało się sprawdzić rejestrów lub zapisać organizacji.",
}


class ImportError(ValueError):
    def __init__(self, code, status=400, conflict=None):
        super().__init__(code)
        self.code, self.status, self.conflict = code, status, conflict


def brief(org):
    return {"id": org.id, "canonical_name": org.canonical_name}


def suggested_name(name):
    # Keep accents and spelling; only remove the same legal forms normalize_name knows.
    name = re.sub(r"\b(spółka z ograniczoną odpowiedzialnością|sp\.?\s*z\s*o\.?\s*o\.?|"
                  r"spółka akcyjna|s\.?\s*a\.?|spółka komandytowa|sp\.?\s*k\.?)\b\.?",
                  " ", name, flags=re.I)
    name = " ".join(name.split()).strip(' ,.;"')
    return name.title() if name.isupper() else name


def name_owner(session, name):
    normalized = registry.normalize_alias(name)
    alias = session.scalar(select(OrganizationAlias).where(OrganizationAlias.normalized_alias == normalized))
    if alias:
        return session.get(Organization, alias.organization_id)
    # Canonical names have no normalized column. Stream only two columns, not ORM graphs;
    # SQL lower/unaccent is not equivalent to Python's NFC/casefold normalization.
    for org_id, canonical in session.execute(select(Organization.id, Organization.canonical_name)
                                             .execution_options(yield_per=500)):
        if registry.normalize_alias(canonical) == normalized:
            return session.get(Organization, org_id)
    return None


def match_company(session, result):
    sources = registry_sources(result)
    records = [(row.get("name"), row) for _, row in sources]
    numbers, disagreeing = [], []
    for kind in ("nip", "krs", "regon"):
        reported = reported_numbers(records, kind)
        queried = result["query"].get(kind)
        if sources_disagree(records, kind, queried):
            disagreeing.append(kind)
        elif reported:
            value = next(iter(reported))
            source = next(source for source, row in sources
                          if value in reported_numbers([(row.get("name"), row)], kind))
            numbers.append({"country_code": "PL", "identifier_type": kind, "value": value,
                            "source_url": result.get("source_urls", {}).get(source)})
    owners = {}
    searched = numbers + [{"country_code": "PL", "identifier_type": kind, "value": value}
                          for kind in ("nip", "krs") if (value := result["query"].get(kind))]
    for number in searched:
        owner = identifiers.find_owner(session, number)
        if owner:
            item = owners.setdefault(owner.id, {**brief(owner), "identifiers": []})
            if not any(n["identifier_type"] == number["identifier_type"] and n["value"] == number["value"]
                       for n in item["identifiers"]):
                item["identifiers"].append(number)
    names = {normalize_name(name) for name, _ in records if name} - {""}
    candidate_ids = set()
    # No persisted registry-normalized name exists. Stream scalar names, and load only
    # matching organizations. A LIKE prefilter would miss diacritics/punctuation variants.
    if names:
        for model, id_column, name_column in ((Organization, Organization.id, Organization.canonical_name),
                                               (OrganizationAlias, OrganizationAlias.organization_id, OrganizationAlias.alias)):
            for org_id, name in session.execute(select(id_column, name_column).select_from(model)
                                                .execution_options(yield_per=500)):
                if org_id not in owners and normalize_name(name) in names:
                    candidate_ids.add(org_id)
    candidates = []
    for org_id in sorted(candidate_ids):
        org = session.get(Organization, org_id)
        candidates.append({**brief(org), "organization_type": org.organization_type,
                           "identifiers": [n for n in identifiers.list_identifiers(session, org_id)
                                           if n["country_code"] == "PL"]})
    legal = next((row["name"] for preferred in ("krs", "vat", "crbr", "ceidg")
                  for source, row in sources if source == preferred and row.get("name")), "")
    return {"identifiers": numbers, "disagreeing": disagreeing, "owners": list(owners.values()),
            "name_candidates": candidates, "registry_name": legal, "suggested_name": suggested_name(legal),
            "sole_proprietor": not bool(reported_numbers(records, "krs"))}


def store_company(session, result, data):
    match = match_company(session, result)
    if not match["registry_name"]:
        raise ImportError("unknown")
    if "nip" in match["disagreeing"]:
        raise ImportError("disagree", 409)
    org_id = data.get("organization_id")
    org = None
    if org_id is not None:
        if type(org_id) is not int or org_id <= 0:
            raise ImportError("input")
        # Serialize imports into the same organization (including initially empty identifiers).
        org = session.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
        if org is None:
            raise ImportError("missing", 404)
    for owner in match["owners"]:
        if owner["id"] != org_id:
            raise ImportError("owner", 409, {k: owner[k] for k in ("id", "canonical_name")})
    if match["sole_proprietor"] and data.get("confirm_sole_proprietor") is not True:
        raise ImportError("sole")
    created = org is None
    if created:
        name = data.get("canonical_name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
            raise ImportError("name")
        name = name.strip()
        owner = name_owner(session, name)
        if owner:
            raise ImportError("name_taken", 409, brief(owner))
        org = Organization(canonical_name=name, organization_type="firma")
        session.add(org)
        session.flush()
        # Also reserves the name through the alias unique constraint for concurrent imports.
        registry.add_alias(session, org, name)
    stored = identifiers.list_identifiers(session, org.id)
    for number in match["identifiers"]:
        if any(n["country_code"] == "PL" and n["identifier_type"] == number["identifier_type"]
               and n["value"] != number["value"] for n in stored):
            raise ImportError("other", 409)
    saved = [identifiers.add_identifier(session, org.id, {**number, "note": "Dodane z rejestru"})[0]
             for number in match["identifiers"]]
    warnings = []
    legal = match["registry_name"]
    owner = name_owner(session, legal)
    if owner and owner.id != org.id:
        warnings.append("Pełna nazwa jest już nazwą lub aliasem innej organizacji; aliasu nie dodano.")
    else:
        try:
            with session.begin_nested():
                registry.add_alias(session, org, legal)
        except (registry.AliasConflictError, IntegrityError):
            owner = name_owner(session, legal)
            if not owner or owner.id == org.id:
                raise
            warnings.append("Pełna nazwa jest już aliasem innej organizacji; aliasu nie dodano.")
    return {"organization": brief(org), "created": created, "identifiers": saved, "warnings": warnings}
