# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY ner_service/pyproject.toml ner_service/uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Download Polish spaCy NER model (pl_core_news_lg, ~560MB) — see docs/geo-place-ner-plan.md / docs/person-ner-plan.md
RUN uv run python -m spacy download pl_core_news_lg

# Copy source code and README (required by hatchling build)
COPY ner_service/README.md .
COPY ner_service/src/ src/

# Create non-root user
RUN groupadd -g 1002 lenie-ner-service && \
    useradd -u 1002 -g lenie-ner-service -m lenie-ner-service && \
    chown -R 1002:1002 /app

USER lenie-ner-service

# No EXPOSE / published port — only reachable from other containers on lenie-net
CMD ["uv", "run", "python", "-m", "src.main"]
