"""Year/month/day precision for an address stay's start and end."""
import datetime

import pytest

from library.partial_dates import format_partial_date, parse_partial_date


@pytest.mark.parametrize("value, end, expected", [
    ("2016", False, (datetime.date(2016, 1, 1), "year")),
    ("2016", True, (datetime.date(2016, 12, 31), "year")),
    ("2015-03", False, (datetime.date(2015, 3, 1), "month")),
    ("2015-03", True, (datetime.date(2015, 3, 31), "month")),
    ("2024-02", True, (datetime.date(2024, 2, 29), "month")),   # leap year
    ("2023-02", True, (datetime.date(2023, 2, 28), "month")),
    ("2015-03-05", False, (datetime.date(2015, 3, 5), "day")),
    ("2015-03-05", True, (datetime.date(2015, 3, 5), "day")),
])
def test_parse_picks_first_or_last_day_of_an_incomplete_period(value, end, expected):
    assert parse_partial_date(value, end=end) == expected


@pytest.mark.parametrize("value", ["", "16", "2016-3", "2016-13", "2016-00", "2016-02-30", "0999", "2016-03-5",
                                   "03.2015", "2016-03-05T10:00", " 2016", "abcd"])
def test_parse_rejects_everything_else(value):
    with pytest.raises(ValueError):
        parse_partial_date(value, end=False)


@pytest.mark.parametrize("day, precision, expected", [
    (datetime.date(2016, 1, 1), "year", "2016"),
    (datetime.date(2015, 3, 1), "month", "2015-03"),
    (datetime.date(2015, 3, 5), "day", "2015-03-05"),
    (datetime.date(2015, 3, 5), None, "2015-03-05"),   # rows from before precision existed are full days
    (None, "year", None),
])
def test_format_round_trips_at_the_stored_precision(day, precision, expected):
    assert format_partial_date(day, precision) == expected


def test_an_end_stored_as_last_day_keeps_ordering_checks_correct():
    start, _ = parse_partial_date("2019-06", end=False)
    end, _ = parse_partial_date("2019", end=True)     # "until 2019" still covers the second half of 2019
    assert end >= start
    late_start, _ = parse_partial_date("2020", end=False)
    assert end < late_start
