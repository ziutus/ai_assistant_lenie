# ADR-001: Remove `/translate` Endpoint and Use Native-Language Embeddings

**Date:** 2026-02 (Sprint 3, Epic 10); cleanup completed 2026-07-22
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The `/translate` endpoint was introduced in the early development phase when the system relied on embedding models that only supported English text (e.g., OpenAI `text-embedding-ada-002`, AWS Titan Embed v1). Since the majority of collected documents are in Polish, a translation step was required before embedding generation. The processing pipeline reflected this: documents moved through `READY_FOR_TRANSLATION` (state 8) before reaching `READY_FOR_EMBEDDING` (state 9).

Over time, multilingual embedding models became available and were integrated into the system:
- **AWS Titan Embed v2** (`amazon.titan-embed-text-v2:0`) — improved multilingual support
- **CloudFerro Bielik/BGE** (`BAAI/bge-multilingual-gemma2`) — native Polish embedding support

The removed implementation left compatibility-only workflow values and a helper classifying some
LLMs as requiring English. No active production path consumed those values.

### Decision

1. **Remove the `/translate` endpoint** from all layers (Lambda, API Gateway, React frontend).
2. **Adopt native-language embeddings** as the standard approach — documents are embedded in their original language (primarily Polish) without prior translation.
3. **Remove the obsolete translation workflow contract**: `READY_FOR_TRANSLATION`, five translation
   error codes and the unused model helper. Historical rows are normalized by Alembic migration
   `d18f4a6b2c7e`.
4. **Do not offer an English-only embedding model** without a translation pipeline. The
   English-only `dunzhang/stella_en_1.5B_v5` is no longer available for new embeddings; historical
   vectors remain readable because their model name stays valid in the database lookup.

### Rationale

1. **Translation is interpretation.** Translating text before embedding introduces semantic distortion. The system should not interpret or alter the user's content without explicit consent. Embedding the original text preserves the author's exact meaning, nuance, and context.

2. **No practical duplication risk.** In theory, skipping translation could cause duplicate detection issues when the same content exists in multiple languages (their embeddings would differ). However, this risk is irrelevant for Project Lenie's use case — the system processes news articles, books, and social media messages (Facebook, Twitter). The same article is not collected in multiple languages.

3. **Quality improvement.** Modern multilingual embedding models produce high-quality vector representations for Polish text. Removing the translation step eliminates a source of information loss and latency.

4. **Dead code cleanup.** The endpoint was already broken (missing backend module). Removing it reduces confusion and maintenance burden.

### Consequences

- **Positive:** Simpler pipeline, no translation cost/latency, preserves original text semantics, fewer moving parts.
- **Positive:** Eliminates dependency on translation service availability.
- **Positive:** Documents cannot become stuck in an unreachable translation state.
- **Positive:** Translation failures no longer pollute the active error taxonomy.
- **Negative:** Supporting a future English-only market/model requires a new, explicit translation
  job rather than reusing `Document.processing_status`.

### Related Artifacts

- Story 10.2: Remove `/translate` endpoint
- Story 12.1: Codebase-wide stale reference verification
- `backend/alembic/versions/d18f4a6b2c7e_remove_translation_processing_states.py`
- `backend/library/embedding.py` — Embedding provider abstraction
