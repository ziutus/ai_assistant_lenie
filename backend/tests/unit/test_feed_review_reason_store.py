"""Catalog cache, validation, migration parity and transition policy."""

import importlib.util
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from library import feed_review_reason_store as store


@pytest.fixture(autouse=True)
def cache(monkeypatch):
    store.bust_cache()
    monkeypatch.setattr(store, "_fetch_rows", lambda: store.SEED_REASONS)
    yield
    store.bust_cache()


def test_ttl_and_bust(monkeypatch):
    now = [100.0]
    fetch = MagicMock(return_value=store.SEED_REASONS)
    monkeypatch.setattr(store.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(store, "_fetch_rows", fetch)
    store.list_reasons()
    now[0] = 159.9
    store.list_reasons()
    assert fetch.call_count == 1
    now[0] = 160
    store.list_reasons()
    assert fetch.call_count == 2
    store.bust_cache()
    store.list_reasons()
    assert fetch.call_count == 3


@pytest.mark.parametrize("error", [RuntimeError("offline"), SystemExit("missing config")])
def test_seed_on_database_failure(monkeypatch, error):
    monkeypatch.setattr(store, "_fetch_rows", MagicMock(side_effect=error))
    assert store.list_reasons() == store.SEED_REASONS


def test_inactive_codes_remain_valid_and_labels_use_raw_fallback(monkeypatch):
    rows = (replace(store.SEED_REASONS[0], active=False), *store.SEED_REASONS[1:])
    monkeypatch.setattr(store, "_fetch_rows", lambda: rows)
    assert store.is_valid_reason("not_interested")
    assert not store.is_valid_reason("unknown")
    assert store.label_for("duplicate") == "Duplikat / już widziałem"
    assert store.label_for("unknown") == "unknown"
    assert all(row.active and row.selectable for row in store.selectable_reasons())
    assert "not_interested" not in [row.code for row in store.list_reasons(include_inactive=False)]


def test_explicit_session_does_not_poison_cache(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(store, "_fetch_rows", lambda session=None: () if session is not None else store.SEED_REASONS)
    assert store.list_reasons(session) == ()
    assert store.list_reasons() == store.SEED_REASONS


@pytest.mark.parametrize("code", [None, "a", "A_code", "1code", "with-dash", "a" * 41, "white space"])
def test_invalid_codes(code):
    assert store.check_reason(code=code, label="Test")[1]


@pytest.mark.parametrize("label", [None, "", " \n\t ", "a" * 121, 12])
def test_invalid_labels(label):
    assert store.check_reason(code="test", label=label)[1]


@pytest.mark.parametrize("order", [-1, 10001, True, 1.2, "10"])
def test_invalid_order(order):
    assert store.check_reason(code="test", label="Test", sort_order=order)[1]


def test_collapses_whitespace():
    values, problem = store.check_reason(code="custom_12", label="  Jeden\n\t drugi  ", sort_order=10000)
    assert problem is None and values["label"] == "Jeden drugi"


def test_seed_matches_migration():
    path = Path(__file__).parents[2] / "alembic/versions/d4e6a8c1b573_feed_review_reasons.py"
    spec = importlib.util.spec_from_file_location("reason_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SEED_REASONS == [asdict(row) for row in store.SEED_REASONS]
    assert module.down_revision == "b9d3f1a7c526"


@pytest.mark.parametrize(
    "code,active,system,accepted",
    [
        ("missing", True, False, False),
        ("", True, False, False),
        ("custom", False, False, False),
        ("custom", True, False, True),
        ("expired", False, True, True),
        ("sent_to_radar", True, True, True),
    ],
)
def test_transition_policy(monkeypatch, code, active, system, accepted):
    from library import feed_monitor_service as service
    from library.db.models import FeedItem

    rows = () if code in {"missing", ""} else (store.ReasonEntry(code, "Test", active=active, system=system),)
    monkeypatch.setattr(store, "_fetch_rows", lambda: rows)
    monkeypatch.setattr(service, "record_review_decision", MagicMock())
    item = FeedItem(id=1, status="new", group_memberships=[])
    session = MagicMock()
    session.get.return_value = item
    session.execute.return_value.rowcount = 1
    if accepted:
        service.transition_item(session, 1, "skipped", review_reason=code)
        session.commit.assert_called_once()
    else:
        with pytest.raises(ValueError, match="^invalid review reason$"):
            service.transition_item(session, 1, "skipped", review_reason=code)
        session.execute.assert_not_called()


def test_default_reason_cannot_bypass_deactivation(monkeypatch):
    from library import feed_monitor_service as service
    from library.db.models import FeedItem

    monkeypatch.setattr(store, "_fetch_rows", lambda: (store.ReasonEntry("other", "Other", active=False),))
    session = MagicMock()
    session.get.return_value = FeedItem(id=1, status="new")
    with pytest.raises(ValueError, match="invalid review reason"):
        service.transition_item(session, 1, "skipped")
