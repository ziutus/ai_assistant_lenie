"""VAT white list and privacy-safe projections of sole proprietor data."""

import re
from datetime import date

import requests

from library.company_registry_client import TIMEOUT, redact
from library.external_service_events import observed_request

VAT_URL = "https://wl-api.mf.gov.pl/api/search/nip"
CEIDG_URL = "https://dane.biznes.gov.pl/api/ceidg/v3/firma"
LIMIT_MESSAGE = "Nie udało się pobrać danych VAT; mógł zostać przekroczony dzienny limit zapytań."


class VatLookupError(ValueError):
    pass


def safe_text(value):
    # Never stringify a nested object: it could contain private fields.
    return redact(value).strip() if isinstance(value, str) else ""


def postal_city(value):
    text = safe_text(value)
    match = re.search(r"\b[0-9]{2}-[0-9]{3}\s+([^,;\n]+)", text)
    if not match:
        return ""
    city = re.split(r"\s+(?:ul\.?|ulica|al\.?|aleja|pl\.?|plac)\s", match[1], maxsplit=1, flags=re.I)[0].strip()
    # Ambiguous addresses are omitted instead of risking disclosure of a street.
    if not city or not all(c.isalpha() or c in " -'’" for c in city):
        return ""
    return f"{match[0][:6]} {city}"


def parse_vat(subject):
    if subject is None:
        return None
    if not isinstance(subject, dict):
        raise VatLookupError(LIMIT_MESSAGE)
    result = {key: safe_text(subject.get(key)) for key in (
        "name", "nip", "statusVat", "regon", "krs", "registrationLegalDate", "removalDate")}
    has_krs = bool(re.fullmatch(r"[0-9]{1,10}", result["krs"]))
    for key in ("residenceAddress", "workingAddress"):
        result[key] = safe_text(subject.get(key)) if has_krs else postal_city(subject.get(key))
    return result


def get_vat(nip):
    response = observed_request(
        service="vat_whitelist", operation="search_nip",
        request_fn=lambda: requests.get(f"{VAT_URL}/{nip}", params={"date": date.today().isoformat()}, timeout=TIMEOUT),
    )
    if response.status_code == 429:
        raise VatLookupError(LIMIT_MESSAGE)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "error" in payload or "code" in payload:
        raise VatLookupError(LIMIT_MESSAGE)
    result = payload.get("result")
    if not isinstance(result, dict) or "subject" not in result:
        raise VatLookupError(LIMIT_MESSAGE)
    return parse_vat(result["subject"])


def parse_ceidg(company):
    result = {target: safe_text(company.get(source)) for source, target in (
        ("nazwa", "name"), ("status", "status"), ("dataRozpoczecia", "start_date"),
        ("dataZawieszenia", "suspension_date"), ("dataWykreslenia", "removal_date"))}
    address = company.get("adresDzialalnosci")
    address = address if isinstance(address, dict) else {}
    result.update(city=safe_text(address.get("miasto")), postal_code=safe_text(address.get("kod")))
    return result
