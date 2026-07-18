"""Structural validation of the search-query fixture (search rebuild, stage 0).

The fixture backend/tests/fixtures/search_query_cases.json is the evaluation
corpus for the future SearchQueryParser (plan: docs/search-rebuild-implementation-plan.md).
These tests pin its schema so later stages (4, 10) can rely on it.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "search_query_cases.json"

# Allowed keys of a partial ParsedSearchQuery (plan, section 5).
PARSED_QUERY_FIELDS = {
    "query",
    "author_name",
    "publisher_name",
    "publisher_domain",
    "discovery_source_name",
    "collection_name",
    "published_on_from",
    "published_on_to",
    "ingested_at_from",
    "ingested_at_to",
    "subject_period_start_year",
    "subject_period_end_year",
    "temporal_expression",
    "document_types",
    "languages",
    "sort",
    "interpretation_summary",
    "warnings",
    "clarification_required",
    "clarification_question",
    "model_confidence",
}

KNOWN_CATEGORIES = {
    "topic",
    "subject_period",
    "published_on",
    "ingested_at",
    "author",
    "publisher",
    "discovery_source",
    "document_type",
    "language",
    "combined",
    "adversarial",
    "fallback",
    "clarification",
    "validation",
}

KNOWN_DOCUMENT_TYPES = {
    "movie", "youtube", "link", "webpage", "text_message", "text", "email", "social_media_post",
}

KNOWN_SORTS = {"relevance", "published_desc", "published_asc", "ingested_desc"}


@pytest.fixture(scope="module")
def fixture_data():
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def cases(fixture_data):
    return fixture_data["cases"]


def test_fixture_has_representative_corpus_size(cases):
    assert 30 <= len(cases) <= 50


def test_case_ids_are_unique(cases):
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_cases_have_required_keys(cases):
    for case in cases:
        assert {"id", "category", "natural_query", "expected"} <= set(case), case.get("id")


def test_categories_are_known(cases):
    for case in cases:
        assert case["category"] in KNOWN_CATEGORIES, case["id"]


def test_natural_query_empty_only_for_clarification(cases):
    for case in cases:
        if not case["natural_query"].strip():
            assert case["category"] == "clarification", case["id"]


def test_expected_uses_only_parsed_query_fields(cases):
    for case in cases:
        unknown = set(case["expected"]) - PARSED_QUERY_FIELDS
        assert not unknown, f"{case['id']}: unknown expected fields {unknown}"


def test_expected_field_value_types(cases):
    for case in cases:
        expected = case["expected"]
        for field in ("subject_period_start_year", "subject_period_end_year"):
            if expected.get(field) is not None:
                assert isinstance(expected[field], int), case["id"]
        for field in ("published_on_from", "published_on_to"):
            if expected.get(field) is not None:
                date.fromisoformat(expected[field])
        for field in ("ingested_at_from", "ingested_at_to"):
            if expected.get(field) is not None:
                datetime.fromisoformat(expected[field])
        if expected.get("document_types") is not None:
            assert set(expected["document_types"]) <= KNOWN_DOCUMENT_TYPES, case["id"]
        if expected.get("languages") is not None:
            for lang in expected["languages"]:
                assert isinstance(lang, str) and len(lang) == 2, case["id"]
        if expected.get("sort") is not None:
            assert expected["sort"] in KNOWN_SORTS, case["id"]
        if "clarification_required" in expected:
            assert isinstance(expected["clarification_required"], bool), case["id"]


def test_period_ranges_are_ordered(cases):
    """Fixture expectations describe the NORMALIZED output, so ranges are ordered
    even when the natural query gives them reversed (edge-04, edge-05)."""
    for case in cases:
        expected = case["expected"]
        start = expected.get("subject_period_start_year")
        end = expected.get("subject_period_end_year")
        if start is not None and end is not None:
            assert start <= end, case["id"]
        pub_from = expected.get("published_on_from")
        pub_to = expected.get("published_on_to")
        if pub_from and pub_to:
            assert date.fromisoformat(pub_from) <= date.fromisoformat(pub_to), case["id"]


def test_relative_date_cases_carry_temporal_expression_or_sort(cases):
    """A relative-dates case must give the evaluation harness something to
    resolve against a fixed 'now': the temporal expression or an ingest sort."""
    for case in cases:
        if case.get("relative_dates"):
            expected = case["expected"]
            assert expected.get("temporal_expression") or expected.get("sort"), case["id"]
