"""Birthday calculations require neither Flask nor a database."""

import datetime as dt
from types import SimpleNamespace

import pytest

from library.contact_birthdays import birthday_source, next_occurrence, upcoming_birthday_entry


def _contact(**extra):
    defaults = dict(id=7, first_name="Anna", last_name="Nowak", display_label=None,
                    birthday=None, birthday_month=None, birthday_day=None)
    defaults.update(extra)
    return SimpleNamespace(**defaults)


def test_same_year_full_birthday_entry():
    contact = _contact(birthday=dt.date(1990, 9, 20))
    assert upcoming_birthday_entry(contact, dt.date(2026, 9, 14)) == {
        "contact_id": 7, "display_name": "Anna Nowak", "birthday_month": 9,
        "birthday_day": 20, "has_year": True, "next_occurrence": "2026-09-20",
        "days_until": 6, "turning_age": 36,
    }


def test_december_to_january_wraparound_without_birth_year():
    entry = upcoming_birthday_entry(_contact(birthday_month=1, birthday_day=3), dt.date(2026, 12, 28))
    assert entry["next_occurrence"] == "2027-01-03"
    assert entry["days_until"] == 6
    assert entry["has_year"] is False
    assert entry["turning_age"] is None


def test_birthday_today_is_not_skipped():
    entry = upcoming_birthday_entry(_contact(birthday_month=9, birthday_day=14), dt.date(2026, 9, 14))
    assert entry["days_until"] == 0
    assert entry["next_occurrence"] == "2026-09-14"


@pytest.mark.parametrize("today, expected", [
    (dt.date(2026, 2, 28), dt.date(2026, 3, 1)),
    (dt.date(2026, 3, 1), dt.date(2026, 3, 1)),
    (dt.date(2024, 3, 1), dt.date(2025, 3, 1)),
    (dt.date(2027, 3, 2), dt.date(2028, 2, 29)),
    (dt.date(2028, 2, 29), dt.date(2028, 2, 29)),
])
def test_february_29_rolls_forward_only_in_non_leap_years(today, expected):
    assert next_occurrence(2, 29, today) == expected


def test_full_date_takes_precedence_and_age_uses_occurrence_year():
    contact = _contact(birthday=dt.date(2000, 2, 29), birthday_month=7, birthday_day=10)
    assert birthday_source(contact) == (2, 29, True)
    entry = upcoming_birthday_entry(contact, dt.date(2024, 12, 31))
    assert entry["next_occurrence"] == "2025-03-01"
    assert entry["turning_age"] == 25


@pytest.mark.parametrize("month, day", [(None, None), (1, None), (None, 2), (0, 1),
                                         (13, 1), (2, 30), (4, 31), (1, 0), (True, 1), (1, "2")])
def test_missing_or_invalid_birthday_is_unusable(month, day):
    contact = _contact(birthday_month=month, birthday_day=day)
    assert birthday_source(contact) is None
    assert upcoming_birthday_entry(contact, dt.date(2026, 9, 14)) is None


def test_display_label_for_contact_without_names():
    contact = _contact(first_name=None, last_name=None, display_label="Neighbour",
                       birthday_month=9, birthday_day=20)
    assert upcoming_birthday_entry(contact, dt.date(2026, 9, 14))["display_name"] == "Neighbour"
