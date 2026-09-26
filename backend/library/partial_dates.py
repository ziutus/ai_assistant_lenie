"""Dates known only to the year or the month ("lives there since 2016", "moved out 03.2019").

A partial date is stored as a real ``date`` plus a precision (``year``/``month``/``day``): the first day of
the period for a range start, the last day for a range end. That keeps every ordering check ("end not before
start", "already ended") correct with plain date comparison — "until 2019" is still valid on 2019-06-01.
On the wire it is the ISO prefix at its precision: ``2016``, ``2016-03`` or ``2016-03-05``.
"""
from __future__ import annotations

import calendar
import datetime
import re

PRECISIONS = ("day", "month", "year")
_PARTIAL = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


def parse_partial_date(value: str, *, end: bool) -> tuple[datetime.date, str]:
    """``"2016"`` / ``"2016-03"`` / ``"2016-03-05"`` -> (date, precision); ValueError on anything else.

    ``end`` picks the last instead of the first day of an incomplete period.
    """
    match = _PARTIAL.fullmatch(value or "")
    if not match:
        raise ValueError("expected YYYY, YYYY-MM or YYYY-MM-DD")
    year, month, day = match.group(1), match.group(2), match.group(3)
    if int(year) < 1000:
        raise ValueError("year out of range")
    if day is not None:
        return datetime.date(int(year), int(month), int(day)), "day"
    if month is not None:
        month_number = int(month)
        if not 1 <= month_number <= 12:
            raise ValueError("month out of range")
        last = calendar.monthrange(int(year), month_number)[1]
        return datetime.date(int(year), month_number, last if end else 1), "month"
    return datetime.date(int(year), 12, 31) if end else datetime.date(int(year), 1, 1), "year"


def format_partial_date(value: datetime.date | None, precision: str | None) -> str | None:
    """Inverse of parse_partial_date; a missing precision (rows from before it existed) means a full day."""
    if value is None:
        return None
    if precision == "year":
        return f"{value.year:04d}"
    if precision == "month":
        return f"{value.year:04d}-{value.month:02d}"
    return value.isoformat()
