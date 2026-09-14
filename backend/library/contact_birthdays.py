"""Pure helpers for upcoming contact birthdays."""

import datetime
from calendar import isleap

from library.contact_names import contact_display_name


def next_occurrence(month: int, day: int, today: datetime.date) -> datetime.date:
    """Return this year's or next year's birthday, including today."""
    for year in (today.year, today.year + 1):
        # Explicit anniversary policy: Feb 29 rolls forward to March 1 in
        # non-leap years; this does not guess or alter the recorded birth date.
        if (month, day) == (2, 29) and not isleap(year):
            occurrence = datetime.date(year, 3, 1)
        else:
            occurrence = datetime.date(year, month, day)
        if occurrence >= today:
            return occurrence


def birthday_source(contact) -> tuple[int, int, bool] | None:
    """Prefer a complete birth date; ignore missing or invalid month/day pairs."""
    if contact.birthday is not None:
        return contact.birthday.month, contact.birthday.day, True
    month, day = contact.birthday_month, contact.birthday_day
    # Mirror contact_routes._validate_birthday_pair without importing Flask/DB.
    if type(month) is not int or not 1 <= month <= 12:
        return None
    max_day = 29 if month == 2 else 30 if month in (4, 6, 9, 11) else 31
    if type(day) is not int or not 1 <= day <= max_day:
        return None
    return month, day, False


def upcoming_birthday_entry(contact, today: datetime.date) -> dict | None:
    """Describe the next birthday without inventing a missing birth year."""
    source = birthday_source(contact)
    if source is None:
        return None
    month, day, has_year = source
    occurrence = next_occurrence(month, day, today)
    return {
        "contact_id": contact.id,
        "display_name": contact_display_name(contact),
        "birthday_month": month,
        "birthday_day": day,
        "has_year": has_year,
        "next_occurrence": occurrence.isoformat(),
        "days_until": (occurrence - today).days,
        "turning_age": occurrence.year - contact.birthday.year if has_year else None,
    }
