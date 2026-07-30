import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g


def test_jobs_list_exposes_timestamps_result_watermark_and_service_capability(monkeypatch):
    from library.feed_routes import get_jobs

    job = SimpleNamespace(
        id="bridge-job", type="legacy_aws_pull", status="done", parameters={}, progress=None,
        result={"found": 6, "added": 0, "skipped": 6, "errors": 0, "watermark": "2026-07-29T15:25:35+00:00"},
        error=None, attempt=1, max_attempts=3,
        created_at=dt.datetime(2026, 7, 29, 15, 0, tzinfo=dt.timezone.utc),
        started_at=dt.datetime(2026, 7, 29, 15, 1, tzinfo=dt.timezone.utc),
        finished_at=dt.datetime(2026, 7, 29, 15, 2, tzinfo=dt.timezone.utc),
    )
    session = MagicMock()
    session.scalar.return_value = 1
    session.scalars.return_value.all.return_value = [job]
    monkeypatch.setattr("library.feed_routes.get_scoped_session", lambda: session)
    app = Flask(__name__)

    with app.test_request_context("/jobs?limit=25&offset=50"):
        g.auth = MagicMock(kind="service")
        response = get_jobs()

    payload = response.json
    assert payload["capabilities"] == {"manage_jobs": True, "run_legacy_aws_pull": True}
    assert payload["limit"] == 25
    assert payload["offset"] == 50
    assert payload["total"] == 1
    assert payload["filters"] == {"type": None, "status": None}
    assert payload["jobs"] == [{
        "id": "bridge-job", "type": "legacy_aws_pull", "status": "done", "parameters": {}, "progress": None,
        "result": job.result, "error": None, "attempt": 1, "max_attempts": 3,
        "created_at": "2026-07-29T15:00:00+00:00", "started_at": "2026-07-29T15:01:00+00:00",
        "finished_at": "2026-07-29T15:02:00+00:00", "watermark": "2026-07-29T15:25:35+00:00",
    }]


def test_user_can_create_only_bridge_job_and_is_recorded(monkeypatch):
    from library.feed_routes import create_job

    captured = {}

    def fake_enqueue(session, job_type, parameters, **kwargs):
        captured.update(job_type=job_type, parameters=parameters, **kwargs)
        return SimpleNamespace(id="user-bridge-job", status="queued")

    monkeypatch.setattr("library.feed_routes.get_scoped_session", lambda: MagicMock())
    monkeypatch.setattr("library.feed_routes.enqueue", fake_enqueue)
    app = Flask(__name__)

    with app.test_request_context("/jobs", method="POST", json={"type": "legacy_aws_pull"}):
        g.auth = SimpleNamespace(kind="user", user_id=42)
        response = create_job()

    assert response[1] == 202
    assert response[0].json == {"id": "user-bridge-job", "status": "queued"}
    assert captured == {"job_type": "legacy_aws_pull", "parameters": {}, "idempotency_key": None, "user_id": 42}


def test_user_cannot_create_other_job_types(monkeypatch):
    from library.feed_routes import create_job

    monkeypatch.setattr("library.feed_routes.get_scoped_session", lambda: MagicMock())
    app = Flask(__name__)

    with app.test_request_context("/jobs", method="POST", json={"type": "feed_daily"}), pytest.raises(Exception) as exc_info:
        g.auth = SimpleNamespace(kind="user", user_id=42)
        create_job()

    assert exc_info.value.code == 403


def test_scheduler_exposes_config_next_runs_and_last_jobs(monkeypatch):
    from library.feed_routes import get_scheduler

    feed_job = SimpleNamespace(
        id="daily", type="feed_daily", status="done", parameters={}, progress=None, result=None, error=None,
        attempt=1, max_attempts=3, created_at=dt.datetime(2026, 7, 29, 4, 0, tzinfo=dt.timezone.utc),
        started_at=None, finished_at=dt.datetime(2026, 7, 29, 4, 2, tzinfo=dt.timezone.utc),
    )
    feed_task = SimpleNamespace(id="feed_daily", enabled=True, timezone="Europe/Warsaw", times=["04:00"])
    bridge_task = SimpleNamespace(id="legacy_aws_pull", enabled=True, timezone="Europe/Warsaw", times=["05:00", "17:00"])
    session = MagicMock()
    session.scalars.side_effect = [MagicMock(all=lambda: [feed_task, bridge_task]), MagicMock(first=lambda: feed_job), MagicMock(first=lambda: None)]
    monkeypatch.setattr("library.feed_routes.get_scoped_session", lambda: session)
    monkeypatch.setenv("FEED_TIMEZONE", "Europe/Warsaw")
    monkeypatch.setenv("FEED_SCHEDULE_TIME", "04:00")
    monkeypatch.setenv("AWS_LEGACY_PULL_ENABLED", "true")
    monkeypatch.setenv("AWS_LEGACY_PULL_INTERVAL_MINUTES", "15")
    app = Flask(__name__)

    with app.test_request_context("/scheduler"):
        g.auth = MagicMock(kind="service")
        payload = get_scheduler().json

    assert payload["schedules"][0]["schedule"] == "04:00"
    assert payload["schedules"][0]["last_job"]["id"] == "daily"
    assert payload["schedules"][1]["enabled"] is True
    assert payload["schedules"][1]["times"] == ["05:00", "17:00"]
