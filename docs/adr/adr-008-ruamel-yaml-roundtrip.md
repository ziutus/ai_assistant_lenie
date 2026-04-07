# ADR-008: ruamel.yaml for Round-Trip YAML Preservation in Variable Classification SSOT

**Date:** 2026-02-27 (Sprint 6, Epic 20)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The `vars-classification.yaml` file was designed as the Single Source of Truth (SSOT) for all ~50 configuration variables in Project Lenie. This file defines variable classification (secret vs config), backend definitions, environment mappings, and per-variable metadata. It is both machine-written (by `env_to_vault.py` commands like `review --write` and `remove`) and human-read/edited (by developers managing the variable inventory).

Two Python YAML libraries were evaluated:
- **PyYAML** (`pyyaml`) — the de-facto standard Python YAML parser. Does not preserve comments, key ordering, or formatting during round-trip (load → modify → dump).
- **ruamel.yaml** — a YAML 1.2 parser that supports round-trip preservation of comments, key order, block/flow style, and whitespace.

### Decision

Use **`ruamel.yaml>=0.18`** instead of `pyyaml` for all YAML operations in `env_to_vault.py`.

### Rationale

1. **Comment preservation is critical.** The SSOT file contains inline comments explaining variable purpose, bootstrap group semantics, and backend-specific notes. Machine writes (adding/removing variables) must not destroy these human-authored comments. PyYAML silently strips all comments on dump.

2. **Key ordering matters for readability.** Variables are grouped logically (database, AI, auth, bootstrap). PyYAML's default `dump()` sorts keys alphabetically, destroying the logical grouping. ruamel.yaml preserves insertion order.

3. **Formatting stability.** When `review --write` adds a new variable to the YAML, only the added section should change. PyYAML reformats the entire file, making diffs noisy and code review difficult.

4. **No performance concern.** The SSOT file is ~200 lines with ~50 variable entries. Round-trip parsing overhead is negligible at this scale.

5. **Lazy import pattern.** ruamel.yaml is loaded via `_require_ruamel()` only when YAML commands are invoked, following the existing pattern for hvac and boto3. Scripts that don't use YAML commands pay no import cost.

### Consequences

- **Positive:** Human-authored comments and formatting survive machine writes — SSOT file remains readable and maintainable.
- **Positive:** Git diffs show only actual changes, not formatting noise.
- **Positive:** YAML 1.2 compliance (ruamel.yaml) vs YAML 1.1 (PyYAML) — better standard adherence.
- **Negative:** Additional dependency (~300 KB) in `backend/pyproject.toml`.
- **Negative:** Slightly different API than PyYAML (`YAML()` instance vs module-level `yaml.safe_load()`), requiring developers to learn the ruamel.yaml idiom.

### Related Artifacts

- `_bmad-output/implementation-artifacts/tech-spec-env-to-vault-compare-review-classify.md` — tech-spec requiring ruamel.yaml
- `scripts/env_to_vault.py` — consumer (YAML loader infrastructure, Task 3)
- `scripts/vars-classification.yaml` — the SSOT file that benefits from round-trip preservation
- `backend/pyproject.toml` — dependency declaration (Task 1)
