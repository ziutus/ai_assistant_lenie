# Python Dependencies

Managing Python dependencies with **uv** package manager.

> **Parent document:** [../CLAUDE.md](../CLAUDE.md) — full architecture reference.

## Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows:
```
pip install uv
```

## Quick Start with Makefile

```bash
make install          # Install base dependencies
make install-all      # Install all dependencies (including optional)
make install-docker   # Install docker dependencies only
make lock             # Update uv.lock after changing pyproject.toml
```

## Manual Usage

```bash
cd backend
uv sync                    # Install base dependencies
uv sync --all-extras       # Install all optional dependencies
uv sync --extra docker     # Install specific extra
uv lock                    # Update lock file
```

## Project Configuration

Dependencies are managed via `backend/pyproject.toml` with optional dependency groups:
- Base dependencies (server)
- `[docker]` - Minimal dependencies for Docker image
- `[markdown]` - Markdown processing tools
- `[all]` - All dependencies including Google APIs, AWS tools, etc.
