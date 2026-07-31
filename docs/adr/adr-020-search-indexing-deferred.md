# ADR-020: Search Indexing — Defer `pg_trgm` GIN and HNSW, With Explicit Revisit Thresholds

**Date:** 2026-07-19
**Status:** Accepted (revisit at stated thresholds)
**Decision Makers:** Ziutus
**Full analysis:** [search-hybrid.md](../search-hybrid.md#wydajność--pomiary-i-decyzje-etapu-12-2026-07-19-nas-9220-dokumentów--3062-embeddingi)

### Context

Stage 12 of the search rebuild (`docs/search-rebuild-implementation-plan.md`)
measured `EXPLAIN (ANALYZE)` for `POST /search` on NAS production data (9220
documents, 3062/3048 embeddings) to decide whether the lexical and vector legs
of `SearchService.search()` need new indexes. Two mechanisms were evaluated
for indexing:

1. **Lexical leg** — `unaccent(...) ILIKE` scan over title/tags/note/text:
   measured at 1404 ms (sequential scan).
2. **Vector leg** — `<=>` similarity against `BAAI/bge-multilingual-gemma2`
   embeddings: measured at 207 ms (sequential scan).

### Decision

**Do not add indexes now; keep both legs as sequential scans**, with explicit
numeric thresholds that trigger revisiting this decision.

1. **Lexical: stay on `ILIKE`, no `pg_trgm` GIN index.**
   - Revisit when: lexical leg exceeds **3 s**, or the corpus exceeds
     **25,000 documents**.
   - When triggered: add a `pg_trgm` GIN index using an `immutable_unaccent()`
     wrapper (`unaccent()` itself is `STABLE`, not usable directly in an
     index expression) over the same expression as `search_text()` — this
     preserves substring-match semantics rather than switching to full FTS
     (`tsvector`), which would need a Polish stemmer (Morfologik/ispell) to
     avoid degrading match quality.

2. **Vector: no HNSW index for the active embedding model.**
   - `BAAI/bge-multilingual-gemma2` has **3584 dimensions**, above pgvector's
     2000-dimension limit for HNSW on the `vector` type — this is why HNSW
     indexes (`idx_emb_*`) exist only for older, smaller-dimension models.
   - Revisit when: gemma2 embeddings exceed **25,000 rows**, or the vector
     leg exceeds **1 s**.
   - When triggered: build HNSW over `embedding::halfvec(3584)` (pgvector
     ≥ 0.7 supports up to 4000 dimensions for `halfvec`), which requires
     rewriting `get_similar()`'s query expression to match the index
     (`embedding::halfvec(3584) <=> query::halfvec(3584)`) and accepting
     fp16 precision loss.

### Rationale

- **The lexical leg's 1.4 s is not the latency bottleneck.** `/search`
  latency is dominated by remote embedding generation for the query itself
  (~5 s via CloudFerro) — see the stage-0 baseline in
  [ADR-017](adr-017-search-rebuild-scope-decisions.md). Speeding up SQL at
  today's corpus size would not be user-perceptible.
- **Premature FTS would cost semantics, not just engineering time.** A GIN
  index over full book-length text would be large and slow to build; plain
  `tsvector` FTS without Polish stemming would degrade the substring-match
  behavior the current `ILIKE` approach already provides (see "Known
  limitations" in `search-hybrid.md`).
- **HNSW is architecturally blocked at the current vector width**, not just
  deferred by choice — pgvector's 2000-dim HNSW limit makes `halfvec` a
  precision trade-off (fp16) to actively decide on later, not something to
  reach for preemptively.
- **Numeric thresholds, not vague "revisit later.".** Both decisions are
  paired with a concrete corpus-size or latency trigger so a future session
  doesn't have to re-derive whether revisiting is warranted from scratch.

### Consequences

- **Positive:** No new index-maintenance cost or build-time risk at current
  scale (9220 documents / ~3050 embeddings).
- **Positive:** Revisit triggers are numeric and checkable via the same
  `EXPLAIN (ANALYZE)` methodology used here, not subjective judgment calls.
- **Negative:** Both legs remain sequential scans — write-heavy growth in
  document/embedding count degrades `/search` linearly until a threshold is
  hit and the deferred work is done.
- **Deferred:** `pg_trgm` GIN (lexical) and HNSW-over-`halfvec` (vector) are
  the documented next steps, not implemented today.

### Related Artifacts

- [search-hybrid.md](../search-hybrid.md) — full measurement table and
  narrative for both decisions
- [search-rebuild-progress.md](../search-rebuild-progress.md) — Stage 12
  journal entry (2026-07-19) recording the same decisions inline
- [ADR-017](adr-017-search-rebuild-scope-decisions.md) — stage-0 scope
  decisions and the `/website_similar` latency baseline this compares against
- [ADR-009](adr-009-postgresql-search-strategy.md) — original `unaccent` +
  `pg_trgm` strategy decision for structured-field search (this ADR only
  concerns indexing the free-text `ILIKE` leg, not that decision)
- `backend/library/search_service.py`, `backend/library/document_repository.py`
  (`search_text()`), `backend/library/document_repository.py` (`get_similar()`)
  — implementation
