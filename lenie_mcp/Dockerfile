# syntax=docker/dockerfile:1.7
# Build context: repo root (nas-deploy.sh builds with -f lenie_mcp/Dockerfile .)

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# curl is used by the compose healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY lenie_mcp/pyproject.toml lenie_mcp/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY lenie_mcp/lenie_mcp/ lenie_mcp/

RUN groupadd -g 1003 lenie-mcp && \
    useradd -u 1003 -g lenie-mcp -m lenie-mcp && \
    chown -R 1003:1003 /app

USER lenie-mcp

ENV LENIE_MCP_TRANSPORT=http LENIE_MCP_HOST=0.0.0.0 LENIE_MCP_PORT=8000
EXPOSE 8000

# Direct venv entrypoint (not "uv run"); the package is run from /app, not installed
ENTRYPOINT ["/app/.venv/bin/python", "-m", "lenie_mcp.server"]
