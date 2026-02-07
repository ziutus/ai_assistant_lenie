# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Lenie is a personal AI assistant for collecting, managing, and searching data using LLMs. Named after the protagonist from Peter Watts' novel "Starfish," it helps users collect links/references, download and store webpage content, transcribe YouTube videos, and assess information reliability.

**Current version**: 0.3.13.0 | **Status**: Active development

## Common Commands

### Development (Docker Compose)
```bash
make build          # Build docker containers
make dev            # Run backend and frontend (docker compose up -d)
make down           # Stop and remove containers
```

### Running the Backend Directly
```bash
cd backend
python server.py    # Requires .env file with all environment variables
```

### Dependencies (uv)
```bash
# Install base dependencies
make install         # or: cd backend && uv sync

# Install all dependencies (including optional)
make install-all     # or: cd backend && uv sync --all-extras

# Install specific extras
make install-docker  # or: cd backend && uv sync --extra docker
make install-markdown # or: cd backend && uv sync --extra markdown

# Update lock file after changing pyproject.toml
make lock            # or: cd backend && uv lock
```

### Testing
```bash
# All tests with HTML report
pytest --self-contained-html --html=pytest-results/

# Unit tests only
pytest backend/tests/unit/

# Integration tests (requires database)
pytest backend/tests/integration/

# Single test file
pytest backend/tests/unit/test_split_for_embedding.py
```

### Code Quality
```bash
ruff check backend/ # Linting (line-length=120)
pre-commit run      # Run pre-commit hooks (includes TruffleHog secret detection)
```

## Architecture

### Backend (`backend/`)
Flask application (`server.py`) exposing REST API with 19 endpoints:
- Document CRUD: `/url_add`, `/website_list`, `/website_get_by_id`, `/website_save`, `/website_delete`
- AI operations: `/ai_get_embedding`, `/search_similar`, `/ai_ask`
- Content processing: `/website_download_text_content`, `/website_text_remove_not_needed`, `/website_split_for_embedding`
- Health checks: `/startup`, `/readiness`, `/liveness`, `/healthz`

All routes (except health endpoints) require `x-api-key` header validated against `STALKER_API_KEY` env var.

### Core Library (`backend/library/`)
- `stalker_web_document.py` - Core document model
- `stalker_web_documents_db_postgresql.py` - PostgreSQL ORM with pgvector
- `ai.py` - LLM provider abstraction
- `embedding.py` - Vector embedding generation
- `text_functions.py` - Text processing utilities
- `api/` - External service integrations:
  - `aws/` - Bedrock, S3, Comprehend
  - `openai/` - OpenAI API
  - `google/` - Vertex AI
  - `cloudferro/sherlock/` - Bielik (Polish LLM)
  - `asemblyai/` - Speech-to-text

### Frontend (`web_interface_react/`)
React 18 application with:
- `src/modules/shared/components/` - Reusable UI components
- `src/modules/shared/hooks/` - Custom React hooks
- `src/modules/shared/context/` - Auth context
- Internationalization via i18next

### Browser Extension (`web_chrome_extension/`)
Chrome/Kiwi browser extension for adding URLs directly from the browser.

## Infrastructure

### Docker Stack (`infra/docker/compose.yaml`)
- `lenie-ai-server` (port 5000) - Flask backend
- `lenie-ai-db` (port 5433) - PostgreSQL with pgvector extension
- `lenie-ai-frontend` (port 3000) - React frontend

### Kubernetes (`infra/kubernetes/kustomize/`)
Kustomize-based deployment with base configurations and GKE dev overlay.

### AWS (`infra/aws/`)
- CloudFormation templates for DynamoDB, RDS, SQS, Lambda, API Gateway
- Serverless Lambda functions

### CI/CD
- CircleCI (`.circleci/config.yml`) - EC2-based testing
- GitLab CI (`.gitlab-ci.yml`) - Qodana security scanning
- Jenkins (`Jenkinsfile`) - AWS EC2 orchestration, Semgrep security

## Environment Variables

Key variables (see `.env_example` for full list):
- `ENV_DATA` - Environment identifier
- `POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT` - Database connection
- `LLM_PROVIDER` - LLM backend (openai, bedrock, vertex)
- `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` - OpenAI credentials
- `EMBEDDING_MODEL` - Model for vector embeddings
- `STALKER_API_KEY` - API authentication key
- `PORT` - Server port

## Database

PostgreSQL with pgvector extension for vector similarity search. Documents stored with:
- Content and metadata
- Embeddings (vector type)
- Document state and processing status

## External Services

- **AI/LLM**: OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Content extraction**: Beautiful Soup, Markdownify, Firecrawl, YouTube Transcript API
- **Speech-to-text**: AssemblyAI ($0.12/hour)
- **PDF processing**: AWS Textract, pypdf
- **Secrets**: HashiCorp Vault
