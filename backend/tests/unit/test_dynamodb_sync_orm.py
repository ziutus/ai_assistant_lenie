"""Regression tests for the backwards-compatible legacy AWS CLI wrapper."""

import sys
from unittest.mock import MagicMock, patch


def test_wrapper_delegates_to_legacy_pull_service_without_processing(monkeypatch, capsys):
    from imports import dynamodb_sync

    cfg = MagicMock()
    session = MagicMock()
    service = MagicMock()
    service.run.return_value = {"found": 1, "added": 1}
    monkeypatch.setattr(dynamodb_sync, "load_config", lambda: cfg)
    monkeypatch.setattr(dynamodb_sync, "get_session", lambda: session)
    monkeypatch.setattr(dynamodb_sync, "storage_from_config", lambda received: MagicMock())
    monkeypatch.setattr(dynamodb_sync, "LegacyAwsPullService", lambda *args: service)

    with patch.object(sys, "argv", ["dynamodb_sync.py", "--since", "2026-07-20T00:00:00Z", "--limit", "1"]):
        assert dynamodb_sync.main() == 0

    service.run.assert_called_once_with({"since": "2026-07-20T00:00:00Z", "dry_run": False, "limit": 1})
    session.close.assert_called_once()
    assert '"added": 1' in capsys.readouterr().out
