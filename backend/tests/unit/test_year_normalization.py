"""Tests for library/year_normalization.py (stage 5 of the search rebuild)."""

from library.year_normalization import coerce_year


class TestCoerceYear:
    def test_plain_int_within_bounds(self):
        assert coerce_year(1945, minimum=-10_000, maximum=3000) == 1945

    def test_bce_negative_int_within_bounds(self):
        assert coerce_year(-1279, minimum=-10_000, maximum=3000) == -1279

    def test_digit_string_coerced(self):
        assert coerce_year("1945", minimum=-10_000, maximum=3000) == 1945

    def test_negative_digit_string_coerced(self):
        assert coerce_year("-1279", minimum=-10_000, maximum=3000) == -1279

    def test_string_with_whitespace_coerced(self):
        assert coerce_year(" 1945 ", minimum=-10_000, maximum=3000) == 1945

    def test_bool_rejected_even_though_int_subclass(self):
        assert coerce_year(True, minimum=-10_000, maximum=3000) is None
        assert coerce_year(False, minimum=-10_000, maximum=3000) is None

    def test_none_rejected(self):
        assert coerce_year(None, minimum=-10_000, maximum=3000) is None

    def test_garbage_string_rejected(self):
        assert coerce_year("dawno temu", minimum=-10_000, maximum=3000) is None

    def test_float_rejected(self):
        assert coerce_year(1945.5, minimum=-10_000, maximum=3000) is None

    def test_out_of_range_above_maximum_rejected(self):
        assert coerce_year(5000, minimum=-10_000, maximum=3000) is None

    def test_out_of_range_below_minimum_rejected(self):
        assert coerce_year(-20_000, minimum=-10_000, maximum=3000) is None

    def test_bounds_are_inclusive(self):
        assert coerce_year(3000, minimum=-10_000, maximum=3000) == 3000
        assert coerce_year(-10_000, minimum=-10_000, maximum=3000) == -10_000

    def test_different_callers_can_use_different_bounds(self):
        # time_periods.py's document-classification bounds are narrower
        # than search's subject_period bounds -- both must be honored.
        assert coerce_year(2200, minimum=-10_000, maximum=2_100) is None
        assert coerce_year(2200, minimum=-10_000, maximum=3000) == 2200
