"""MCP server entry point — exposes the lenie-mcp FastMCP instance via streamable HTTP transport.

Routing:
- GET /healthz  → shallow health check (no DB), returns {"status": "ok", ...}
- /*            → FastMCP ASGI app (MCP protocol)
"""

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp_server.config import settings
from mcp_server.tools.lenie import register_lenie_tools

mcp = FastMCP(
    name=settings.server_name,
    stateless_http=True,  # Production mode — no session state
    json_response=True,   # JSON-RPC wire format
)

register_lenie_tools(mcp)

VERSION = "0.1.0"


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": settings.server_name, "version": VERSION})


# Starlette wrapper: /healthz is checked first, then everything else goes to FastMCP ASGI app.
# uvicorn entry point stays the same: mcp_server.main:app
app = Starlette(routes=[
    Route("/healthz", endpoint=healthz),
    Mount("/", app=mcp.streamable_http_app()),
])
