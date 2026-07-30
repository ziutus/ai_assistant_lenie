"""Dry-run contract for the backwards-compatible legacy AWS CLI wrapper."""

import sys
from unittest.mock import MagicMock, patch


def test_dry_run_wrapper_does_not_open_postgres_or_construct_minio(monkeypatch):
    from imports import dynamodb_sync

    service = MagicMock()
    service.run.return_value = {"found": 0, "dry_run": True}
    get_session = MagicMock()
    storage_from_config = MagicMock()
    monkeypatch.setattr(dynamodb_sync, "load_config", lambda: MagicMock())
    monkeypatch.setattr(dynamodb_sync, "get_session", get_session)
    monkeypatch.setattr(dynamodb_sync, "storage_from_config", storage_from_config)
    monkeypatch.setattr(dynamodb_sync, "LegacyAwsPullService", lambda *args: service)

    with patch.object(sys, "argv", ["dynamodb_sync.py", "--since", "2026-07-20T00:00:00Z", "--dry-run"]):
        assert dynamodb_sync.main() == 0

    get_session.assert_not_called()
    storage_from_config.assert_not_called()
    assert service.run.call_args.args[0]["dry_run"] is True
