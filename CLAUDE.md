# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Lenie is a personal AI assistant for collecting, managing, and searching data (articles, YouTube videos, books) using LLMs. It's a side project under active development — see `README.md` for the full narrative/vision. An MCP server prototype and a Slack bot were tried and removed 2026-07-22 as unnecessary maintenance surface — not needed for the actual Obsidian integration path (`/obsidian-note` skill + `article_browser.py`, see `README.md` Phase 2/3 notes); archived at git tags `archive/mcp-server` / `archive/slack-bot`.

**Licensing**: Business Source License 1.1 (`LICENSE`) — free to use/modify/self-host, but may not be offered as a competing hosted/managed/SaaS service. Converts to Apache 2.0 on 2030-03-12.

## Deployment reality — read this before trusting other docs

The project moved from an AWS-serverless architecture (Lambda/API Gateway/DynamoDB/SQS — see `docs/aws-roadmap.md`) to a **NAS-first architecture**: Docker Compose (Flask API + PostgreSQL + MinIO + workers) running on the author's own QNAP NAS. **`docs/deployment/README.md` is the current source of truth** for what's real vs. experimental — read it first when touching architecture/infra:

- `docs/deployment/nas/` — the only actively-deployed environment (own NAS, household users).
- `docs/deployment/commercial-multi-tenant-scaling-experiment.md`, `federation-experiment.md`, `hyperscalers/`, `eu_cloud/`, `onprem/` — thought experiments, low priority, must not force complexity into current code.

**Several root-level docs generated 2026-02-13 predate this pivot and describe the old AWS/Cognito-era plan as if current** — `docs/index.md`, `docs/development-guide.md`, `docs/project-overview.md`, `docs/architecture-*.md`, `docs/backlog-reference.md`, `docs/aws-roadmap.md`, and the "Future: Multiuser/LLM Text Analysis" sections at the bottom of `docs/development-guide.md` (Cognito auth, `_bmad-output/implementation-artifacts/sprint-status.yaml` backlog IDs — that backlog file no longer exists in this repo, it moved to a private repo). Treat these as historical unless cross-checked against `docs/deployment/` and the subdirectory `CLAUDE.md` files below.

BMad workflow output (`_bmad-output/`) is no longer stored in this repo — it was moved to a private repo (session/planning artifacts contain personal/business-strategy content not meant to be public) and `_bmad-output/` is gitignored here. `_bmad/*/config.yaml` point new BMad output there.

## Repo structure — subprojects

Monorepo, each subproject with its own dependency environment. Most have their own `CLAUDE.md` — read it before working in that directory instead of duplicating its content here:

| Path | What it is | Docs |
|---|---|---|
| `backend/` | Flask REST API — the core: document CRUD, LLM/embedding operations, NER, search, auth | [backend/CLAUDE.md](backend/CLAUDE.md) (and nested `library/`, `database/`, `imports/`, `data/`, `tests/` `CLAUDE.md` files) |
| `ner_service/` | Internal-only microservice wrapping spaCy Polish NER, isolated so the ~600MB model doesn't bloat the backend image | `ner_service/README.md` |
| `web_interface_react/` | Main React 18 SPA | [web_interface_react/CLAUDE.md](web_interface_react/CLAUDE.md) |
| `web_chrome_extension/` | Chrome/Kiwi Manifest v3 extension, primary content-capture path | [web_chrome_extension/CLAUDE.md](web_chrome_extension/CLAUDE.md) |
| `web_interface_app2/` | Placeholder app (only login works) — not in active use | [web_interface_app2/CLAUDE.md](web_interface_app2/CLAUDE.md) |
| `web_landing_page/` | Static landing page | `web_landing_page/README.md` |
| `infra/` | Docker Compose (local + NAS), AWS CloudFormation/Terraform/EKS, GCloud, Kubernetes Kustomize/Helm — AWS/K8s paths are historical, NAS Compose (`infra/docker/compose.nas.yaml`) is what's actually deployed |
| `docs/` | Architecture docs, ADRs (`docs/adr/`), deployment plans (`docs/deployment/`) |

Each subproject manages its own Python/Node dependencies independently (no shared root lockfile) — `cd` into it before installing/running.

## Common commands

Run from repo root unless noted. Full reference: `Makefile`, `docs/development-guide.md` (dated, verify against this file for anything infra-related).

```bash
# Docker stack (local dev)
make build && make dev        # build + run backend/db/frontend via docker compose
make down                     # stop and remove containers

# Backend deps (uv only — never pip)
cd backend && uv sync                    # base deps
cd backend && uv sync --all-extras       # everything
cd backend && uv lock                    # after editing pyproject.toml

# Lint / format (ruff, line-length=120)
make lint                     # or: cd backend && uv run ruff check .
make lint-fix
make format
make format-check

# Security (all via uvx — no venv pollution)
make security                 # semgrep
make security-deps            # pip-audit
make security-bandit
make security-safety
make security-all
```

### Tests

```bash
# Backend — full suite requires PostgreSQL + a resolvable config (Vault or ENV_DATA)
cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest tests/unit/ -q      # Windows
pytest backend/tests/unit/                                                    # if venv already active
pytest backend/tests/unit/test_split_for_embedding.py                         # single file
pytest backend/tests/integration/    # requires a running PostgreSQL

# ner_service — separate venv, has pl_core_news_lg installed locally
cd ner_service && .venv/Scripts/python -m pytest tests/ -q
```

`.venv_wsl/` (Linux) is a second, separate environment used for deploy/import scripts run through WSL — never plain `uv sync` there, always `UV_PROJECT_ENVIRONMENT=.venv_wsl uv sync` or an activated `--active` sync, or it silently overwrites the Windows `.venv`.

## Architecture notes that span multiple files

- **Auth**: `x-api-key` header on every route except health checks. `api_keys` table, `kind=user` (reader identity, household trust model, no passwords) vs `kind=service` (full access, 403 on reader-only endpoints). See `backend/library/auth.py`, `backend/library/api_key_routes.py`, `backend/library/reader_routes.py`.
- **Storage abstraction (in progress)**: `backend/library/storage.py` defines an `ObjectStorage` interface (`LocalStorage`/`S3Storage`, S3-compatible so MinIO/AWS/CloudFerro share one code path) per `docs/deployment/nas/storage-and-jobs-migration-plan.md` Etap 1 — new code should go through this, not direct `boto3`/filesystem calls.
- **Job execution**: today, batch scripts (`backend/documents_pipeline.py`, `backend/imports/*.py`) run manually/locally; the plan (`docs/deployment/nas/storage-and-jobs-migration-plan.md`) moves this to a PostgreSQL-backed job queue + worker on the NAS. Don't add new cron/local-only automation without checking that plan first.
- **Multi-user model**: household trust model (`docs/deployment/nas/multi-user-household.md`) — shared document library, `kind=user` per person, no per-workspace data isolation. This is deliberately simpler than the (separate, thought-experiment-only) commercial multi-tenant model in `docs/deployment/commercial-multi-tenant-scaling-experiment.md`.
- **NER / entities**: `backend/library/entity_service.py`, `backend/library/person_registry.py` — person canonicalization, aliases, manual-review queue, `ner_exclusions` false-positive suppression. Backed by `ner_service/` over the internal Docker network.
- **Search**: hybrid (explicit filters + embeddings + LLM query parsing) — see `docs/search-hybrid.md` for the current design and known regressions/fixes, not `docs/architecture-backend.md` (stale, pre-rebuild).
- **`source` vs `byline`** on documents: `source` = how you discovered it (newsletter, friend, own), `byline` = who created it (author/channel). See `backend/CLAUDE.md` for the full explanation — a common source of confusion.

## Conventions

- Feature branch + PR to `main` always — never commit directly to `main` (branch protection also enforces this).
- `.gitattributes` enforces LF line endings repo-wide; don't fight it on Windows.
- Pre-commit hooks include gitleaks + TruffleHog secret scanning — don't bypass with `--no-verify`.
