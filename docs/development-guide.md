# Development Guide

> Generated: 2026-02-13 | Project: lenie-server-2025

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | >= 3.11 | Backend runtime |
| uv | latest | Python package manager |
| Node.js | >= 18 | Frontend build |
| npm/yarn | latest | Frontend package manager |
| Docker + Docker Compose | latest | Local development stack |
| PostgreSQL | 17 | Database (via Docker or standalone) |
| Git | latest | Version control |

## Quick Start (Docker)

```bash
# Clone repository
git clone <repo-url> && cd lenie-server-2025

# Copy environment template
cp .env_example .env
# Edit .env with required values (see Environment Variables below)

# Build and run all services
make build
make dev

# Access:
# Backend API: http://localhost:5000
# Frontend:    http://localhost:3000
# Database:    localhost:5433
```

## Backend Development

### Setup

```bash
cd backend

# Install base dependencies
uv sync

# Install all dependencies (including optional)
uv sync --all-extras

# Install specific extras
uv sync --extra docker     # Docker-specific deps
uv sync --extra markdown   # Markdown processing deps
```

### Running

```bash
# Direct execution (requires .env in backend/)
python server.py

# Via Docker
make build && make dev
```

### Testing

```bash
# Full test suite with HTML report
pytest --self-contained-html --html=pytest-results/

# Unit tests only (no dependencies)
pytest backend/tests/unit/

# Integration tests (requires PostgreSQL)
pytest backend/tests/integration/

# Single test file
pytest backend/tests/unit/test_split_for_embedding.py
```

### Code Quality

```bash
# Linting (ruff, line-length=120)
make lint                    # or: cd backend && uv run ruff check .
make lint-fix                # Auto-fix

# Formatting
make format                  # or: cd backend && uv run ruff format .
make format-check            # Check only

# Security scanning
make security                # Semgrep
make security-deps           # pip-audit
make security-bandit         # Bandit
make security-safety         # Safety
make security-all            # All of the above

# Pre-commit hooks (includes TruffleHog secret detection)
pre-commit run
```

### Dependency Management

```bash
# Update lock file after changing pyproject.toml
make lock                    # or: cd backend && uv lock

# Sync dependencies from lock file
make sync                    # or: cd backend && uv sync
```

## Frontend Development (web_interface_react)

### Setup

```bash
cd web_interface_react
npm install
```

### Running

```bash
npm start          # Dev server (port 3000, hot reload)
npm run build      # Production build
npm test           # Run tests (@testing-library/react)
```

### API Backend Configuration

The frontend supports two backend modes (toggled in Authorization panel):
- **AWS Serverless**: Two Lambda endpoints via API Gateway
- **Docker**: Single Flask endpoint (http://localhost:5000)

Set API key and backend URL in the Authorization section of the UI.

## Browser Extension Development (web_chrome_extension)

No build step. Load unpacked:
1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `web_chrome_extension/` folder
4. Configure API key and server URL in extension Settings tab

## Environment Variables

Key variables (see `.env_example` for full list):

```bash
# Database
POSTGRESQL_HOST=lenie-ai-db        # Docker service name or RDS endpoint
POSTGRESQL_DATABASE=lenie
POSTGRESQL_USER=postgres
POSTGRESQL_PASSWORD=postgres
POSTGRESQL_PORT=5432

# Application
PORT=5000
STALKER_API_KEY=your-api-key       # API authentication
ENV_DATA=dev                       # Environment identifier

# LLM Configuration
LLM_PROVIDER=openai                # openai, bedrock, vertex, cloudferro
OPENAI_API_KEY=sk-...
OPENAI_ORGANIZATION=org-...
EMBEDDING_MODEL=text-embedding-ada-002
AI_MODEL_SUMMARY=gpt-4o

# AWS (optional)
AWS_REGION=us-east-1
AWS_S3_WEBSITE_CONTENT=bucket-name
AWS_QUEUE_URL_ADD=sqs-queue-url

# Other (optional)
ASSEMBLYAI=assemblyai-api-key     # Speech-to-text
CLOUDFERRO_SHERLOCK_KEY=...       # Polish LLM
GCP_PROJECT_ID=...                # Google Vertex AI
```

## Docker Operations

```bash
make build              # Build Docker containers
make dev                # Run backend + frontend + DB
make down               # Stop and remove containers

make docker-image       # Build and tag Docker image
make docker-push        # Push to Docker Hub
make docker-release     # Build + push
make docker-clean       # Remove old Docker images
```

## AWS Operations

```bash
make aws-start-openvpn  # Start OpenVPN EC2 + update DNS
```

For batch processing scripts that access AWS RDS:
1. Start OpenVPN: `make aws-start-openvpn`
2. Connect to VPN
3. Run batch script (e.g., `python backend/web_documents_do_the_needful_new.py`)

## Project Conventions

- **Python linting**: ruff with line-length=120, selects E/F/W, ignores E501
- **Python formatting**: ruff format
- **Pre-commit**: TruffleHog for secret detection
- **Makefile targets**: `aws-*` (AWS), `gcloud-*` (GCloud), no prefix (local)
- **API auth**: All routes except health checks require `x-api-key` header
- **Database**: Raw psycopg2 (no ORM)
- **Commits**: CI/CD varies by tool (CircleCI, GitLab CI, Jenkins)

## Line Endings (.gitattributes)

The project uses a `.gitattributes` file to enforce **LF (Unix) line endings** for all text files, regardless of the developer's operating system.

### Why this matters

- **Shell scripts break with CRLF**: Bash interprets `\r` (carriage return) as part of the code, causing cryptic syntax errors like `$'{\r'`. This is the most common issue when developing on Windows and running scripts in WSL or Linux.
- **Consistent diffs**: Mixed line endings (some files LF, some CRLF) create noisy git diffs where entire files appear changed even though only whitespace differs.
- **Cross-platform collaboration**: Developers on Windows, macOS, and Linux all get the same file content in their working copies.

### How it works

The `.gitattributes` file tells Git how to handle line endings at checkout and commit time:

```
# Auto detect text files and ensure LF line endings
* text=auto eol=lf

# Shell scripts must always use LF
*.sh text eol=lf
```

- `text=auto` — Git detects whether a file is text or binary
- `eol=lf` — text files are always checked out with LF endings, even on Windows
- Binary files (`.png`, `.ico`, `.svg`) are explicitly marked to prevent Git from mangling them

### What to do after cloning

No action needed — Git applies `.gitattributes` rules automatically on checkout.

### Fixing existing working copy after adding .gitattributes

If `.gitattributes` was added to a project that previously had CRLF files, run:

```bash
git add --renormalize .
git commit -m "fix: normalize line endings to LF"
```

This re-stages all tracked files through the new line ending rules without changing file content.

### Template for new projects

Copy the `.gitattributes` file from this project's root as a starting point. Adjust the file extension list to match your project's file types. The key rules to always include:

```
* text=auto eol=lf
*.sh text eol=lf
```

### Verification (B-12 Closure — Sprint 4, Story 13.2)

On 2026-02-20, all 29 CloudFormation parameter files in `infra/aws/cloudformation/parameters/dev/` were verified to have **LF line endings** (no CRLF found). The `.gitattributes` rules — the global `* text=auto eol=lf` and explicit `*.json text eol=lf` — are confirmed adequate. Verification included `git check-attr` confirmation that git applies `text: set` and `eol: lf` to parameter files. No additional rules needed.

**Background:** Sprint 3 Story 7-2 encountered a CRLF git warning when committing parameter files. Root cause was the Windows `core.autocrlf=true` setting, not corrupt file content. The `.gitattributes` file (commit `6a9bfd7`) and line ending normalization (commit `88b833e`) resolved the issue. This verification formally closes backlog item B-12.
