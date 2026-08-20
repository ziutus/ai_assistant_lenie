"""Tests for the auto-apply behavior in content_group_suggestion_service.py.

No database: session.get()/session.scalar() are faked directly rather than
executed against real SQLAlchemy statements (see FakeSession below) — this
mirrors the FakeSessionFactory pattern used in test_llm_usage_recorder.py.
Covers: a document suggestion above CONTENT_GROUP_AUTO_APPLY_MIN_CONFIDENCE
is auto-accepted with decided_by_user_id left None (the marker that
distinguishes a Bielik auto-decision from a human accept via
decide_suggestion()); a suggestion between the show/auto-apply thresholds
stays pending; a feed_item target never auto-applies regardless of
confidence (feed items stay a curated manual-review workflow).
"""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

import library.content_group_suggestion_service as svc  # noqa: E402
from library.db.models import (  # noqa: E402
    ContentGroup,
    ContentGroupSuggestionRun,
    Document,
    DocumentGroupMembership,
    FeedItem,
    Job,
)


class FakeSession:
    """Fakes exactly the calls execute_suggestion_job()/_auto_apply_suggestion() make."""

    def __init__(self, get_map, scalar_results=()):
        self._get_map = get_map
        self._scalar_results = list(scalar_results)
        self.added = []
        self.flush_count = 0
        self.commit_count = 0

    def get(self, model, id_):
        return self._get_map.get((model, id_))

    def scalar(self, _stmt):
        return self._scalar_results.pop(0) if self._scalar_results else None

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1


def _fake_ai_ask(suggestions, no_match=False):
    def call(*_args, **_kwargs):
        return SimpleNamespace(response_text=json.dumps({"suggestions": suggestions, "no_match": no_match}))
    return call


def _document_job(confidence: float):
    job = Job(id="job-1", parameters={"document_id": 42, "run_id": 7})
    doc = Document(id=42)
    run = ContentGroupSuggestionRun(
        id=7, document_id=42, status="queued", model="Bielik-11B-v3.0-Instruct",
        prompt_version="content-groups-v1", input_hash="x", catalog_snapshot=[{"id": 10, "name": "Linux"}],
    )
    session = FakeSession(
        get_map={(Document, 42): doc, (ContentGroupSuggestionRun, 7): run},
        scalar_results=[ContentGroup(id=10, kind="topic", archived_at=None), None],
    )
    return job, session, run


class TestAutoApply:
    def test_high_confidence_document_suggestion_is_auto_accepted(self, monkeypatch):
        job, session, run = _document_job(confidence=0.9)
        monkeypatch.setattr(svc, "ai_ask", _fake_ai_ask([{"group_id": 10, "confidence": 0.9, "reason": "o linuksie"}]))

        result = svc.execute_suggestion_job(session, job)

        assert result == {"run_id": 7, "suggestions": 1}
        suggestion = next(obj for obj in session.added if obj.__class__.__name__ == "ContentGroupSuggestion")
        assert suggestion.status == "accepted"
        assert suggestion.membership_created is True
        assert suggestion.decided_by_user_id is None  # auto-decision marker
        assert suggestion.decided_at is not None

        membership = next(obj for obj in session.added if isinstance(obj, DocumentGroupMembership))
        assert membership.document_id == 42
        assert membership.group_id == 10
        assert membership.source == "llm_suggestion"
        assert membership.source_suggestion_id == suggestion.id

    def test_mid_confidence_document_suggestion_stays_pending(self, monkeypatch):
        job, session, run = _document_job(confidence=0.65)
        monkeypatch.setattr(svc, "ai_ask", _fake_ai_ask([{"group_id": 10, "confidence": 0.65, "reason": "moze"}]))

        svc.execute_suggestion_job(session, job)

        # status/membership_created rely on DB server_default (only applied on
        # a real INSERT) -- against this fake session the invariant we can
        # check in-process is simply "auto-apply never touched this row".
        suggestion = next(obj for obj in session.added if obj.__class__.__name__ == "ContentGroupSuggestion")
        assert suggestion.status != "accepted"
        assert not any(isinstance(obj, DocumentGroupMembership) for obj in session.added)

    def test_feed_item_target_never_auto_applies(self, monkeypatch):
        job = Job(id="job-2", parameters={"feed_item_id": 5, "run_id": 8})
        item = FeedItem(id=5)
        run = ContentGroupSuggestionRun(
            id=8, feed_item_id=5, status="queued", model="Bielik-11B-v3.0-Instruct",
            prompt_version="content-groups-v1", input_hash="x", catalog_snapshot=[{"id": 10, "name": "Linux"}],
        )
        session = FakeSession(get_map={(FeedItem, 5): item, (ContentGroupSuggestionRun, 8): run})
        monkeypatch.setattr(svc, "ai_ask", _fake_ai_ask([{"group_id": 10, "confidence": 0.95, "reason": "o linuksie"}]))

        svc.execute_suggestion_job(session, job)

        suggestion = next(obj for obj in session.added if obj.__class__.__name__ == "ContentGroupSuggestion")
        assert suggestion.status != "accepted"
        assert not any(isinstance(obj, DocumentGroupMembership) for obj in session.added)
