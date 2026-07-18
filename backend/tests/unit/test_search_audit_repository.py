"""Tests for library/search/audit_repository.py (stage 2B of the search rebuild).

No database: sessions are faked. What matters is the shape of the row the
repository builds (statuses, truncation, JSONB serialization), that the
write commits in its own session, and that a database failure is swallowed
instead of breaking the search path.
"""

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import SearchInterpretationLog  # noqa: E402
from library.search.audit_repository import (  # noqa: E402
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_RAW_RESPONSE_LENGTH,
    TRUNCATION_SUFFIX,
    delete_expired_interpretations,
    parsed_query_to_dict,
    record_feedback,
    record_interpretation,
)
from library.search.types import (  # noqa: E402
    MAX_QUERY_LENGTH,
    FeedbackVerdict,
    InterpretationStatus,
    ParsedSearchQuery,
    SearchFeedback,
)


class FakeSessionFactory:
    def __init__(self, existing_log: SearchInterpretationLog | None = None, fail_on_commit: bool = False):
        self.added: list = []
        self.session = MagicMock()
        self.session.add.side_effect = self.added.append
        self.session.get.return_value = existing_log
        if fail_on_commit:
            self.session.commit.side_effect = RuntimeError("db down")
        else:
            self.session.commit.side_effect = self._assign_ids

    def _assign_ids(self):
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = i

    def __call__(self):
        return self.session


def parsed_query() -> ParsedSearchQuery:
    return ParsedSearchQuery(
        query="niewolnictwo w Afryce",
        subject_period_start_year=1945,
        published_on_from=date(2020, 1, 1),
        ingested_at_to=datetime(2026, 7, 18, 12, 30),
        document_types=("text",),
        interpretation_summary="Niewolnictwo w Afryce od 1945 roku",
        warnings=("Nie podano końca okresu.",),
    )


class TestRecordInterpretation:
    def test_parsed_success_row(self):
        factory = FakeSessionFactory()
        log_id = record_interpretation(
            raw_query="niewolnictwo w afryce po ii wojnie",
            status=InterpretationStatus.PARSED,
            model="Bielik-11B-v3.0-Instruct",
            parser_version="1",
            prompt_version="1",
            raw_response='{"query": "niewolnictwo w Afryce"}',
            parsed_query=parsed_query(),
            llm_latency_ms=900,
            search_latency_ms=150,
            result_count=7,
            session_factory=factory,
        )
        assert log_id == 1
        assert len(factory.added) == 1
        log = factory.added[0]
        assert log.status == "parsed"
        assert log.fallback_used is False
        assert log.parsed_query["query"] == "niewolnictwo w Afryce"
        assert log.result_count == 7
        factory.session.commit.assert_called_once()
        factory.session.close.assert_called_once()

    @pytest.mark.parametrize("status", list(InterpretationStatus))
    def test_every_status_is_writable(self, status):
        factory = FakeSessionFactory()
        assert record_interpretation(raw_query="q", status=status, session_factory=factory) == 1
        assert factory.added[0].status == status.value

    def test_llm_error_row(self):
        factory = FakeSessionFactory()
        record_interpretation(
            raw_query="cokolwiek",
            status="llm_error",
            error_code="timeout",
            error_message="Sherlock request timed out",
            fallback_used=True,
            session_factory=factory,
        )
        log = factory.added[0]
        assert log.status == "llm_error"
        assert log.error_code == "timeout"
        assert log.fallback_used is True

    def test_fallback_status_forces_fallback_flag(self):
        factory = FakeSessionFactory()
        record_interpretation(raw_query="q", status=InterpretationStatus.FALLBACK, session_factory=factory)
        assert factory.added[0].fallback_used is True

    def test_invalid_status_raises_before_any_write(self):
        factory = FakeSessionFactory()
        with pytest.raises(ValueError):
            record_interpretation(raw_query="q", status="nonsense", session_factory=factory)
        assert factory.added == []

    def test_parsed_query_accepts_plain_dict(self):
        factory = FakeSessionFactory()
        record_interpretation(
            raw_query="q",
            status=InterpretationStatus.PARSED,
            parsed_query={"query": "x"},
            session_factory=factory,
        )
        assert factory.added[0].parsed_query == {"query": "x"}

    def test_db_failure_swallowed_returns_none(self):
        factory = FakeSessionFactory(fail_on_commit=True)
        log_id = record_interpretation(raw_query="q", status="parsed", session_factory=factory)
        assert log_id is None
        factory.session.rollback.assert_called_once()
        factory.session.close.assert_called_once()


class TestTruncation:
    def test_raw_query_capped_at_query_limit(self):
        factory = FakeSessionFactory()
        record_interpretation(raw_query="x" * (MAX_QUERY_LENGTH + 500), status="parsed", session_factory=factory)
        stored = factory.added[0].raw_query
        assert len(stored) == MAX_QUERY_LENGTH
        assert stored.endswith(TRUNCATION_SUFFIX)

    def test_raw_response_capped(self):
        factory = FakeSessionFactory()
        record_interpretation(
            raw_query="q",
            status="invalid_json",
            raw_response="y" * (MAX_RAW_RESPONSE_LENGTH * 2),
            session_factory=factory,
        )
        stored = factory.added[0].raw_response
        assert len(stored) == MAX_RAW_RESPONSE_LENGTH
        assert stored.endswith(TRUNCATION_SUFFIX)

    def test_error_message_capped(self):
        factory = FakeSessionFactory()
        record_interpretation(
            raw_query="q",
            status="llm_error",
            error_message="e" * (MAX_ERROR_MESSAGE_LENGTH + 1),
            session_factory=factory,
        )
        stored = factory.added[0].error_message
        assert len(stored) == MAX_ERROR_MESSAGE_LENGTH
        assert stored.endswith(TRUNCATION_SUFFIX)

    def test_short_values_untouched(self):
        factory = FakeSessionFactory()
        record_interpretation(
            raw_query="krótkie zapytanie",
            status="parsed",
            raw_response="{}",
            session_factory=factory,
        )
        assert factory.added[0].raw_query == "krótkie zapytanie"
        assert factory.added[0].raw_response == "{}"


class TestParsedQuerySerialization:
    def test_json_safe_values(self):
        data = parsed_query_to_dict(parsed_query())
        assert data["query"] == "niewolnictwo w Afryce"
        assert data["subject_period_start_year"] == 1945
        assert data["published_on_from"] == "2020-01-01"
        assert data["ingested_at_to"] == "2026-07-18T12:30:00"
        assert data["document_types"] == ["text"]
        assert data["warnings"] == ["Nie podano końca okresu."]
        assert data["sort"] == "relevance"
        assert data["model_confidence"] == "medium"
        assert data["clarification_question"] is None

    def test_only_json_types(self):
        def check(value):
            if isinstance(value, list):
                for item in value:
                    check(item)
            else:
                assert value is None or isinstance(value, (str, int, float, bool))

        for value in parsed_query_to_dict(parsed_query()).values():
            check(value)


class TestRecordFeedback:
    def test_feedback_written_to_existing_row(self):
        log = SearchInterpretationLog(raw_query="q", status="parsed")
        factory = FakeSessionFactory(existing_log=log)
        ok = record_feedback(
            5,
            SearchFeedback(
                verdict=FeedbackVerdict.PARTIALLY_CORRECT,
                comment="Okres OK, ale zły portal",
                corrected_query=parsed_query(),
            ),
            session_factory=factory,
        )
        assert ok is True
        assert log.feedback_verdict == "partially_correct"
        assert log.feedback_comment == "Okres OK, ale zły portal"
        assert log.corrected_query["query"] == "niewolnictwo w Afryce"
        assert log.feedback_at is not None
        factory.session.commit.assert_called_once()

    def test_feedback_update_overwrites_previous(self):
        log = SearchInterpretationLog(raw_query="q", status="parsed")
        log.feedback_verdict = "incorrect"
        log.feedback_comment = "stary komentarz"
        factory = FakeSessionFactory(existing_log=log)
        ok = record_feedback(5, SearchFeedback(verdict="correct"), session_factory=factory)
        assert ok is True
        assert log.feedback_verdict == "correct"
        assert log.feedback_comment is None
        assert log.corrected_query is None

    def test_missing_row_returns_false(self):
        factory = FakeSessionFactory(existing_log=None)
        ok = record_feedback(999, SearchFeedback(verdict="correct"), session_factory=factory)
        assert ok is False
        factory.session.commit.assert_not_called()

    def test_db_failure_swallowed(self):
        log = SearchInterpretationLog(raw_query="q", status="parsed")
        factory = FakeSessionFactory(existing_log=log, fail_on_commit=True)
        ok = record_feedback(5, SearchFeedback(verdict="correct"), session_factory=factory)
        assert ok is False
        factory.session.rollback.assert_called_once()
        factory.session.close.assert_called_once()


class TestRetention:
    def test_delete_expired_returns_rowcount(self):
        factory = FakeSessionFactory()
        factory.session.execute.return_value.rowcount = 3
        assert delete_expired_interpretations(session_factory=factory) == 3
        statement = factory.session.execute.call_args.args[0]
        assert "expires_at" in str(statement)
        factory.session.commit.assert_called_once()
        factory.session.close.assert_called_once()

    def test_delete_expired_propagates_db_errors(self):
        factory = FakeSessionFactory()
        factory.session.execute.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            delete_expired_interpretations(session_factory=factory)
        factory.session.close.assert_called_once()
