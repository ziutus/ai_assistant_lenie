# Development Guide

> Generated: 2026-02-13 | Project: lenie-server-2025

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | >= 3.11 | Backend runtime |
| uv | latest | Python package manager |
| Node.js | >= 22 (recommended: 24 LTS) | Frontend build |
| npm/yarn | latest | Frontend package manager |
| Docker + Docker Compose | latest | Local development stack |
| PostgreSQL | 18 | Database (via Docker or standalone) |
| Git | latest | Version control |

## Recommended Local Tools

Development tools installed on the developer's Windows machine:

| Tool | Version | Install | Purpose |
|------|---------|---------|---------|
| `psql` | 18.3 | [PostgreSQL 18 installer](https://www.postgresql.org/download/windows/) | Direct database access (NAS, AWS RDS) |
| `uv` | latest | `pip install uv` or [installer](https://docs.astral.sh/uv/) | Python package & project manager |
| `uvx` | (part of uv) | — | Run Python tools without installing (pytest, ruff) |
| `ruff` | latest | `uvx ruff` | Python linter & formatter |
| `pre-commit` | latest | `uv tool install pre-commit` | Git pre-commit hooks (secret detection) |
| `docker` | latest | [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Container builds, local stack |
| `gh` | latest | `winget install GitHub.cli` | GitHub CLI (PRs, issues) |

### PostgreSQL client tools (`psql`)

Installed at `C:\Program Files\PostgreSQL\18\bin\`. Not in PATH by default in Git Bash.

```bash
# Connect to NAS database
PGPASSWORD=postgres "/c/Program Files/PostgreSQL/18/bin/psql.exe" -h 192.168.200.7 -p 5434 -U postgres -d lenie-ai

# Or add to PATH (add to ~/.bashrc):
export PATH="/c/Program Files/PostgreSQL/18/bin:$PATH"
```

Other useful tools from the PostgreSQL package:
- `pg_dump` — database export/backup
- `pg_restore` — database import/restore
- `createdb` / `dropdb` — database management

### WSL tools

For scripts requiring Linux (deploy, imports):
- `ssh` — NAS access (`admin@192.168.200.7`)
- `scp` — file transfer to/from NAS
- `uv` — Python package manager (`~/.local/bin/uv`)

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

### Note on PYTHONPATH

Older documentation and some files may reference `PYTHONPATH=. python -m ...` when running backend scripts. This is **no longer necessary**. The project's `pyproject.toml` now includes a `[tool.hatch.build.targets.wheel]` section that tells hatchling which directories are Python packages:

```toml
[tool.hatch.build.targets.wheel]
packages = ["library", "imports"]
```

After `uv sync`, the project is installed as an editable package and Python resolves `library` and `imports` modules automatically. You can run scripts directly:

```bash
cd backend
./imports/unknown_news_import.py --help
./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
```

### WSL: Separate Virtual Environment Required

The Windows `.venv` (`backend/.venv/`) **cannot be shared with WSL**. Python virtual environments are platform-specific — compiled packages (e.g., `psycopg2-binary`) produce `.pyd` files on Windows and `.so` files on Linux, and `pyvenv.cfg` stores an absolute path to the system interpreter.

If you need to run backend scripts (e.g., `imports/unknown_news_import.py`) from WSL, create a separate venv:

```bash
cd /mnt/c/Users/<user>/git/_lenie-all/lenie-server-2025/backend
uv venv .venv_wsl
source .venv_wsl/bin/activate
uv sync --active
./imports/unknown_news_import.py --help
```

> **Why `--active`?** `uv sync` defaults to the project's `.venv` directory. Without `--active`, uv ignores the activated `.venv_wsl` and installs into `.venv` instead.

> **Expected warning:** When WSL accesses files on a Windows filesystem (`/mnt/c/...`), uv may print: `warning: Failed to hardlink files; falling back to full copy`. This is normal — hardlinks don't work across the Linux/Windows filesystem boundary. Installation still completes correctly, just slower. The fix is in the "WSL: Final Bash Setup" section below.

> **Note:** `.venv_wsl/` is already covered by `.gitignore` (`.venv*` pattern). Do not attempt to reuse the Windows `.venv/` from WSL — it will fail with `ModuleNotFoundError` for compiled packages.

### WSL: Keeping `.venv_wsl` in Sync

`.venv_wsl` is a **separate environment** that is not updated automatically when you change `pyproject.toml` or lock files on Windows. After any dependency change (adding/removing packages, adding path dependencies like `shared_python/`), you must sync `.venv_wsl` manually:

```bash
# Full sync from lock file (recommended after pyproject.toml changes)
cd /mnt/c/Users/<user>/git/_lenie-all/lenie-server-2025/backend
source .venv_wsl/bin/activate
uv sync --active

# Or install a specific new path dependency
uv pip install -e ../shared_python/unified-config-loader/ --python .venv_wsl/bin/python
```

**When to sync:**
- After running `uv lock` on Windows (changed `pyproject.toml`)
- After adding/removing a path dependency (e.g., `shared_python/`)
- After pulling changes that modify `uv.lock`

**Quick verification:**
```bash
.venv_wsl/bin/python -c "from library.config_loader import load_config; print('OK')"
```

### WSL: Final Bash Setup

Add the following lines to your `~/.bashrc` (or `~/.zshrc`):

```bash
# --- Lenie project: WSL settings ---
# Suppress uv hardlink warning (hardlinks don't work across Windows/Linux filesystem boundary)
export UV_LINK_MODE=copy
```

Then reload your shell: `source ~/.bashrc`

### WSL: Project Location and IDE Considerations

**Keep the project on the Windows filesystem** (`/mnt/c/...`), not on the native WSL filesystem (`/home/<user>/...`).

While the native Linux filesystem offers 5-10x faster I/O for shell operations (`git status`, `uv sync`, `npm install`), IDEs running on Windows access it through the `\\wsl$\` network bridge (9P protocol), which reverses the performance advantage:

| Setup | Shell I/O | IDE indexing | IDE editing |
|-------|-----------|-------------|-------------|
| Project on `/mnt/c/` (Windows FS) | moderate | fast | fast |
| Project on `/home/` (Linux FS) | fast | **slow** (via `\\wsl$\`) | noticeable lag |

**PyCharm** supports WSL interpreters natively (Settings → Project → Python Interpreter → Add → WSL), so you can use the `.venv_wsl` interpreter while keeping files on the Windows filesystem. This gives the best of both worlds: fast IDE performance with access to Linux Python environment when needed.

**VS Code** with the "Remote - WSL" extension works better with the native Linux filesystem (its server runs inside WSL), but since the project uses PyCharm, moving the repo is not recommended.

**Recommended workflow:** Project on `/mnt/c/`, PyCharm with Windows interpreter for daily development, WSL with `.venv_wsl` only for running scripts that require Linux (deploy scripts, shell scripts, import scripts).

### Running

```bash
# Direct execution (requires .env in backend/)
python server.py

# Via Docker
make build && make dev
```

### Testing

```bash
# Full test suite
pytest

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

> **Remember:** After changing dependencies, also sync `.venv_wsl` if you use WSL. See [WSL: Keeping .venv_wsl in Sync](#wsl-keeping-venv_wsl-in-sync).

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
- **Database**: SQLAlchemy ORM (see [ADR-004a](architecture-decisions.md#adr-004a-migrate-to-sqlalchemy-orm--pydantic-schemas))
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

## Claude Code — MCP Servers Setup

The project uses [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers to give Claude Code direct access to AWS services. Configuration is in `.mcp.json`.

### Configured MCP servers

| Server | Purpose |
|--------|---------|
| `awslabs.aws-iac-mcp-server` | CloudFormation template validation, compliance checking, CDK docs |
| `awslabs.cfn-mcp-server` | Read/list AWS resources by CloudFormation type (readonly) |
| `awslabs.aws-api-mcp-server` | Execute AWS API calls (read-only mode) |
| `gitguardian` | Secret detection and remediation |

### Prerequisites

1. **Install `uv`** (Python package manager): https://docs.astral.sh/uv/getting-started/installation/

2. **Install MCP servers as persistent tools** (one-time setup):

```bash
uv tool install awslabs.aws-iac-mcp-server
uv tool install awslabs.cfn-mcp-server
uv tool install awslabs.aws-api-mcp-server
```

> **Why not `uv tool run --from ...@latest`?** The `@latest` variant downloads packages on every start (~23s), which combined with server startup time (~10s) exceeds Claude Code's default 30-second MCP connection timeout. Pre-installing eliminates the download step.

3. **Set MCP connection timeout** — the default 30 seconds is too short for these servers on Windows:

**Windows (permanent, recommended):**
```cmd
setx MCP_TIMEOUT 60000
```

**Linux/macOS (add to `~/.bashrc` or `~/.zshrc`):**
```bash
export MCP_TIMEOUT=60000
```

After setting the variable, restart your terminal and Claude Code.

### Updating MCP servers

To update to the latest versions:

```bash
uv tool upgrade awslabs.aws-iac-mcp-server
uv tool upgrade awslabs.cfn-mcp-server
uv tool upgrade awslabs.aws-api-mcp-server
```

### Troubleshooting

If MCP servers fail to connect, check the debug logs:

```bash
# Latest debug log (look for "timeout" or "Connection failed")
cat ~/.claude/debug/latest
```

Common issues:
- **Connection timeout**: Increase `MCP_TIMEOUT` (e.g., `90000` for 90s)
- **Command not found**: Verify installation with `uv tool list` — all three `awslabs-*` servers should be listed
- **AWS credentials**: Servers use `AWS_PROFILE=default` and `AWS_REGION=eu-central-1` (configured in `.mcp.json` env)

## Future: LLM Text Analysis (Phase 6)

> **Status:** Backlog — po MVP (Security, MCP Server, Obsidian), przed Multiuser.

Automatyczna analiza tekstu dokumentów przez LLM, zwracająca ustrukturyzowany JSON z metadanymi. Backlog items (B-29 do B-32) w `_bmad-output/implementation-artifacts/sprint-status.yaml`.

### Zakres

| Backlog ID | Opis |
|------------|------|
| B-29 | Endpoint analizy tekstu przez LLM — ekstrakcja metadanych do JSON (autor, temat, państwa, źródło, osoby, organizacje) |
| B-30 | Schemat JSON analizy i przechowywanie w bazie — kolumna JSONB lub dedykowana tabela, indeksy GIN |
| B-31 | UI wyników analizy — wyświetlanie, edycja, filtrowanie listy dokumentów po metadanych |
| B-32 | Batch analysis istniejących dokumentów — skrypt przetwarzający + integracja ze Step Function/SQS |

### Wpływ na architekturę

- **Baza danych:** Nowa kolumna `ai_analysis` (JSONB) w `web_documents` lub dedykowana tabela `web_documents_analysis`. Indeksy GIN do wyszukiwania po polach JSON.
- **Backend (Flask / Lambda):** Nowy endpoint + prompt ekstrakcyjny. Wykorzystanie istniejącej konfiguracji `LLM_PROVIDER` (OpenAI, Bedrock, Vertex).
- **Pipeline:** Nowe statusy dokumentu (`ANALYSIS_NEEDED` → `ANALYSIS_DONE`) w `stalker_document_status.py`.
- **Frontend:** Sekcja analizy na stronie edycji dokumentu + filtry na liście.

## Future: Multiuser Support (Phase 7)

> **Status:** Backlog — planowane na samym końcu, po zakończeniu wszystkich faz łącznie z LLM Text Analysis.

Sekcja multiuser umożliwi korzystanie z systemu przez wielu użytkowników na infrastrukturze AWS. Backlog items (B-23 do B-28) w `_bmad-output/implementation-artifacts/sprint-status.yaml`.

### Zakres

| Backlog ID | Opis |
|------------|------|
| B-23 | Uwierzytelnianie użytkowników — AWS Cognito User Pool (rejestracja, logowanie, JWT) |
| B-24 | Własność danych w bazie — kolumna `user_id` w `web_documents` i `websites_embeddings`, migracja istniejących danych |
| B-25 | Izolacja danych per użytkownik — filtrowanie po `user_id` we wszystkich endpointach API |
| B-26 | Zamiana `x-api-key` na tokeny Cognito — aktualizacja API Gateway (Cognito Authorizer) i wszystkich klientów |
| B-27 | UI logowania/wylogowania — ekrany auth w React SPA, Chrome extension i Add URL app |
| B-28 | Panel administracyjny — zarządzanie użytkownikami, statystyki per użytkownik |

### Wpływ na architekturę

- **API Gateway:** Cognito Authorizer zamiast API Key auth
- **Baza danych:** Nowa kolumna `user_id` + indeksy, RLS (Row Level Security) lub filtrowanie w warstwie aplikacji
- **Backend (Flask / Lambda):** Ekstrakcja `user_id` z JWT tokena, przekazywanie do zapytań SQL
- **Frontend:** Integracja z Cognito (Amplify Auth lub aws-amplify SDK), obsługa sesji i odświeżania tokenów
- **Chrome extension:** Zastąpienie pola API key logowaniem Cognito
