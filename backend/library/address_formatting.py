"""Canonical address text and conservative, offline legacy-text parsing.

No ORM dependency: migrations can use these helpers too. Interactive parsing
uses Bielik instead; these rules deliberately recognize only simple addresses.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

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
