"""Unit tests for duplicate analysis-run handling.

Reproduces the document 9245 scenario: two runs for the same scope (whole
document), the older one abandoned in status "created" with a pending chunk,
the newer one reviewed and used for Obsidian notes. The abandoned run must be
superseded (and its open chunks skipped) so it stops showing up in the
"missing Obsidian notes" filter; legal multi-run setups (different scopes,
reviewed runs) must never be touched.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.document_analysis_service import (  # noqa: E402
    OPEN_CHUNK_STATUSES,
    UNFINISHED_RUN_STATUSES,
    stale_duplicate_runs,
    supersede_unfinished_runs,
)

T0 = datetime(2026, 7, 9, 12, 0, 0)


def _run(id_, status="created", scope=None, minutes=0):
    return SimpleNamespace(
        id=id_, document_id=9245, scope=scope, status=status,
        created_at=T0 + timedelta(minutes=minutes),
    )


class TestStaleDuplicateRuns:
    def test_case_9245_abandoned_older_run_is_stale(self):
        run32 = _run(32, status="created", minutes=0)
        run33 = _run(33, status="reviewed", minutes=10)

        assert stale_duplicate_runs([run32, run33]) == [run32]

    def test_reviewed_older_run_is_never_stale(self):
        # deliberate re-analysis for comparison: both runs were actually used
        run1 = _run(1, status="reviewed", minutes=0)
        run2 = _run(2, status="reviewed", minutes=10)

        assert stale_duplicate_runs([run1, run2]) == []

    def test_newest_run_is_never_stale_even_when_unfinished(self):
        run1 = _run(1, status="reviewed", minutes=0)
        run2 = _run(2, status="created", minutes=10)

        assert stale_duplicate_runs([run1, run2]) == []

    def test_single_run_group_has_no_duplicates(self):
        assert stale_duplicate_runs([_run(32)]) == []
        assert stale_duplicate_runs([]) == []

    def test_in_review_older_run_is_stale(self):
        run1 = _run(1, status="in_review", minutes=0)
        run2 = _run(2, status="created", minutes=10)

        assert stale_duplicate_runs([run1, run2]) == [run1]

    def test_input_order_does_not_matter(self):
        run32 = _run(32, status="created", minutes=0)
        run33 = _run(33, status="reviewed", minutes=10)

        assert stale_duplicate_runs([run33, run32]) == [run32]

    def test_created_at_tie_broken_by_id(self):
        # double click: both runs share the same created_at second
        run32 = _run(32, status="created", minutes=0)
        run33 = _run(33, status="created", minutes=0)

        assert stale_duplicate_runs([run33, run32]) == [run32]


class TestSupersedeUnfinishedRuns:
    def _session_with(self, runs):
        session = MagicMock()
        session.scalars.return_value.all.return_value = runs
        return session

    def test_case_9245_unfinished_sibling_is_superseded(self):
        run32 = _run(32, status="created")
        session = self._session_with([run32])

        stale = supersede_unfinished_runs(session, 9245, None)

        assert stale == [run32]
        assert run32.status == "superseded"
        # one chunk UPDATE (open statuses -> skipped) issued per stale run
        assert session.execute.call_count == 1

    def test_reviewed_sibling_is_left_alone(self):
        run33 = _run(33, status="reviewed")
        session = self._session_with([run33])

        assert supersede_unfinished_runs(session, 9245, None) == []
        assert run33.status == "reviewed"
        assert session.execute.call_count == 0

    def test_other_scope_is_left_alone(self):
        # book workflow: split_only run over the whole book (scope=None) must
        # survive a new per-chapter run (scope="Rozdział 1") and vice versa
        whole_book = _run(1, status="created", scope=None)
        chapter = _run(2, status="created", scope="Rozdział 1")
        session = self._session_with([whole_book, chapter])

        stale = supersede_unfinished_runs(session, 9245, "Rozdział 1")

        assert stale == [chapter]
        assert whole_book.status == "created"
        assert chapter.status == "superseded"

    def test_matching_chapter_scope_is_superseded(self):
        chapter_old = _run(1, status="in_review", scope="Rozdział 1")
        session = self._session_with([chapter_old])

        assert supersede_unfinished_runs(session, 9245, "Rozdział 1") == [chapter_old]
        assert chapter_old.status == "superseded"


class TestStatusConstants:
    def test_open_chunk_statuses_exclude_terminal_ones(self):
        # approved/split chunks (and already-skipped ones) must survive a
        # supersede untouched — only review work still pending is skipped
        assert set(OPEN_CHUNK_STATUSES) == {"pending", "needs_reanalysis", "split_requested"}

    def test_unfinished_run_statuses(self):
        assert set(UNFINISHED_RUN_STATUSES) == {"created", "in_review"}
        assert "reviewed" not in UNFINISHED_RUN_STATUSES
        assert "superseded" not in UNFINISHED_RUN_STATUSES
