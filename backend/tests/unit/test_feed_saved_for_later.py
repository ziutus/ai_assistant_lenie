"""Contract tests for the feed saved-for-later queue."""

import datetime as dt
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import inspect  # noqa: E402

from library.db.models import FeedItem  # noqa: E402
from library.feed_monitor_service import ACTIVE_TRANSITIONS, transition_item  # noqa: E402


def test_feed_item_has_saved_metadata_and_index():
    mapper = inspect(FeedItem).mapper
    assert {"saved_at", "saved_by_user_id"}.issubset(mapper.columns.keys())
    assert list(mapper.columns.saved_by_user_id.foreign_keys)[0].target_fullname == "users.id"
    assert any(index.name == "idx_feed_items_status_saved_at" for index in FeedItem.__table__.indexes)
    check = next(constraint for constraint in FeedItem.__table__.constraints if constraint.name == "ck_feed_items_status")
    assert "saved_for_later" in str(check.sqltext)


class _Session:
    def __init__(self, item):
        self.item = item
        self.statement = None

    def get(self, model, item_id):
        return self.item if self.item.id == item_id else None

    def execute(self, statement):
        # The real UPDATE is guarded by id + current status; rowcount=1 means
        # the transition won the race.
        self.statement = statement
        return SimpleNamespace(rowcount=1)

    def commit(self):
        pass


@pytest.mark.parametrize("source", ["new", "llm_analysis_requested", "error"])
def test_saved_for_later_transition_records_user_and_timestamp(source):
    item = SimpleNamespace(id=7, status=source, saved_at=None, saved_by_user_id=None)
    session = _Session(item)
    result = transition_item(session, 7, "saved_for_later", 42)
    assert result is item
    assert "saved_for_later" in ACTIVE_TRANSITIONS[source]
    params = session.statement.compile().params
    assert params["saved_by_user_id"] == 42
    assert isinstance(params["saved_at"], dt.datetime)
    assert "reviewed_at" not in params


def test_saved_for_later_can_restore_to_new():
    assert ACTIVE_TRANSITIONS["saved_for_later"] == {"new", "imported", "skipped", "ignored"}
