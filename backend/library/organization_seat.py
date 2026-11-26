"""Fill an organization's seat from an official register: "siedziba w: Polska" and, for KRS companies, the address.

A Polish NIP alone proves nothing (foreign firms register for VAT too), so only a KRS entry that is not a foreign
branch, or a CEIDG entry, counts. Existing data is never overwritten. The address is taken only from KRS: a sole
proprietor's address is often a home address.
"""

import logging

from library.company_registry_service import normalize_name
from library.organization_location import add_country, geocode_headquarters, list_countries

logger = logging.getLogger(__name__)

POLAND = "polska"
STREET_PREFIXES = {"UL.": "ul.", "AL.": "al.", "PL.": "pl.", "OS.": "os."}

MESSAGES = {
    "name_mismatch": "Nazwa w rejestrze nie pasuje do organizacji, więc siedziby nie uzupełniono.",
    "foreign": "KRS opisuje oddział lub podmiot zagraniczny, więc siedziby w Polsce nie dodano.",
    "other_seat": "Organizacja ma już siedzibę w innym kraju. Sprawdź rozbieżność; nic nie zmieniono.",
    "vat_only": "Sam NIP nie przesądza o siedzibie w Polsce. Dodaj kraj ręcznie, jeśli to właściwe.",
}


def format_address(address):
    """"ul. Filtrowa 63/43, 02-056 Warszawa" from the upper-case KRS fields; None without a locality."""
    address = address or {}
    city = (address.get("city") or "").strip().title()
    if not city:
        return None
    words = (address.get("street") or "").split()
    street = " ".join(STREET_PREFIXES.get(word.upper(), word.title()) for word in words)
    number = (address.get("house") or "").strip()
    flat = (address.get("flat") or "").strip()
    if number and flat:
        number = f"{number}/{flat}"
    first = " ".join(part for part in (street or city, number) if part)
    locality = " ".join(part for part in ((address.get("postal_code") or "").strip(), city) if part)
    return f"{first}, {locality}" if street or number else locality


def _outcome(reason=None, country_added=False, address_added=None):
    return {"country_added": country_added, "address_added": address_added, "message": MESSAGES.get(reason)}


def apply_seat(session, organization, result, own_names=None):
    """Apply the seat evidence of one registry check; never commits.

    ``own_names`` (normalized names and aliases) guards the automatic path: the registry name must be one of
    them. ``None`` means the user picked the organization for this company, so no name check is needed.
    """
    krs = result.get("krs") or {}
    ceidg = result.get("ceidg") or {}
    address = None
    if krs.get("status") == "ok":
        seat = krs.get("address") or {}
        if "ZAGRANICZN" in (krs.get("legal_form") or "").upper() or (
                seat.get("country") or "POLSKA").upper() != "POLSKA":
            return _outcome("foreign")
        name, source, address = krs.get("name"), "KRS", format_address(seat)
    elif ceidg.get("status") == "ok" and ceidg.get("company"):
        name, source = ceidg["company"].get("name"), "CEIDG"
    else:
        return _outcome("vat_only" if (result.get("vat") or {}).get("status") == "ok" else None)

    if own_names is not None and normalize_name(name or "") not in own_names:
        return _outcome("name_mismatch")

    seats = {row["country_slug"] for row in list_countries(session, organization.id) if row["relation"] == "based_in"}
    if seats - {POLAND}:
        return _outcome("other_seat")
    country_added = False
    if POLAND not in seats:
        _, country_added = add_country(session, organization.id, POLAND, "based_in", f"Z rejestru {source}")

    address_added = None
    if address and not organization.headquarters_address and organization.latitude is None \
            and organization.longitude is None:
        organization.headquarters_address = address_added = address
        try:
            with session.begin_nested():
                geocode_headquarters(session, organization)
        except Exception:
            # The address stays; the map point can be geocoded later by saving the organization.
            logger.exception("Geocoding a registry address failed")
    return _outcome(country_added=country_added, address_added=address_added)
