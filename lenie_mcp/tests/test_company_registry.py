import asyncio

import httpx

from lenie_mcp.client import LenieClient
from lenie_mcp.config import Settings
from lenie_mcp.service import LenieService


def test_registry_lookup_transport_and_wrapper():
    def handle(request):
        assert request.method == "GET"
        assert request.url.path == "/company_registry/check"
        assert dict(request.url.params) == {"krs": "123"}
        assert request.headers["x-api-key"] == "test-key"
        assert request.extensions["timeout"]["read"] == 180.0
        return httpx.Response(200, json={"crbr": {"status": "error"}, "krs": {"status": "ok"}})

    settings = Settings(api_url="https://backend.test", api_key="test-key", vault=None, vault_mode="remote")
    service = LenieService(settings, client=LenieClient(settings, transport=httpx.MockTransport(handle)))
    result = service.company_registry_check(krs="123")
    assert "notice" in result
    assert result["data"]["krs"]["status"] == "ok"


def test_registry_tool():
    from lenie_mcp.server import build_server

    settings = Settings(api_url="https://backend.test", api_key="test-key", vault=None, vault_mode="remote")
    service = LenieService(settings)
    listed = asyncio.run(build_server(service).list_tools())
    tools = listed.tools if hasattr(listed, "tools") else listed
    tool = next(t for t in tools if t.name == "company_registry_check")
    assert tool.annotations.read_only_hint is True
