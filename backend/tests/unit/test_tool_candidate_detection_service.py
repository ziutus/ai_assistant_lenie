"""Unit tests for tool_candidate_detection_service (Story 43.2).

No database, no live LLM: session is mocked, ai_ask() is monkeypatched.
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.tool_candidate_detection_service import (
    DEFAULT_BATCH_LIMIT,
    _parse_mentions,
    _prioritize,
    execute_tool_candidate_detect,
)
from library.db.models import ToolCandidate


def _doc(doc_id, discovery_source_id=None, ingested_at=None, text_md="Treść.", title="T"):
    return SimpleNamespace(
        id=doc_id, discovery_source_id=discovery_source_id, ingested_at=ingested_at,
        text_md=text_md, text=None, title=title,
    )


def _ai_response(mentions):
    return SimpleNamespace(response_text=json.dumps({"mentions": mentions}))


class TestPrioritize:
    def test_sorts_descending_by_source_document_count(self):
        low = _doc(1, discovery_source_id=10)
        high = _doc(2, discovery_source_id=20)
        result = _prioritize([low, high], {10: 1, 20: 5})
        assert [doc.id for doc in result] == [2, 1]

    def test_ties_broken_by_ingested_at_ascending(self):
        newer = _doc(1, discovery_source_id=10, ingested_at=datetime(2026, 8, 2))
        older = _doc(2, discovery_source_id=10, ingested_at=datetime(2026, 8, 1))
        result = _prioritize([newer, older], {10: 3})
        assert [doc.id for doc in result] == [2, 1]

    def test_missing_source_count_treated_as_zero(self):
        known = _doc(1, discovery_source_id=10)
        unknown = _doc(2, discovery_source_id=99)
        result = _prioritize([unknown, known], {10: 2})
        assert [doc.id for doc in result] == [1, 2]


class TestParseMentions:
    def test_parses_plain_json(self):
        raw = json.dumps({"mentions": [{"name": "Grafana"}]})
        assert _parse_mentions(raw) == [{"name": "Grafana"}]

    def test_parses_fenced_json(self):
        raw = "```json\n" + json.dumps({"mentions": []}) + "\n```"
        assert _parse_mentions(raw) == []

    def test_invalid_json_returns_empty_list(self):
        assert _parse_mentions("not json at all") == []

    def test_non_list_mentions_returns_empty_list(self):
        raw = json.dumps({"mentions": "oops"})
        assert _parse_mentions(raw) == []

    def test_none_input_returns_empty_list(self):
        assert _parse_mentions(None) == []


class TestExecuteToolCandidateDetect:
    def test_real_tool_mention_creates_candidate(self):
        doc = _doc(5)
        session = MagicMock()
        session.get.return_value = doc
        session.scalar.return_value = None  # no existing duplicate
        job = MagicMock(id="job-1", parameters={"document_id": 5})

        mentions = [{"name": "Grafana", "context_snippet": "dashboard do Grafana", "is_tool": True, "reason": "narzędzie"}]
        with patch("library.tool_candidate_detection_service.ai_ask", return_value=_ai_response(mentions)):
            result = execute_tool_candidate_detect(session, job)

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, ToolCandidate)
        assert added.name == "Grafana"
        assert added.source_document_id == 5
        assert added.context_snippet == "dashboard do Grafana"
        assert result == {
            "documents_scanned": 1, "candidates_created": 1, "mentions_evaluated": 1,
            "documents_skipped_empty": 0, "documents_failed": 0,
        }

    def test_false_positive_mention_creates_no_candidate(self):
        """KubeCon scenario (AC #3 / PRD User Journey 2): zero writes for a non-tool mention."""
        doc = _doc(6)
        session = MagicMock()
        session.get.return_value = doc
        job = MagicMock(id="job-2", parameters={"document_id": 6})

        mentions = [{"name": "KubeCon", "context_snippet": "byliśmy na KubeCon", "is_tool": False, "reason": "to konferencja"}]
        with patch("library.tool_candidate_detection_service.ai_ask", return_value=_ai_response(mentions)):
            result = execute_tool_candidate_detect(session, job)

        session.add.assert_not_called()
        assert result["candidates_created"] == 0
        assert result["mentions_evaluated"] == 1

    def test_duplicate_mention_for_same_document_is_skipped(self):
        doc = _doc(7)
        session = MagicMock()
        session.get.return_value = doc
        session.scalar.return_value = 99  # an existing ToolCandidate.id already matches
        job = MagicMock(id="job-3", parameters={"document_id": 7})

        mentions = [{"name": "Grafana", "context_snippet": "...", "is_tool": True, "reason": "..."}]
        with patch("library.tool_candidate_detection_service.ai_ask", return_value=_ai_response(mentions)):
            result = execute_tool_candidate_detect(session, job)

        session.add.assert_not_called()
        assert result["candidates_created"] == 0

    def test_document_with_no_text_is_skipped_without_llm_call(self):
        doc = _doc(8, text_md=None)
        session = MagicMock()
        session.get.return_value = doc
        job = MagicMock(id="job-4", parameters={"document_id": 8})

        with patch("library.tool_candidate_detection_service.ai_ask") as mock_ai_ask:
            result = execute_tool_candidate_detect(session, job)

        mock_ai_ask.assert_not_called()
        assert result == {
            "documents_scanned": 1, "candidates_created": 0, "mentions_evaluated": 0,
            "documents_skipped_empty": 1, "documents_failed": 0,
        }

    def test_llm_failure_on_one_document_does_not_abort_the_batch(self):
        first = _doc(1)
        second = _doc(2)
        session = MagicMock()
        session.scalar.return_value = None
        job = MagicMock(id="job-5", parameters={})

        good_mentions = [{"name": "Grafana", "context_snippet": "...", "is_tool": True, "reason": "..."}]
        with patch("library.tool_candidate_detection_service._select_batch", return_value=[first, second]), \
             patch("library.tool_candidate_detection_service.ai_ask", side_effect=[Exception("boom"), _ai_response(good_mentions)]):
            result = execute_tool_candidate_detect(session, job)

        assert result["documents_scanned"] == 2
        assert result["documents_failed"] == 1
        assert result["candidates_created"] == 1

    def test_document_id_mode_never_calls_select_batch(self):
        doc = _doc(9)
        session = MagicMock()
        session.get.return_value = doc
        job = MagicMock(id="job-6", parameters={"document_id": 9})

        with patch("library.tool_candidate_detection_service._select_batch") as mock_select, \
             patch("library.tool_candidate_detection_service.ai_ask", return_value=_ai_response([])):
            execute_tool_candidate_detect(session, job)

        mock_select.assert_not_called()

    def test_missing_document_id_raises(self):
        session = MagicMock()
        session.get.return_value = None
        job = MagicMock(id="job-7", parameters={"document_id": 404})

        with pytest.raises(RuntimeError):
            execute_tool_candidate_detect(session, job)

    def test_batch_mode_uses_explicit_limit_from_job_parameters(self):
        session = MagicMock()
        job = MagicMock(id="job-8", parameters={"limit": 5})

        with patch("library.tool_candidate_detection_service._select_batch", return_value=[]) as mock_select:
            execute_tool_candidate_detect(session, job)

        mock_select.assert_called_once_with(session, 5)

    def test_batch_mode_falls_back_to_default_limit(self):
        session = MagicMock()
        job = MagicMock(id="job-9", parameters={})

        with patch("library.tool_candidate_detection_service._select_batch", return_value=[]) as mock_select:
            execute_tool_candidate_detect(session, job)

        mock_select.assert_called_once_with(session, DEFAULT_BATCH_LIMIT)


class TestJobTypeRegistration:
    def test_tool_candidate_detect_is_a_registered_job_type(self):
        from library.job_queue import JOB_TYPES

        assert "tool_candidate_detect" in JOB_TYPES
