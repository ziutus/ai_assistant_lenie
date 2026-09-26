"""Canonical address text and conservative, offline legacy-text parsing.

No ORM dependency: migrations can use these helpers too. Interactive parsing
uses Bielik instead; these rules deliberately recognize only simple addresses.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from unidecode import unidecode

if TYPE_CHECKING:
    from library.db.models import Address

ADDRESS_FIELD_LIMITS = {
    "street": 200, "building_number": 20, "block_number": 20, "apartment_number": 20,
    "postal_code": 10, "city": 200, "country": 100,
}


def format_address(address: Address) -> str:
    """street building[ blok block]/apartment, postal city[, non-Polska country].

    The block follows the building and precedes the apartment slash:
    "Bratysławska 15 blok 31/26, 90-001 Łódź". Without a block, the original
    format is unchanged: "Bratysławska 15/26, 90-001 Łódź".
    """
    def value(field):
        return " ".join((getattr(address, field, None) or "").split())

    line = " ".join(filter(None, (value("street"), value("building_number"))))
    if value("block_number"):
        line = " ".join(filter(None, (line, f"blok {value('block_number')}")))
    if value("apartment_number"):
        line += f"/{value('apartment_number')}"
    locality = " ".join(filter(None, (value("postal_code"), value("city"))))
    country = value("country")
    return ", ".join(filter(None, (line, locality, country if country != "Polska" else "")))


_NUMBER = r"\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?"
_TRAILING_NUMBER = re.compile(rf"(?:(.+?)\s+)?({_NUMBER})(?:\s+(?:m\.?|lok\.?)\s*(\d+[A-Za-z]?))?$")
_LEADING_NUMBER = re.compile(rf"({_NUMBER})\s+(.+)$")
_PREFIX = re.compile(r"^(?:ul\.|al\.|ulica|aleja)\s*", re.IGNORECASE)


def parse_address_text_heuristic(text: str) -> dict:
    """Extract simple Polish addresses; city=None means preserve the whole input.

    Any unconsumed segment makes the parse unsafe, even if a postal city was
    found. Returning an empty parse prevents migration/import from discarding
    that segment. A slash number is guessed to mean building/apartment; ranges
    such as 15/17 are inherently ambiguous and need human review.
    """
    empty = dict.fromkeys(ADDRESS_FIELD_LIMITS)
    result = empty.copy()
    segments = [part.strip() for part in re.split(r"[,\n]+", text) if part.strip()]
    remaining = []
    for segment in segments:
        postal = re.fullmatch(r"(\d{2}-\d{3})\s+([^\d,]+)", segment)
        if postal and result["city"] is None:
            result["postal_code"], result["city"] = postal.group(1), postal.group(2).strip()
        elif segment.casefold() in {"polska", "poland"} and result["country"] is None:
            result["country"] = segment
        else:
            remaining.append(segment)
    if len(remaining) > 1:
        return empty
    if remaining:
        segment = remaining[0]
        prefixed = bool(_PREFIX.match(segment))
        segment = _PREFIX.sub("", segment)
        match = _TRAILING_NUMBER.fullmatch(segment)
        if match:
            name, number, apartment = match.groups()
        else:
            leading = _LEADING_NUMBER.fullmatch(segment)
            if not leading:
                return empty
            number, name = leading.groups()
            apartment = None
        if "/" in number and apartment is None:
            number, apartment = number.split("/", 1)
        result["building_number"], result["apartment_number"] = number, apartment
        if name and not prefixed and (result["city"] is None or name.casefold() == result["city"].casefold()):
            result["city"] = result["city"] or name
        else:
            result["street"] = name
    if not result["city"] or any(value and len(value) > ADDRESS_FIELD_LIMITS[key] for key, value in result.items()):
        return empty
    return result


_COUNTRY_ALIASES = {"pl", "polska", "poland", "rp", "rzeczpospolita polska"}
_IDENTITY_FIELDS = ("street", "building_number", "block_number", "apartment_number", "postal_code", "city", "country")


def _field(address, name):
    value = address.get(name) if isinstance(address, dict) else getattr(address, name, None)
    return " ".join((value or "").split())


def _fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unidecode(value or "").casefold()).strip()


def address_identity(address) -> dict:
    """Comparable, accent/case/country-alias-insensitive fields of an address.

    A legacy row whose whole text sits in ``city`` (no street/number — how an
    unparsable import is stored, see imported_address_fields) is re-parsed so it
    compares equal to the same address entered field by field. Unparsable text
    is kept as-is and simply matches nothing else.
    """
    fields = {name: _field(address, name) for name in _IDENTITY_FIELDS}
    if not fields["street"] and not fields["building_number"] and re.search(r"[\n,]|\d", fields["city"]):
        raw = (address.get("city") if isinstance(address, dict) else address.city) or ""
        segments = [part.strip() for part in re.split(r"[,\n]+", raw) if part.strip()]
        kept = [part for part in segments if part.casefold() not in _COUNTRY_ALIASES]
        parsed = parse_address_text_heuristic(",".join(kept))
        if parsed["city"] is not None:
            country = fields["country"] or next((part for part in segments if part.casefold() in _COUNTRY_ALIASES), "")
            fields = {name: (parsed[name] or "") for name in _IDENTITY_FIELDS}
            fields["country"] = country
    identity = {name: _fold(value) for name, value in fields.items()}
    if identity["country"] in {_fold(alias) for alias in _COUNTRY_ALIASES} or not identity["country"]:
        identity["country"] = "pl"
    return identity


def is_specific_address(address) -> bool:
    """True when the address names a street or a building, not just a city.

    Only such addresses are worth offering for sharing between contacts: 22 unrelated contacts have just
    "Łódź", and that is not a shared place. A legacy one-line row counts once it parses into a street/number.
    """
    identity = address_identity(address)
    return bool(identity["street"] or identity["building_number"])


def addresses_match(first, second) -> bool:
    """True when two addresses point at the same place.

    Everything must be equal after folding except the postal code, which may be
    missing on either side (an address entered without one is still the same).
    """
    a, b = address_identity(first), address_identity(second)
    if not a["city"] or a["city"] != b["city"]:
        return False
    if a["postal_code"] and b["postal_code"] and a["postal_code"] != b["postal_code"]:
        return False
    return all(a[name] == b[name] for name in _IDENTITY_FIELDS if name != "postal_code")


def imported_address_fields(text: str) -> dict:
    """Use the complete original text as city when parsing is unsafe.

    Never truncate a fallback to fit VARCHAR(200): fail before losing data.
    In a migration this rolls back, leaving the original column intact.
    """
    fields = parse_address_text_heuristic(text)
    if fields["city"] is None:
        if len(text) > ADDRESS_FIELD_LIMITS["city"]:
            raise ValueError("Unparsed address exceeds city's 200 characters; split it before migrating/importing")
        fields = dict.fromkeys(ADDRESS_FIELD_LIMITS)
        fields["city"] = text
    return fields
