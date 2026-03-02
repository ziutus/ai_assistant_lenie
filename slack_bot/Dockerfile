# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy shared package first (path dependency)
COPY shared_python/unified-config-loader/ /shared_python/unified-config-loader/

# Copy dependency files
COPY slack_bot/pyproject.toml slack_bot/uv.lock ./

# Install dependencies (include vault + aws extras for secret backends)
RUN uv sync --frozen --no-dev --no-install-project --extra vault --extra aws

# Copy source code and README (required by hatchling build)
COPY slack_bot/README.md .
COPY slack_bot/src/ src/

# Create non-root user
RUN groupadd -g 1001 lenie-slack-bot && \
    useradd -u 1001 -g lenie-slack-bot -m lenie-slack-bot && \
    chown -R 1001:1001 /app

USER lenie-slack-bot

# Socket Mode uses outbound WebSocket — no EXPOSE needed
CMD ["uv", "run", "python", "-m", "src.main"]
