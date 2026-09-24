"""CEIDG (Centralna Ewidencja i Informacja o Działalności Gospodarczej) API client.

Looks up a sole proprietorship (JDG) by NIP against the official CEIDG data
warehouse ("Hurtownia Danych CEIDG i biznes.gov.pl", dane.biznes.gov.pl) —
clean JSON, no scraping. The public CEIDG search UI
(aplikacja.ceidg.gov.pl/CEIDG/CEIDG.Public.UI/SearchDetails.aspx) is an old
ASP.NET WebForms page that Lenie's webpage downloader cannot parse into
usable text (confirmed via a failed document import, ERROR_DOWNLOAD) — this
client is the supported replacement for looking up a specific, known NIP.

Auth: JWT bearer token, free registration via Profil Zaufany/mObywatel at
biznes.gov.pl (see .agents/skills/lenie-contact-ceidg-lookup/SKILL.md for the
registration steps). Config key: CEIDG_API_KEY (in Vault).

CEIDG only covers sole proprietorships. A spółka (sp. z o.o. etc.) needs KRS
instead, which this client does not query.
"""

import logging

import requests

from library.external_service_events import observed_request

logger = logging.getLogger(__name__)

FIRMA_URL = "https://dane.biznes.gov.pl/api/ceidg/v3/firma"
REQUEST_TIMEOUT_S = 15


def _api_key() -> str | None:
    from library.config_loader import load_config
    return load_config().get("CEIDG_API_KEY")


def normalize_nip(nip: str) -> str:
    """Strip everything but digits — the API expects a bare 10-digit NIP."""
    return "".join(c for c in (nip or "") if c.isdigit())


def get_company_by_nip(nip: str) -> dict | None:
    """Look up one JDG by NIP. Returns the raw first matching "firma" dict, or None.

    Returns None on: missing/invalid API key, no match (deregistered or
    never-existed NIP), or a request failure — callers treat all of these as
    "nothing to show", logging carries the distinction. Never raises for a
    normal miss; only for programmer-error inputs (e.g. non-string nip).
    """
    key = _api_key()
    if not key:
        logger.warning("CEIDG_API_KEY not configured — CEIDG lookup disabled")
        return None

    clean_nip = normalize_nip(nip)
    if not clean_nip:
        logger.warning("CEIDG lookup called with an empty/invalid NIP: %r", nip)
        return None

    try:
        resp = observed_request(
            service="ceidg", operation="firma_by_nip",
            request_fn=lambda: requests.get(
                FIRMA_URL,
                params={"nip": clean_nip},
                headers={"Authorization": f"Bearer {key}"},
                timeout=REQUEST_TIMEOUT_S,
            ),
        )
        if resp.status_code in (401, 403):
            logger.warning("CEIDG API rejected the configured token (HTTP %s)", resp.status_code)
            return None
        # 204: no match for these criteria (documented, most common "miss").
        # 404: the resource path itself doesn't exist — treated the same way
        # here since it can never happen for a valid nip query, only for a
        # wrong URL (which is itself a configuration bug, not a real miss).
        if resp.status_code in (204, 404):
            return None
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("CEIDG request failed for NIP %s: %s", clean_nip, e)
        return None
    except ValueError as e:
        logger.warning("CEIDG returned invalid JSON for NIP %s: %s", clean_nip, e)
        return None

    firma = data.get("firma") if isinstance(data, dict) else None
    if not firma:
        return None
    return firma[0]


def _format_address(addr: dict | None) -> str | None:
    """Single-line rendering of a CEIDG address dict (API v3 field names).

    Fields per the official schema: ulica, budynek, lokal, kod, miasto.
    Returns None when nothing usable is present.
    """
    if not isinstance(addr, dict):
        return None
    street = addr.get("ulica")
    house = addr.get("budynek")
    flat = addr.get("lokal")
    postal = addr.get("kod")
    city = addr.get("miasto")

    street_part = None
    if street:
        street_part = f"{street} {house}" if house else street
        if flat:
            street_part += f"/{flat}"

    postal_city = " ".join(p for p in (postal, city) if p) or None
    return ", ".join(p for p in (street_part, postal_city) if p) or None


#: CEIDG API v3 status values (firma.status) that count as an active JDG.
_ACTIVE_STATUSES = {"AKTYWNY", "OCZEKUJE_NA_ROZPOCZECIE_DZIALANOSCI", "WYLACZNIE_W_FORMIE_SPOLKI"}


def company_to_organization_fields(firma: dict) -> dict:
    """Map a raw CEIDG "firma" dict (API v3 field names) onto ContactOrganization fields.

    Only includes keys that were actually found — callers should merge this
    into an existing record rather than overwrite blindly with None.
    """
    fields: dict = {}

    name = firma.get("nazwa")
    if name:
        fields["organization_name"] = name

    business_address = _format_address(firma.get("adresDzialalnosci"))
    if business_address:
        fields["address"] = business_address

    correspondence_address = _format_address(firma.get("adresKorespondencyjny"))
    if correspondence_address:
        fields["correspondence_address"] = correspondence_address

    status = (firma.get("status") or "").upper()
    if status:
        fields["is_current"] = status in _ACTIVE_STATUSES
        if status == "ZAWIESZONY" and firma.get("dataZawieszenia"):
            fields["suspended_at"] = firma["dataZawieszenia"]
        elif status == "WYKRESLONY" and firma.get("dataWykreslenia"):
            fields["end_date"] = firma["dataWykreslenia"]

    if firma.get("dataRozpoczecia"):
        fields["start_date"] = firma["dataRozpoczecia"]

    contact_bits = []
    phone = firma.get("telefon")
    if phone:
        contact_bits.append(f"tel.: {phone}")
    email = firma.get("email")
    if email:
        contact_bits.append(f"e-mail: {email}")
    www = firma.get("www")
    if www:
        contact_bits.append(f"www: {www}")
    if contact_bits:
        fields["notes"] = ", ".join(contact_bits)

    return fields
