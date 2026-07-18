"""Tests for library/search/temporal.py (stage 5 of the search rebuild).

No sqlalchemy needed -- temporal.py only depends on library.search.types
(pure dataclasses) and unidecode.
"""

import pytest

from library.search.temporal import (
    HISTORICAL_ANCHORS,
    TemporalRelation,
    TemporalRelationError,
    enrich_subject_period,
    resolve_anchor,
    resolve_relation,
)
from library.search.types import MAX_SUBJECT_YEAR, MIN_SUBJECT_YEAR


class TestResolveAnchor:
    def test_known_anchor_resolves(self):
        assert resolve_anchor("koniec II wojny światowej") == 1945

    def test_case_and_diacritic_insensitive(self):
        assert resolve_anchor("KONIEC II WOJNY SWIATOWEJ") == 1945
        assert resolve_anchor("koniec ii wojny swiatowej") == 1945

    def test_extra_whitespace_normalized(self):
        assert resolve_anchor("  koniec   II wojny   światowej  ") == 1945

    def test_unknown_anchor_returns_none(self):
        assert resolve_anchor("bitwa pod jakims nieznanym miejscem") is None

    def test_none_and_empty_return_none(self):
        assert resolve_anchor(None) is None
        assert resolve_anchor("") is None
        assert resolve_anchor("   ") is None

    def test_every_dictionary_value_within_domain_bounds(self):
        for year in HISTORICAL_ANCHORS.values():
            assert MIN_SUBJECT_YEAR <= year <= MAX_SUBJECT_YEAR

    def test_fall_of_berlin_wall(self):
        assert resolve_anchor("upadek muru berlińskiego") == 1989

    def test_ussr_collapse(self):
        assert resolve_anchor("rozpad ZSRR") == 1991


class TestResolveRelationExact:
    def test_exact_returns_single_year_as_both_bounds(self):
        start, end, warning = resolve_relation(TemporalRelation.EXACT, year=1945)
        assert (start, end, warning) == (1945, 1945, None)

    def test_exact_accepts_string_relation_value(self):
        start, end, _warning = resolve_relation("exact", year=1945)
        assert (start, end) == (1945, 1945)

    def test_exact_without_year_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.EXACT)


class TestResolveRelationBeforeAfter:
    def test_before_leaves_start_open(self):
        start, end, warning = resolve_relation(TemporalRelation.BEFORE, year=1945)
        assert start is None
        assert end == 1945
        assert warning is None

    def test_after_leaves_end_open(self):
        start, end, warning = resolve_relation(TemporalRelation.AFTER, year=1945)
        assert start == 1945
        assert end is None
        assert warning is None

    def test_before_without_year_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.BEFORE)

    def test_after_without_year_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.AFTER)


class TestResolveRelationBetween:
    def test_between_returns_both_bounds(self):
        start, end, warning = resolve_relation(TemporalRelation.BETWEEN, year=1939, year_end=1945)
        assert (start, end, warning) == (1939, 1945, None)

    def test_between_swaps_reversed_years(self):
        start, end, _warning = resolve_relation(TemporalRelation.BETWEEN, year=1945, year_end=1939)
        assert (start, end) == (1939, 1945)

    def test_between_missing_year_end_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.BETWEEN, year=1939)

    def test_between_missing_year_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.BETWEEN, year_end=1945)


class TestResolveRelationAround:
    def test_around_uses_default_span_and_warns(self):
        start, end, warning = resolve_relation(TemporalRelation.AROUND, year=1945)
        assert (start, end) == (1940, 1950)
        assert warning is not None
        assert "1945" in warning

    def test_around_custom_span(self):
        start, end, _warning = resolve_relation(TemporalRelation.AROUND, year=2000, span_years=10)
        assert (start, end) == (1990, 2010)

    def test_around_clamped_to_domain_bounds(self):
        start, _end, _warning = resolve_relation(TemporalRelation.AROUND, year=MIN_SUBJECT_YEAR, span_years=100)
        assert start == MIN_SUBJECT_YEAR
        _start, end, _warning = resolve_relation(TemporalRelation.AROUND, year=MAX_SUBJECT_YEAR, span_years=100)
        assert end == MAX_SUBJECT_YEAR

    def test_around_without_year_raises(self):
        with pytest.raises(TemporalRelationError):
            resolve_relation(TemporalRelation.AROUND)


class TestResolveRelationInvalid:
    def test_unknown_relation_string_raises_value_error(self):
        with pytest.raises(ValueError):
            resolve_relation("sometime", year=1945)


class TestEnrichSubjectPeriod:
    def test_explicit_years_are_never_overridden(self):
        start, end, warning = enrich_subject_period(
            start_year=1939, end_year=1945, relation="after", anchor_text="upadek muru berlińskiego",
        )
        assert (start, end, warning) == (1939, 1945, None)

    def test_only_start_year_set_still_blocks_enrichment(self):
        start, end, warning = enrich_subject_period(
            start_year=1939, end_year=None, relation="after", anchor_text="rozpad ZSRR",
        )
        assert (start, end, warning) == (1939, None, None)

    def test_no_relation_leaves_both_bounds_null(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation=None, anchor_text=None,
        )
        assert (start, end, warning) == (None, None, None)

    def test_known_anchor_after_relation_resolves_year(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="after", anchor_text="upadek muru berlińskiego",
        )
        assert start == 1989
        assert end is None
        assert warning is not None and "1989" in warning

    def test_known_anchor_before_relation_resolves_year(self):
        start, end, _warning = enrich_subject_period(
            start_year=None, end_year=None, relation="before", anchor_text="rozpad ZSRR",
        )
        assert start is None
        assert end == 1991

    def test_known_anchor_exact_relation_resolves_year(self):
        start, end, _warning = enrich_subject_period(
            start_year=None, end_year=None,
            relation="exact", anchor_text="koniec II wojny światowej",
        )
        assert (start, end) == (1945, 1945)

    def test_known_anchor_around_relation_resolves_year_with_warning(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="around", anchor_text="rozpad ZSRR",
        )
        assert (start, end) == (1986, 1996)
        assert warning is not None

    def test_unknown_anchor_leaves_bounds_null_with_diagnostic_warning(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="after", anchor_text="bitwa pod nieznanym",
        )
        assert (start, end) == (None, None)
        assert warning is not None and "bitwa pod nieznanym" in warning

    def test_relation_without_anchor_text_leaves_bounds_null(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="after", anchor_text=None,
        )
        assert (start, end, warning) == (None, None, None)

    def test_between_relation_is_never_resolved_from_single_anchor(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="between", anchor_text="upadek muru berlińskiego",
        )
        assert (start, end, warning) == (None, None, None)

    def test_invalid_relation_string_is_ignored_not_raised(self):
        start, end, warning = enrich_subject_period(
            start_year=None, end_year=None, relation="sometime", anchor_text="upadek muru berlińskiego",
        )
        assert (start, end, warning) == (None, None, None)

    def test_never_touches_published_on_or_ingested_at(self):
        # Structural guarantee (stage 5 acceptance criterion): the function
        # signature only accepts/returns subject_period_* fields, so a
        # historical period can never leak into a publication/ingestion date.
        import inspect

        signature = inspect.signature(enrich_subject_period)
        assert set(signature.parameters) == {"start_year", "end_year", "relation", "anchor_text"}
