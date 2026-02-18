# Architecture Decision Records (ADR)

> Living document tracking key architectural decisions in Project Lenie.

## ADR-001: Remove `/translate` Endpoint and Use Native-Language Embeddings

**Date:** 2026-02 (Sprint 3, Epic 10)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The `/translate` endpoint was introduced in the early development phase when the system relied on embedding models that only supported English text (e.g., OpenAI `text-embedding-ada-002`, AWS Titan Embed v1). Since the majority of collected documents are in Polish, a translation step was required before embedding generation. The processing pipeline reflected this: documents moved through `READY_FOR_TRANSLATION` (state 8) before reaching `READY_FOR_EMBEDDING` (state 9).

Over time, multilingual embedding models became available and were integrated into the system:
- **AWS Titan Embed v2** (`amazon.titan-embed-text-v2:0`) — improved multilingual support
- **CloudFerro Bielik/BGE** (`BAAI/bge-multilingual-gemma2`) — native Polish embedding support

The `ai_model_need_translation_to_english(model)` helper function in `backend/library/ai.py` already handled model-specific translation requirements, but the `/translate` endpoint itself was broken — the backend module `library.translate` did not exist, making the endpoint non-functional.

### Decision

1. **Remove the `/translate` endpoint** from all layers (Lambda, API Gateway, React frontend).
2. **Adopt native-language embeddings** as the standard approach — documents are embedded in their original language (primarily Polish) without prior translation.
3. **Keep `READY_FOR_TRANSLATION` status** in the document processing pipeline for backward compatibility with existing database records.

### Rationale

1. **Translation is interpretation.** Translating text before embedding introduces semantic distortion. The system should not interpret or alter the user's content without explicit consent. Embedding the original text preserves the author's exact meaning, nuance, and context.

2. **No practical duplication risk.** In theory, skipping translation could cause duplicate detection issues when the same content exists in multiple languages (their embeddings would differ). However, this risk is irrelevant for Project Lenie's use case — the system processes news articles, books, and social media messages (Facebook, Twitter). The same article is not collected in multiple languages.

3. **Quality improvement.** Modern multilingual embedding models produce high-quality vector representations for Polish text. Removing the translation step eliminates a source of information loss and latency.

4. **Dead code cleanup.** The endpoint was already broken (missing backend module). Removing it reduces confusion and maintenance burden.

### Consequences

- **Positive:** Simpler pipeline, no translation cost/latency, preserves original text semantics, fewer moving parts.
- **Positive:** Eliminates dependency on translation service availability.
- **Negative:** `READY_FOR_TRANSLATION` status still exists in the pipeline enum — requires future cleanup or repurposing.
- **Negative:** The `ai_model_need_translation_to_english()` function still exists for models that may require English input — not all models are equal.

### Related Artifacts

- Story 10.2: Remove `/translate` endpoint
- Story 12.1: Codebase-wide stale reference verification
- `backend/library/ai.py:17` — `ai_model_need_translation_to_english()`
- `backend/library/models/stalker_document_status.py:13` — `READY_FOR_TRANSLATION` state
- `backend/library/embedding.py` — Embedding provider abstraction

---

## ADR-002: API Gateway as Security Boundary (No NAT Gateway)

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted

### Context

The system needed internet-facing API access for mobile devices (Chrome extension on phone/tablet) while keeping infrastructure costs minimal (hobby project, $8/month budget target).

### Decision

Use AWS API Gateway as the single entry point with API key authentication. No NAT Gateway (saves ~$30/month). Lambda functions split into VPC (database access) and non-VPC (internet access) to work around the missing NAT Gateway.

### Consequences

- **Positive:** Fully managed TLS, throttling, DDoS protection. No servers to patch.
- **Positive:** ~$30/month saved on NAT Gateway.
- **Negative:** Lambda functions must be split between VPC and non-VPC, adding architectural complexity.
- **Negative:** Some endpoints exist only in `server.py` (Docker/K8s) and not in Lambda.

---

## ADR-003: DynamoDB as Cloud-Local Synchronization Buffer

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted

### Context

Documents are submitted from mobile devices at any time, but the PostgreSQL RDS database runs only on demand (cost optimization). A persistent, always-available store was needed to buffer incoming documents.

### Decision

Use DynamoDB (PAY_PER_REQUEST) to immediately store document metadata from mobile submissions. S3 stores the full content. The local PostgreSQL database synchronizes from DynamoDB/S3 when needed.

### Consequences

- **Positive:** Documents are never lost — DynamoDB is always available regardless of RDS state.
- **Positive:** Enables asynchronous processing via SQS when RDS starts.
- **Negative:** Two data stores to manage, potential sync issues.

---

## ADR-004: Raw psycopg2 Instead of ORM

**Date:** 2025 (initial development)
**Status:** Accepted

### Context

The project needed PostgreSQL access with pgvector extension support for vector similarity search.

### Decision

Use raw `psycopg2` queries instead of an ORM (SQLAlchemy, Django ORM). Custom domain model classes (`StalkerWebDocument`, `StalkerWebDocumentDB`) handle persistence directly.

### Consequences

- **Positive:** Full control over queries, especially pgvector-specific operations (cosine similarity search with IVFFlat index).
- **Positive:** Simpler dependency tree, no ORM abstraction overhead.
- **Negative:** Manual SQL query construction, no migration framework, schema changes require manual DDL scripts.
