"""Unit tests for mcp_server.main — healthz endpoint response."""

import asyncio
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")


def _import_main_with_mock_config(server_name: str = "lenie-mcp"):
    """Force-reload main.py with a mocked config module to bypass env var requirement."""
    sys.modules.pop("mcp_server.main", None)
    mock_cfg = MagicMock()
    mock_cfg.settings.server_name = server_name
    with patch.dict("sys.modules", {"mcp_server.config": mock_cfg}):
        import mcp_server.main as main_module
    return main_module


def test_healthz_returns_http_200_with_ok_status():
    """GET /healthz returns HTTP 200 and body with status=ok."""
    main_module = _import_main_with_mock_config()

    response = asyncio.run(main_module.healthz(MagicMock()))
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


def test_healthz_server_name_comes_from_settings():
    """healthz() uses settings.server_name — not a hardcoded string."""
    main_module = _import_main_with_mock_config(server_name="custom-mcp")

    response = asyncio.run(main_module.healthz(MagicMock()))
    body = json.loads(response.body)

    assert body["server"] == "custom-mcp"
