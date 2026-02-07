CONTAINER_NAME=lenie


# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'

default:	help

help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

# Everything below is an example

build:          ## Builds docker containers
	docker compose build

dev:            ## Runs backend and frontend
	docker compose up -d

down:           ## Stops and removes containers
	docker compose down -v

# Python dependency management with uv
install:        ## Install base dependencies using uv
	cd backend && uv sync

install-all:    ## Install all dependencies (including optional)
	cd backend && uv sync --all-extras

install-docker: ## Install docker dependencies only
	cd backend && uv sync --extra docker

install-markdown: ## Install markdown dependencies only
	cd backend && uv sync --extra markdown

lock:           ## Update uv.lock file
	cd backend && uv lock

sync:           ## Sync dependencies from lock file
	cd backend && uv sync

# Code quality
lint:           ## Run ruff linter
	cd backend && uv run ruff check .

lint-fix:       ## Run ruff linter with auto-fix
	cd backend && uv run ruff check . --fix

format:         ## Format code with ruff
	cd backend && uv run ruff format .

format-check:   ## Check code formatting (no changes)
	cd backend && uv run ruff format . --check

# Security (all tools use uvx - no installation to project venv)
security:       ## Run semgrep security scan
	uvx semgrep --config=auto backend/

security-deps:  ## Check dependencies for vulnerabilities (pip-audit)
	cd backend && uvx pip-audit

security-bandit: ## Run bandit Python security linter
	uvx bandit -r backend/ -x backend/tests

security-safety: ## Check dependencies with safety
	cd backend && uvx safety scan

security-all:   ## Run all security checks
	@echo "=== Running Semgrep ==="
	-uvx semgrep --config=auto backend/
	@echo ""
	@echo "=== Running pip-audit ==="
	-cd backend && uvx pip-audit
	@echo ""
	@echo "=== Running Bandit ==="
	-uvx bandit -r backend/ -x backend/tests
	@echo ""
	@echo "=== Running Safety ==="
	-cd backend && uvx safety scan
	@echo ""
	@echo "=== Security checks complete ==="
