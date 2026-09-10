# ADR-027: Data-backed line-removal rules for portal cleanup

**Date:** 2026-09-10
**Status:** Proposed
**Decision makers:** Ziutus

## Context

Removing portal boilerplate ("Dalsza część tekstu pod materiałem wideo.",
"REKLAMA", cookie prompts, "Zobacz również:" teasers) from imported article
markdown is spread across five code-resident mechanisms:

| Mechanism | File | Kind |
|---|---|---|
| Generic + per-portal line cleanup | `backend/library/article_cleaner.py` | Python, context-aware |
| Simple per-domain string/regex removal | `backend/data/site_rules.json` | regex, applied at HTML download |
| Legacy per-site regex | `backend/library/website/website_text_clean_regexp.py` | regex |
| Full-article extraction patterns | `backend/data/pages_analyze/*.regex` | regex, one capture group |
| Manual `document_md_decode.py` replacements | `backend/document_md_decode.py` | literal `.replace()` |

`document_removed_lines` collects candidates (lines a reviewer deleted, whole
`SZUM`/`REKLAMA` chunks) and
[`docs/agent/document-removed-lines-workflow.md`](../agent/document-removed-lines-workflow.md)
turns them into rules — but the workflow's terminal step is always *edit a
file, add a test, open a PR, deploy*. A single new literal phrase on one portal
(the onet/forbes "tekstu" variant, [PR #631](https://github.com/ziutus/ai_assistant_lenie/pull/631))
costs the full branch → CI → merge → image rebuild → NAS deploy cycle, and
`main` branch protection makes the PR mandatory.

`site_rules.json` already has a partial escape hatch: the NAS reads it from
`/share/ContainerNew/lenie-config/site_rules.json` without a restart. But it is
still a file edited by hand, the repo stays the source of truth, there is no
self-service editing, and it does not reach the line-level rules that live in
`article_cleaner.py`.

The friction is real and it is concentrated in one rule shape: **"drop any line
equal to / containing this fixed phrase, globally or on this domain"**. That
shape is safe, high-volume, and does not belong in code.

## Decision

Add a `cleanup_rules` table for literal and simple-anchored line-removal rules,
loaded by the cleaner at runtime.

### Schema

| Column | Notes |
|---|---|
| `id` | PK |
| `scope` | `global` \| `domain` |
| `domain` | e.g. `www.onet.pl`; required when `scope='domain'`, matched against the document URL host |
| `match_type` | `literal_line` (whole stripped line equals, case-insensitive, after unwrapping `*_` and trailing `.:` ) \| `contains` (stripped line contains the phrase) \| `regex` (anchored, gated — see below) |
| `pattern` | the phrase or regex |
| `active` | bool; a bad rule is disabled, never deleted |
| `note` | free text — "forbes zajawka, dok. 10480" |
| `source_removed_line_id` | nullable FK to `document_removed_lines` — provenance |
| `created_by`, `created_at`, `hit_count`, `last_hit_at` | audit / usefulness signal |

### Runtime

- `article_cleaner._clean_lines_generic()` / per-portal cleaners and
  `website.webpage_text_clean()` consult an in-process cache of active rules
  (TTL ~60 s, or explicit bust on write) before their hard-coded checks.
- `literal_line` / `contains` rules run as plain string comparisons — no regex
  engine, cannot catastrophically backtrack, cannot match across lines.
- Every rule application increments `hit_count`; `hit_count = 0` after weeks is
  the signal a rule was wrong or the portal changed.

### Editing

- `GET/POST /cleanup_rules`, `PATCH/DELETE /cleanup_rules/<id>` (service key).
- A minimal panel in the web admin; until then, SQL on the NAS is enough.
- `/lenie-review-removed-lines` gains a "promote to rule" action: instead of
  emitting a code diff for the safe cases, it inserts a `cleanup_rules` row
  with `source_removed_line_id` set and marks the candidate `rule_added`.

### Scope boundary — what stays in code

- **Context-dependent logic** (skip a section between two markers, drop an H2
  because the next line is an image, keep a numbered line unless it has a
  bibliographic signal) stays in `article_cleaner.py` with unit tests.
- **`regex` rules in the table are gated**: on write, the pattern must be
  anchored (`^`/`$` or `\b`), compile within a time budget, and be tested
  against a stored corpus of known-good article paragraphs — a regex that
  matches any of them is rejected. Regex rules are the exception, not the norm;
  prefer `literal_line`.
- **Full-article extraction** (`pages_analyze/*.regex`) is out of scope — that
  is structural capture, not line removal.

## Consequences

- The common case — one portal emits a new boilerplate line — becomes one
  `INSERT` (or one button), live within a minute, no deploy, no PR. This is the
  point.
- New failure surface: a careless `contains` rule with a short phrase can eat
  real sentences. Mitigations: `literal_line` is the default and is
  whole-line; `contains` needs a minimum length; every rule carries provenance
  and an audit trail; `active=false` is instant rollback; `hit_count` surfaces
  overreach. The blast radius is still smaller than a bad regex in
  `site_rules.json` today, which ships with no telemetry at all.
- The repo stops being the sole source of truth for this rule class. This
  already happened for `site_rules.json` on the NAS; ADR-027 makes it
  deliberate and gives it structure (audit columns, provenance, an API)
  instead of a hand-edited file. A periodic `cleanup_rules` → fixture dump into
  the repo keeps the rules reviewable and testable in CI.
- Existing hard-coded rules are left in place; they can be migrated to rows
  opportunistically when the review workflow next touches them, not in a big
  bang.
- Ties into the broader "config out of code, jobs on the NAS" direction
  (`docs/deployment/nas/storage-and-jobs-migration-plan.md`).

## Implementation sketch

1. **Migration** `cleanup_rules` table (Alembic; grep
   `backend/alembic/versions/` for a free revision id first).
2. **`library/cleanup_rules.py`** — `load_active_rules(session)` +
   `_RuleCache` (TTL), `line_matches_rule(stripped, host, rules)`,
   `validate_rule(rule)` (the regex gate + known-good corpus check).
3. **Wire into `article_cleaner.py`**: in `_clean_lines_generic()` and the
   per-portal cleaners, after the cheap structural checks, `if
   line_matches_rule(...): bump hit_count; continue`. Pass the document `url`
   into `clean_article_text()` (already available at the call sites).
4. **Wire into `website/website_download_context.py:webpage_text_clean()`** for
   the download-time path.
5. **`library/cleanup_rules_routes.py`** — Blueprint, service-key only,
   cache-bust on write.
6. **`/lenie-review-removed-lines`** — add the promote-to-row branch + mark
   `rule_added` with `rule_reference = 'cleanup_rules:<id>'`.
7. **Tests**: `literal_line` / `contains` matching, host scoping, the regex
   validation gate rejecting a body-matching pattern, cache TTL, and the
   onet/forbes "tekstu" case reproduced as a row rather than code.
8. **Repo dump**: `imports/dump_cleanup_rules.py` →
   `tests/fixtures/cleanup_rules.json`, asserted in CI so live rules stay
   visible in review.
