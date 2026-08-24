"""Polish PESEL (national ID number) parsing — validation and birth date decoding.

PESEL encodes: YYMMDD (birth date, century folded into the month field),
a 4-digit serial (last digit = sex, odd male/even female — not needed by any
current caller), and a checksum digit.
"""

import datetime

_CHECKSUM_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)

# Month field range -> (century base, offset to subtract to get the real 1-12 month).
_CENTURY_RANGES = (
    (1, 12, 1900),
    (21, 32, 2000),
    (41, 52, 2100),
    (61, 72, 2200),
    (81, 92, 1800),
)


def is_valid_pesel(pesel: str | None) -> bool:
    if not pesel or len(pesel) != 11 or not pesel.isdigit():
        return False
    checksum = sum(int(d) * w for d, w in zip(pesel[:10], _CHECKSUM_WEIGHTS)) % 10
    control = (10 - checksum) % 10
    return control == int(pesel[10])


def pesel_birthdate(pesel: str | None) -> datetime.date | None:
    """Decode the birth date encoded in a PESEL, or None if it's not a valid PESEL
    (bad checksum/length) or its month field doesn't fall in any known century range."""
    if not is_valid_pesel(pesel):
        return None
    yy = int(pesel[0:2])
    month_field = int(pesel[2:4])
    day = int(pesel[4:6])
    for low, high, century_base in _CENTURY_RANGES:
        if low <= month_field <= high:
            year = century_base + yy
            month = month_field - low + 1
            try:
                return datetime.date(year, month, day)
            except ValueError:
                return None
    return None
