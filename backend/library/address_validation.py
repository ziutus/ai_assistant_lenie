"""On-demand verification of registered Polish addresses, independent of geocoding."""

import datetime
import math

from library import address_validation_client
from library.address_formatting import format_address
from library.db.models import Address


def _normalized(value: str | None) -> str:
    return "".join((value or "").split()).casefold()


def validate_address(session, address: Address) -> dict:
    """Return the REST result and update verified_at only for a real answer.

    outcome is confirmed, not_found or unavailable. official_postal_code and
    score are nullable registry values for a confirmed match. postal_code_matches
    is a whitespace/case-insensitive comparison, or None if either code is absent
    or the address is not confirmed. Unavailable leaves verified_at untouched.
    A different/missing building number is inconclusive, never proof of the
    requested house's existence. No coordinates are changed and no commit occurs;
    session is accepted to mirror geocode_address's calling convention.
    """
    result = {
        "outcome": "unavailable", "official_postal_code": None,
        "postal_code_matches": None, "score": None,
    }
    hit = address_validation_client.validate_address_external(format_address(address))
    if hit is None:
        return result
    if hit["outcome"] == "confirmed":
        match = hit["match"]
        building = match.get("nr_budynku")
        if (not isinstance(building, str) or not _normalized(building)
                or _normalized(building) != _normalized(address.building_number)):
            return result
        postal_code = match.get("kod_pocztowy")
        if isinstance(postal_code, str) and postal_code.strip():
            result["official_postal_code"] = postal_code.strip()
            if _normalized(address.postal_code):
                result["postal_code_matches"] = _normalized(postal_code) == _normalized(address.postal_code)
        score = match.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score):
            result["score"] = float(score)
    result["outcome"] = hit["outcome"]
    address.verified_at = datetime.datetime.now()
    return result
