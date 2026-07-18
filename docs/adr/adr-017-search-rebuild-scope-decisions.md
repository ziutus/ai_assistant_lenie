# ADR-017: Search Rebuild — Scope Decisions and Baseline (Stage 0)

**Date:** 2026-07-18
**Status:** Accepted
**Decision Makers:** Ziutus
**Plan:** [search-rebuild-implementation-plan.md](../search-rebuild-implementation-plan.md)

## Context

The search rebuild (natural-language Polish queries interpreted by Bielik 11B into
explicit, validated search intents) requires three upfront decisions before any
schema work can start, plus a recorded baseline of the current `/website_similar`
behaviour. This ADR closes stage 0 of the plan.

## Decisions

### 1. Target naming dictionary — approved as proposed

The dictionary in section 3 of the plan is approved without changes
(`documents`, `document_id`, `published_on`, `byline`, `discovery_source_id`,
`collection_id`, `subject_period_start/end_year`, `public_id`,
`processing_status`, `search` endpoint, etc.). New domain names are used in the
API and in new code from the start; physical table/column renames are deferred
to stage 11.

### 2. Collection is a 1:N relation (`collection_id`)

A document belongs to at most one collection. Evidence: as of 2026-07-18 the
existing `web_documents.project` column is **100% NULL across all 9220
documents** on the production NAS database — there is no existing usage that
would justify an M:N join table. Moving from 1:N to M:N later is a lossless
migration, the reverse is not; start simple.

### 3. Search-log retention: 90 days

`search_interpretation_logs` rows get `expires_at = created_at + 90 days`.
Rationale: raw user queries may contain private data; 90 days is enough to
analyse parser mistakes and collect corrections, after which rows are eligible
for cleanup. Feedback aggregates that should outlive the raw rows must be
derived before expiry (stage 10 evaluation reports are stored separately).

## Baseline (recorded 2026-07-18)

### Current behaviour of `POST /website_similar` (NAS, production data)

Request payload key is `search` (not `text`); optional `limit`,
`period_from`, `period_to`. Measured on NAS (`192.168.200.7:5055`, Docker
backend, warm service), `limit=10`, two runs per query:

| Query | Run 1 | Run 2 |
|---|---:|---:|
| "niewolnictwo w Afryce" | 5.90 s | 6.21 s |
| "wojna w Ukrainie" | 6.98 s | 6.91 s |
| "pompy ciepła" | 5.99 s | 6.10 s |

All returned HTTP 200 with 10 results. Latency is dominated by remote
embedding generation (CloudFerro `BAAI/bge-multilingual-gemma2`); the SQL part
is negligible at this corpus size. Stage-12 performance work should be compared
against these numbers, and stage 6 (filter-only search without embedding
generation) should come in well under 1 s.

### Current tests

`tests/unit/test_search_service.py` + `tests/unit/test_similarity_search_orm.py`:
30 passed (1.17 s) on `main` at commit `2e8c112`.

### Evaluation corpus

43 representative Polish queries with partial expected `ParsedSearchQuery`
objects live in
[`backend/tests/fixtures/search_query_cases.json`](../../backend/tests/fixtures/search_query_cases.json),
schema-pinned by `tests/unit/test_search_query_cases_fixture.py`. Categories:
plain topic, subject period (incl. BCE and anchored expressions), publication
date, ingestion date, author, publisher, discovery source, document type,
language, combined, adversarial (prompt injection), fallback, clarification,
and validation (reversed ranges). The corpus feeds parser tests (stage 4) and
the real-Bielik evaluation (stage 10).

## Consequences

- Stage 2 migrations can reference `collection_id` semantics and a 90-day
  `expires_at` without further consultation.
- All new code and API contracts use the approved names immediately; code that
  still maps to old SQL names must do so only at the ORM layer.
- The fixture file is a stable contract: schema changes to it require updating
  the pinned tests deliberately, not incidentally.
