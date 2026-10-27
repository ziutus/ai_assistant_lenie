import json

import httpx
import pytest
from starlette.testclient import TestClient

from lenie_mcp.config import ConfigError, Settings
from lenie_mcp.http_app import BearerAuthApp, HttpSettings, build_http_app, load_http_settings
from lenie_mcp.server import build_server
from lenie_mcp.service import LenieService

TOKEN = "t" * 40
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


def make_app():
    settings = Settings("http://x", "k", None, "remote")
    svc = LenieService(settings, __import__("lenie_mcp.client", fromlist=["LenieClient"]).LenieClient(
        settings, httpx.MockTransport(lambda r: httpx.Response(404, json={}))))
    http = HttpSettings(token=TOKEN, allowed_hosts=("localhost:*", "192.168.200.7:*"))
    return build_http_app(build_server(svc), http)


def auth(token=TOKEN):
    return {"authorization": f"Bearer {token}"}


def parse(resp):
    """MCP answers either JSON or an SSE 'data:' frame."""
    text = resp.text
    if text.lstrip().startswith("{"):
        return json.loads(text)
    return json.loads(next(line[5:] for line in text.splitlines() if line.startswith("data:")))


def test_settings_validation():
    assert load_http_settings({"LENIE_MCP_TOKEN": TOKEN}).port == 8000
    with pytest.raises(ConfigError):
        load_http_settings({})
    with pytest.raises(ConfigError):
        load_http_settings({"LENIE_MCP_TOKEN": "short"})
    with pytest.raises(ConfigError):
        load_http_settings({"LENIE_MCP_TOKEN": TOKEN, "LENIE_MCP_PORT": "abc"})
    custom = load_http_settings({"LENIE_MCP_TOKEN": TOKEN, "LENIE_MCP_ALLOWED_HOSTS": "a:*, b:80"})
    assert custom.allowed_hosts == ("a:*", "b:80")


def test_healthz_is_public_everything_else_needs_token():
    with TestClient(make_app(), base_url="http://localhost:8000") as client:
        assert client.get("/healthz").json() == {"status": "ok", "server": "lenie-mcp"}
        assert client.post("/mcp", json=INIT, headers=HEADERS).status_code == 401
        assert client.post("/mcp", json=INIT, headers={**HEADERS, **auth("w" * 40)}).status_code == 401
        no_scheme = client.post("/mcp", json=INIT, headers={**HEADERS, "authorization": TOKEN})
        assert no_scheme.status_code == 401
        resp = client.get("/anything")
        assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"


def test_authorized_client_can_initialize_and_list_tools():
    with TestClient(make_app(), base_url="http://localhost:8000") as client:
        init = client.post("/mcp", json=INIT, headers={**HEADERS, **auth()})
        assert init.status_code == 200, init.text
        assert parse(init)["result"]["serverInfo"]["name"] == "lenie"
        listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                             headers={**HEADERS, **auth()})
        names = {t["name"] for t in parse(listed)["result"]["tools"]}
        assert {"lenie_get_document", "obsidian_propose_package", "obsidian_commit_package"} <= names


def test_foreign_host_header_is_refused():
    with TestClient(make_app(), base_url="http://evil.example:8000") as client:
        resp = client.post("/mcp", json=INIT, headers={**HEADERS, **auth()})
        assert resp.status_code == 421


def test_lan_host_with_port_is_accepted():
    with TestClient(make_app(), base_url="http://192.168.200.7:8765") as client:
        assert client.post("/mcp", json=INIT, headers={**HEADERS, **auth()}).status_code == 200


def test_browser_origin_is_refused():
    with TestClient(make_app(), base_url="http://localhost:8000") as client:
        resp = client.post("/mcp", json=INIT, headers={**HEADERS, **auth(), "origin": "http://evil.example"})
        assert resp.status_code == 403


def test_non_http_scopes_pass_through():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    import asyncio
    asyncio.run(BearerAuthApp(inner, TOKEN)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]
