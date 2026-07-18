"""Unit tests for the search domain types (stage 1 of the search rebuild).

Every field is exercised with a valid value, a wrong type and its boundary;
the stage's exit condition is that an invalid object cannot be constructed,
so it can never reach SearchService.
"""

import dataclasses
from datetime import date, datetime

import pytest

from library.search import (
    MAX_SEARCH_LIMIT,
    MAX_SUBJECT_YEAR,
    MIN_SUBJECT_YEAR,
    FeedbackVerdict,
    InterpretationStatus,
    ModelConfidence,
    ParsedSearchQuery,
    SearchFeedback,
    SearchFilters,
    SearchQueryValidationError,
    SearchRequest,
    SearchSort,
    normalize_date_range,
    normalize_datetime_range,
    normalize_year_range,
)


def parsed_query(**overrides) -> ParsedSearchQuery:
    kwargs = {"interpretation_summary": "testowa interpretacja"}
    kwargs.update(overrides)
    return ParsedSearchQuery(**kwargs)


class TestEnums:
    def test_sort_values(self):
        assert [m.value for m in SearchSort] == [
            "relevance", "published_desc", "published_asc", "ingested_desc",
        ]

    def test_interpretation_status_values(self):
        assert [m.value for m in InterpretationStatus] == [
            "parsed", "ambiguous", "invalid_json", "validation_error", "llm_error", "fallback",
        ]

    def test_feedback_verdict_values(self):
        assert [m.value for m in FeedbackVerdict] == ["correct", "partially_correct", "incorrect"]

    def test_model_confidence_values(self):
        assert [m.value for m in ModelConfidence] == ["high", "medium", "low"]

    def test_enums_construct_from_string(self):
        assert SearchSort("published_desc") is SearchSort.PUBLISHED_DESC
        assert InterpretationStatus("fallback") is InterpretationStatus.FALLBACK


class TestSearchFilters:
    def test_full_valid_object(self):
        filters = SearchFilters(
            author_name="Jan Kowalski",
            publisher_name="Onet",
            publisher_domain="onet.pl",
            discovery_source_name="unknow.news",
            collection_name="historia",
            published_on_from=date(2020, 1, 1),
            published_on_to=date(2025, 12, 31),
            ingested_at_from=datetime(2024, 1, 1, 12, 0),
            ingested_at_to=datetime(2024, 6, 1, 12, 0),
            subject_period_start_year=-3100,
            subject_period_end_year=-30,
            document_types=["webpage", "youtube"],
            languages=["pl", "EN"],
        )
        assert filters.document_types == ("webpage", "youtube")
        assert filters.languages == ("pl", "en")
        assert not filters.is_empty()

    def test_empty_by_default(self):
        assert SearchFilters().is_empty()

    @pytest.mark.parametrize("field_name", [
        "author_name", "publisher_name", "discovery_source_name", "collection_name",
    ])
    @pytest.mark.parametrize("bad", ["", "   ", 123, ["x"]])
    def test_text_fields_reject_empty_and_wrong_types(self, field_name, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(**{field_name: bad})
        assert exc.value.field == field_name

    def test_text_fields_are_stripped(self):
        assert SearchFilters(author_name="  Jan  ").author_name == "Jan"

    @pytest.mark.parametrize("bad", ["onet", "http://onet.pl", "o net.pl", "-bad-.pl", 5])
    def test_publisher_domain_rejects_invalid(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(publisher_domain=bad)
        assert exc.value.field == "publisher_domain"

    def test_publisher_domain_is_lowercased(self):
        assert SearchFilters(publisher_domain="Onet.PL").publisher_domain == "onet.pl"

    @pytest.mark.parametrize("field_name", ["published_on_from", "published_on_to"])
    @pytest.mark.parametrize("bad", ["2024-01-01", datetime(2024, 1, 1), 20240101])
    def test_published_on_requires_plain_date(self, field_name, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(**{field_name: bad})
        assert exc.value.field == field_name

    @pytest.mark.parametrize("field_name", ["ingested_at_from", "ingested_at_to"])
    @pytest.mark.parametrize("bad", ["2024-01-01T00:00:00", date(2024, 1, 1), 0])
    def test_ingested_at_requires_datetime(self, field_name, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(**{field_name: bad})
        assert exc.value.field == field_name

    @pytest.mark.parametrize("field_name", ["subject_period_start_year", "subject_period_end_year"])
    @pytest.mark.parametrize("bad", ["1945", 1945.0, True, MIN_SUBJECT_YEAR - 1, MAX_SUBJECT_YEAR + 1])
    def test_years_reject_wrong_types_and_bounds(self, field_name, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(**{field_name: bad})
        assert exc.value.field == field_name

    def test_years_accept_boundaries(self):
        filters = SearchFilters(
            subject_period_start_year=MIN_SUBJECT_YEAR,
            subject_period_end_year=MAX_SUBJECT_YEAR,
        )
        assert filters.subject_period_start_year == MIN_SUBJECT_YEAR
        assert filters.subject_period_end_year == MAX_SUBJECT_YEAR

    @pytest.mark.parametrize("bad", ["webpage", [1], ["nosuchtype"], [""], [None]])
    def test_document_types_reject_invalid(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(document_types=bad)
        assert exc.value.field == "document_types"

    @pytest.mark.parametrize("bad", [["polski"], ["p"], ["pl-PL"], "pl", [1]])
    def test_languages_reject_invalid(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(languages=bad)
        assert exc.value.field == "languages"

    def test_reversed_year_range_rejected(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(subject_period_start_year=1800, subject_period_end_year=1700)
        assert exc.value.field == "subject_period_start_year"

    def test_reversed_published_on_range_rejected(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(published_on_from=date(2025, 1, 1), published_on_to=date(2020, 1, 1))
        assert exc.value.field == "published_on_from"

    def test_reversed_ingested_at_range_rejected(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFilters(
                ingested_at_from=datetime(2025, 1, 1),
                ingested_at_to=datetime(2020, 1, 1),
            )
        assert exc.value.field == "ingested_at_from"

    def test_open_ended_ranges_allowed(self):
        assert SearchFilters(subject_period_start_year=1945).subject_period_end_year is None
        assert SearchFilters(published_on_to=date(2025, 1, 1)).published_on_from is None

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            SearchFilters().author_name = "x"


class TestParsedSearchQuery:
    def test_canonical_plan_example(self):
        parsed = ParsedSearchQuery(
            query="niewolnictwo w Afryce",
            subject_period_start_year=1945,
            subject_period_end_year=None,
            temporal_expression="od końca II wojny światowej",
            interpretation_summary="Niewolnictwo w Afryce od zakończenia II wojny światowej",
            warnings=["Nie podano końca okresu."],
        )
        assert parsed.query == "niewolnictwo w Afryce"
        assert parsed.subject_period_start_year == 1945
        assert parsed.warnings == ("Nie podano końca okresu.",)
        assert parsed.sort is SearchSort.RELEVANCE
        assert parsed.model_confidence is ModelConfidence.MEDIUM
        assert not parsed.clarification_required

    def test_interpretation_summary_is_required(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            ParsedSearchQuery(query="cokolwiek")
        assert exc.value.field == "interpretation_summary"

    def test_shared_filter_fields_are_validated(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            parsed_query(subject_period_start_year=1800, subject_period_end_year=1700)
        assert exc.value.field == "subject_period_start_year"
        with pytest.raises(SearchQueryValidationError):
            parsed_query(document_types=["nosuchtype"])

    def test_query_length_limit(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            parsed_query(query="x" * 1001)
        assert exc.value.field == "query"

    def test_sort_and_confidence_accept_strings(self):
        parsed = parsed_query(sort="published_desc", model_confidence="high")
        assert parsed.sort is SearchSort.PUBLISHED_DESC
        assert parsed.model_confidence is ModelConfidence.HIGH

    @pytest.mark.parametrize("field_name,bad", [
        ("sort", "newest"),
        ("model_confidence", "certain"),
        ("warnings", "warning"),
        ("clarification_required", 1),
        ("temporal_expression", ""),
    ])
    def test_invalid_values_rejected(self, field_name, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            parsed_query(**{field_name: bad})
        assert exc.value.field == field_name

    def test_clarification_question_requires_flag(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            parsed_query(clarification_question="Doprecyzuj temat?")
        assert exc.value.field == "clarification_question"
        parsed = parsed_query(clarification_required=True, clarification_question="Doprecyzuj temat?")
        assert parsed.clarification_question == "Doprecyzuj temat?"

    def test_empty_query_with_summary_means_list_everything(self):
        parsed = parsed_query()
        assert parsed.query is None
        assert parsed.to_filters().is_empty()

    def test_to_filters_round_trip(self):
        parsed = parsed_query(
            publisher_domain="onet.pl",
            published_on_from=date(2024, 1, 1),
            document_types=["webpage"],
            languages=["pl"],
        )
        filters = parsed.to_filters()
        assert filters == SearchFilters(
            publisher_domain="onet.pl",
            published_on_from=date(2024, 1, 1),
            document_types=("webpage",),
            languages=("pl",),
        )

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            parsed_query().query = "zmiana"


class TestNormalizeRanges:
    def test_year_swap_with_warning(self):
        start, end, warning = normalize_year_range(1800, 1700)
        assert (start, end) == (1700, 1800)
        assert "1800" in warning and "1700" in warning

    def test_year_noop(self):
        assert normalize_year_range(1700, 1800) == (1700, 1800, None)
        assert normalize_year_range(None, 1800) == (None, 1800, None)
        assert normalize_year_range(1700, None) == (1700, None, None)

    def test_date_swap_with_warning(self):
        d_from, d_to, warning = normalize_date_range(date(2025, 12, 31), date(2020, 1, 1))
        assert (d_from, d_to) == (date(2020, 1, 1), date(2025, 12, 31))
        assert "2025-12-31" in warning

    def test_datetime_swap_with_warning(self):
        dt_from, dt_to, warning = normalize_datetime_range(datetime(2025, 1, 1), datetime(2020, 1, 1))
        assert (dt_from, dt_to) == (datetime(2020, 1, 1), datetime(2025, 1, 1))
        assert warning is not None

    def test_normalized_values_construct_cleanly(self):
        start, end, warning = normalize_year_range(1800, 1700)
        filters = SearchFilters(subject_period_start_year=start, subject_period_end_year=end)
        assert filters.subject_period_start_year == 1700
        assert warning is not None


class TestSearchRequest:
    def test_natural_variant(self):
        request = SearchRequest(natural_query="niewolnictwo w Afryce po 1945")
        assert request.is_natural
        assert request.limit == 10
        assert request.offset == 0
        assert request.sort is SearchSort.RELEVANCE

    def test_explicit_variant_query_only(self):
        request = SearchRequest(query="niewolnictwo w Afryce", limit=20)
        assert not request.is_natural

    def test_explicit_variant_filters_only(self):
        request = SearchRequest(filters=SearchFilters(languages=["pl"]))
        assert not request.is_natural

    def test_both_variants_rejected(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchRequest(natural_query="temat", query="temat")
        assert exc.value.field == "natural_query"
        with pytest.raises(SearchQueryValidationError):
            SearchRequest(natural_query="temat", filters=SearchFilters(languages=["pl"]))

    @pytest.mark.parametrize("kwargs", [{}, {"natural_query": None}, {"query": None}])
    def test_empty_request_rejected(self, kwargs):
        with pytest.raises(SearchQueryValidationError):
            SearchRequest(**kwargs)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_natural_query_rejected(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchRequest(natural_query=bad)
        assert exc.value.field == "natural_query"

    @pytest.mark.parametrize("bad", [0, -1, MAX_SEARCH_LIMIT + 1, True, 10.0, "10"])
    def test_limit_bounds_and_types(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchRequest(natural_query="temat", limit=bad)
        assert exc.value.field == "limit"

    def test_limit_boundaries_accepted(self):
        assert SearchRequest(natural_query="temat", limit=1).limit == 1
        assert SearchRequest(natural_query="temat", limit=MAX_SEARCH_LIMIT).limit == MAX_SEARCH_LIMIT

    @pytest.mark.parametrize("bad", [-1, True, "0"])
    def test_offset_rejects_invalid(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchRequest(natural_query="temat", offset=bad)
        assert exc.value.field == "offset"

    def test_filters_must_be_typed(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchRequest(query="temat", filters={"languages": ["pl"]})
        assert exc.value.field == "filters"

    def test_sort_from_string(self):
        request = SearchRequest(natural_query="temat", sort="ingested_desc")
        assert request.sort is SearchSort.INGESTED_DESC


class TestSearchFeedback:
    def test_verdict_from_string(self):
        feedback = SearchFeedback(verdict="partially_correct", comment="prawie dobrze")
        assert feedback.verdict is FeedbackVerdict.PARTIALLY_CORRECT

    def test_invalid_verdict_rejected(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFeedback(verdict="maybe")
        assert exc.value.field == "verdict"

    def test_corrected_query_must_be_typed(self):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFeedback(verdict="incorrect", corrected_query={"query": "temat"})
        assert exc.value.field == "corrected_query"
        feedback = SearchFeedback(verdict="incorrect", corrected_query=parsed_query(query="temat"))
        assert feedback.corrected_query.query == "temat"

    @pytest.mark.parametrize("bad", ["", 42])
    def test_comment_rejects_invalid(self, bad):
        with pytest.raises(SearchQueryValidationError) as exc:
            SearchFeedback(verdict="correct", comment=bad)
        assert exc.value.field == "comment"
