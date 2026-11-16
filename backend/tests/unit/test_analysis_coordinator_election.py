"""The analysis queue coordinator election must survive a database that is not ready yet.

Regression: after a NAS reboot the backend started before PostgreSQL accepted
connections ("the database system is starting up"); the election raised, the
worker thread returned for good and queued analysis jobs waited forever.
"""
from unittest.mock import MagicMock

from library import chunk_review_routes as routes


def _session(result=None, error=None):
    session = MagicMock()
    if error is not None:
        session.scalar.side_effect = error
    else:
        session.scalar.return_value = result
    return session


def test_owner_gets_session_and_keeps_it_open():
    session = _session(result=True)
    sleeps = []

    result = routes._elect_analysis_coordinator(lambda: session, sleep=sleeps.append, retry_seconds=0)

    assert result is session
    session.close.assert_not_called()
    assert sleeps == []


def test_not_owner_returns_none_and_closes_session():
    session = _session(result=False)

    result = routes._elect_analysis_coordinator(lambda: session, sleep=lambda _s: None, retry_seconds=0)

    assert result is None
    session.close.assert_called_once()


def test_database_error_is_retried_until_it_answers():
    failing = [_session(error=RuntimeError("the database system is starting up")) for _ in range(3)]
    ok = _session(result=True)
    sessions = iter([*failing, ok])
    sleeps = []

    result = routes._elect_analysis_coordinator(lambda: next(sessions), sleep=sleeps.append, retry_seconds=7)

    assert result is ok
    assert sleeps == [7, 7, 7]
    for session in failing:
        session.close.assert_called_once()


def test_retry_then_not_owner_ends_without_lock():
    first = _session(error=RuntimeError("connection refused"))
    second = _session(result=False)
    sessions = iter([first, second])

    result = routes._elect_analysis_coordinator(lambda: next(sessions), sleep=lambda _s: None, retry_seconds=0)

    assert result is None
    first.close.assert_called_once()
    second.close.assert_called_once()
