"""Shared year coercion for untrusted LLM/JSON input (search-rebuild plan, stage 5).

Extracted out of time_periods.py's local ``_coerce_year`` so the search
subject_period fields (library/search/temporal.py) and the document
time-period classifier (library/time_periods.py) share one implementation
of "turn a raw JSON value into a plausible year, BCE as negative, or None".
Each caller supplies its own domain bounds — the two features are not
required to agree on how far back or forward a year may plausibly be.
"""

import re

_YEAR_STRING_RE = re.compile(r"-?\d{1,5}")


def coerce_year(value, *, minimum: int, maximum: int) -> int | None:
    """Coerce ``value`` to an int within [minimum, maximum], or None.

    Accepts a real int or a digit string (optionally negative — BCE years
    are negative by convention). Never raises: this reads untrusted model
    output, so anything else (bool, float, garbage string, out-of-range
    year) becomes None rather than an exception.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and _YEAR_STRING_RE.fullmatch(value.strip()):
        year = int(value.strip())
    else:
        return None
    return year if minimum <= year <= maximum else None
