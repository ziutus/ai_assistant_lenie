"""Streamable-HTTP transport for the NAS container (ADR-030 Etap B1).

The MCP app is wrapped in a Bearer-token ASGI layer: the container holds the service API key, so nothing may
reach a tool without the token. ``/healthz`` is the only unauthenticated path. Host-header (DNS rebinding)
protection is on, with the allowed hosts coming from the environment.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .config import ConfigError

MIN_TOKEN_CHARS = 32
DEFAULT_ALLOWED_HOSTS = "localhost:*,127.0.0.1:*,lenie-mcp:*,192.168.200.7:*"


@dataclass(frozen=True)
class HttpSettings:
    token: str
    host: str = "0.0.0.0"
    port: int = 8000
    path: str = "/mcp"
    allowed_hosts: tuple[str, ...] = ()


def load_http_settings(env: Mapping[str, str]) -> HttpSettings:
    token = env.get("LENIE_MCP_TOKEN", "").strip()
    if len(token) < MIN_TOKEN_CHARS:
        raise ConfigError(f"LENIE_MCP_TOKEN must be set and at least {MIN_TOKEN_CHARS} characters long")
    try:
        port = int(env.get("LENIE_MCP_PORT", "8000"))
    except ValueError:
        raise ConfigError("LENIE_MCP_PORT must be an integer") from None
    hosts = tuple(h.strip() for h in env.get("LENIE_MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS).split(",") if h.strip())
    return HttpSettings(token=token, host=env.get("LENIE_MCP_HOST", "0.0.0.0"), port=port, allowed_hosts=hosts)


class BearerAuthApp:
    """ASGI wrapper: GET /healthz is public, every other HTTP request needs ``Authorization: Bearer <token>``."""

    def __init__(self, app, token: str):
        self.app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan (session manager start/stop) and anything else pass through
            await self.app(scope, receive, send)
            return
        if scope["method"] == "GET" and scope["path"] == "/healthz":
            await self._respond(send, 200, {"status": "ok", "server": "lenie-mcp"})
            return
        if not self._authorized(scope):
            await self._respond(send, 401, {"error": "unauthorized"}, {b"www-authenticate": b"Bearer"})
            return
        await self.app(scope, receive, send)

    def _authorized(self, scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                scheme, _, supplied = value.partition(b" ")
                return scheme.lower() == b"bearer" and hmac.compare_digest(supplied.strip(), self._token)
        return False

    @staticmethod
    async def _respond(send, status: int, body: dict, extra: dict[bytes, bytes] | None = None):
        payload = json.dumps(body).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
        headers += list((extra or {}).items())
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": payload})


def build_http_app(server: MCPServer, http: HttpSettings):
    inner = server.streamable_http_app(
        streamable_http_path=http.path,
        stateless_http=True,  # proposals live in the service, not in MCP sessions; restarts must not strand clients
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(http.allowed_hosts),
            allowed_origins=[],  # CLI clients send no Origin; browsers are refused
        ),
        host=http.host,
    )
    return BearerAuthApp(inner, http.token)
