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
**Status:** Superseded by ADR-004a

### Context

The project needed PostgreSQL access with pgvector extension support for vector similarity search.

### Decision

Use raw `psycopg2` queries instead of an ORM (SQLAlchemy, Django ORM). Custom domain model classes (`StalkerWebDocument`, `StalkerWebDocumentDB`) handle persistence directly.

### Consequences

- **Positive:** Full control over queries, especially pgvector-specific operations (cosine similarity search with IVFFlat index).
- **Positive:** Simpler dependency tree, no ORM abstraction overhead.
- **Negative:** Manual SQL query construction, no migration framework, schema changes require manual DDL scripts.

---

## ADR-004a: Migrate to SQLAlchemy ORM + Pydantic Schemas

**Date:** 2026-03
**Status:** Accepted (supersedes ADR-004)

### Context

The raw psycopg2 approach (ADR-004) proved increasingly painful as the schema grew. Adding a single column required manual changes in 5+ places: SELECT column list, INSERT statement, UPDATE columns, `dict()` serialization, `__clean_values()`, and the domain model constructor. This violated DRY and was error-prone.

Additionally, the project needs:
- **OpenAPI schema generation** for automatic TypeScript type generation ([B-50](#b-50-api-type-synchronization-pipeline-pydantic--openapi--typescript))
- **Structured AI outputs** — Pydantic models as response format for LLM calls (OpenAI, Bedrock, Vertex AI)
- **Schema migration management** — currently using raw DDL scripts with no versioning

### Decision

Adopt a two-layer architecture:

1. **SQLAlchemy 2.x ORM** — database access layer. Declarative models define the schema once; SQLAlchemy generates all SQL (SELECT, INSERT, UPDATE, DELETE). Alembic manages schema migrations.
2. **Pydantic v2 schemas** — API serialization and validation layer. Separate from ORM models. Used for Flask API responses, OpenAPI generation, and structured AI outputs.

Key technology choices:
- **SQLAlchemy 2.x** with `mapped_column()` declarative style
- **pgvector-python** for `Vector()` column type and `cosine_distance()` operator
- **Alembic** for migration management
- **Pydantic v2** for API response schemas (not SQLModel — separation of DB and API concerns is cleaner)

### Consequences

- **Positive:** Adding a column = one field in the ORM model. SQL is generated automatically.
- **Positive:** Alembic auto-generates migration scripts from model changes.
- **Positive:** Pydantic schemas enable OpenAPI → TypeScript pipeline ([B-50](#b-50-api-type-synchronization-pipeline-pydantic--openapi--typescript)).
- **Positive:** Pydantic schemas work directly as structured output format for LLM calls.
- **Positive:** pgvector-python provides native SQLAlchemy support for vector operations.
- **Negative:** Larger dependency tree (SQLAlchemy, Alembic, pgvector-python).
- **Negative:** Two model layers (ORM + Pydantic) instead of one custom class.
- **Negative:** Lambda cold start may increase slightly due to SQLAlchemy import size.
- **Trade-off:** Supersedes B-91 (SQL f-strings) — SQLAlchemy uses parameterized queries by default.

---

## ADR-005: Remove `/ai_ask` Endpoint — Delegate AI Analysis to Claude Desktop via MCP

**Date:** 2026-02 (Sprint 3, Epic 10)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The `/ai_ask` endpoint allowed sending a text query to an LLM (OpenAI, Bedrock, Vertex AI, Bielik) directly from the React frontend. It was the only way to run AI analysis on collected documents from within the Lenie application.

Meanwhile, the workflow for working with collected knowledge evolved. Claude Desktop (and Claude Code) emerged as the primary interface for AI-powered text analysis, offering far richer capabilities than a single API call — multi-turn conversations, tool use, structured output, and deep reasoning. The missing piece was connecting Claude to Lenie's document store.

### Decision

1. **Remove the `/ai_ask` endpoint** from all layers (server.py, Lambda, API Gateway, React frontend).
2. **Preserve the `ai_ask()` function** in `backend/library/ai.py` — it is still used internally by `youtube_processing.py` for AI-generated video summaries.
3. **Adopt an MCP-based architecture** for AI analysis of collected documents:
   - **Lenie AI** serves as the knowledge base and document retrieval system, exposing its data to Claude Code/Desktop via an MCP server.
   - **Claude Desktop/Code** performs the AI analysis — summarizing, comparing, fact-checking, and synthesizing information from retrieved articles.
   - **Obsidian** serves as the knowledge output system — Claude Code places organized, summarized notes into Obsidian via a separate MCP server.

### Rationale

1. **Separation of concerns.** Lenie's role is to collect, store, and retrieve documents — not to be an AI chat interface. AI analysis is better handled by a dedicated tool (Claude Desktop) that is purpose-built for multi-turn reasoning and tool use.

2. **Superior AI capabilities.** Claude Desktop provides conversational analysis, multi-document synthesis, and structured reasoning that a single `/ai_ask` API call could never match. The user gets a far more powerful analytical experience.

3. **MCP as the integration layer.** The Model Context Protocol (MCP) allows Claude to pull documents from Lenie on demand and push structured notes to Obsidian. This creates a clean pipeline: **Lenie (collect & retrieve) → Claude (analyze) → Obsidian (organize & store knowledge)**.

4. **Reduced maintenance surface.** Removing the endpoint simplifies the API, reduces the attack surface, and eliminates the need to manage LLM API keys in the frontend.

### Consequences

- **Positive:** Clean separation — Lenie focuses on document management, Claude handles AI analysis, Obsidian stores knowledge output.
- **Positive:** Users get dramatically better AI analysis through Claude Desktop's full capabilities vs. a simple ask-and-answer endpoint.
- **Positive:** The MCP-based pipeline enables workflows impossible with a REST endpoint: multi-document comparison, cross-reference checking, structured note generation.
- **Negative:** Requires MCP server implementation for Lenie (future work).
- **Negative:** Users who don't have Claude Desktop lose in-app AI analysis capability (acceptable trade-off for a personal project).

### Related Artifacts

- Story 10.1: Remove `/ai_ask` endpoint
- Story 12.1: Codebase-wide stale reference verification
- `backend/library/ai.py:25` — `ai_ask()` function (preserved for internal use)
- `backend/library/youtube_processing.py:290` — internal consumer of `ai_ask()`

---

## ADR-006: Separate Infrastructure API Gateway from Application API Gateway

**Date:** 2026-02 (Sprint 3)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The AWS deployment had 4 API Gateways:
1. `lenie_split` (1bkc3kz7c9) — main app API from `api-gw-app.yaml`, containing 18 endpoints (10 app + 8 infra)
2. `lenie_dev_infra` (px1qflfpha) — infra API from `api-gw-infra.yaml`, with 7 infra endpoints under different paths
3. `lenie_dev_add_from_chrome_extension` (61w8tmmzkh) — UNUSED duplicate Chrome ext API from `api-gw-url-add.yaml`
4. `lenie_dev_add_from_chrome_extension` (jg40fjwz61) — USED Chrome ext API from `url-add.yaml`

Problems: (A) infrastructure endpoints were duplicated across `api-gw-app` and `api-gw-infra` with inconsistent paths and HTTP methods, (B) two Chrome extension APIs existed where only one was used, (C) the infra API paths (`/database/status`, `/vpn-server/start`) did not match what the frontend expected (`/infra/database/status`, `/infra/vpn_server/start`).

### Decision

1. **Remove the unused Chrome extension API Gateway** (`api-gw-url-add.yaml`) from deployment by commenting it out in `deploy.ini`.
2. **Consolidate all infrastructure endpoints into `api-gw-infra.yaml`** with paths matching frontend expectations (`/infra/database/*`, `/infra/vpn_server/*`, `/infra/sqs/size`, `/infra/git-webhooks`).
3. **Remove all `/infra/*` endpoints from `api-gw-app.yaml`**, leaving only the 10 application endpoints.
4. **Add `infraApiUrl` to the React frontend** so that in AWS Serverless mode, infrastructure calls go to the dedicated infra API Gateway while app calls go to the app API Gateway. In Docker mode, both use the same URL.

### Rationale

1. **Platform consistency.** Infrastructure management (RDS start/stop, EC2, SQS) is AWS-specific and does not exist in Docker/K8s deployments. Keeping infra endpoints separate means `api-gw-app.yaml` defines the same API surface as Docker and K8s, following the project principle of platform-similar deployments.

2. **Single source of truth.** Having the same endpoints in two API Gateways creates confusion about which one is authoritative and risks configuration drift.

3. **Independent lifecycle.** Infrastructure and application endpoints can be deployed and updated independently.

### Consequences

- **Positive:** `api-gw-app.yaml` now matches the Docker/K8s API surface exactly (10 endpoints).
- **Positive:** No duplicate infrastructure endpoints across APIs.
- **Positive:** `api-gw-infra.yaml` paths now match what the frontend sends.
- **Negative:** Frontend needs two API URLs in AWS mode (added `infraApiUrl` to authorization context).
- **Negative:** Requires coordinated deployment (both templates + stack deletion).

### Related Artifacts

- `infra/aws/cloudformation/templates/api-gw-app.yaml` — 10 app endpoints only
- `infra/aws/cloudformation/templates/api-gw-infra.yaml` — 7 infra endpoints (database start/stop/status, vpn start/stop/status, sqs size)
- `web_interface_react/src/modules/shared/context/authorizationContext.js` — `infraApiUrl` state
- `web_interface_react/src/modules/shared/hooks/useDatabase.js` — uses `infraApiUrl` for AWS mode
- `web_interface_react/src/modules/shared/hooks/useVpnServer.js` — uses `infraApiUrl` for AWS mode
- `web_interface_react/src/modules/shared/hooks/useSqs.js` — uses `infraApiUrl` for AWS mode

---

## ADR-007: pytubefix Excluded from Lambda — Serverless YouTube Processing Requires Alternative Compute

**Date:** 2026-02 (Sprint 6, Epic 20)
**Status:** Accepted (constraint identified), Decision Pending (future compute model)
**Decision Makers:** Ziutus

### Context

During the Lambda layer rebuild for Epic 20 (Secrets Management), `pytube` was replaced with `pytubefix` (the maintained fork). The `pytubefix` package has a transitive dependency on `nodejs-wheel-binaries` — a ~60 MB Node.js binary bundled as a Python wheel. This single dependency exceeds the AWS Lambda layer size limit (50 MB zipped / 250 MB unzipped), making it impossible to include `pytubefix` in any Lambda layer.

The previous `lenie_all_layer` (with `pytubefix`) produced a 66 MB ZIP. After removing `pytubefix`, the layer is ~1.6 MB.

### Analysis

Modules that use `pytubefix`:
- `backend/library/stalker_youtube_file.py` — YouTube URL validation, metadata extraction, video download
- `backend/library/youtube_processing.py` — orchestrates YouTube processing pipeline (imports `stalker_youtube_file`)

These modules are **not imported** by any Lambda function handler (`app-server-db`, `app-server-internet`, `sqs-into-rds`, `sqs-weblink-put-into`). YouTube processing currently runs only in:
- Flask server (`server.py`) in Docker/K8s deployments
- Batch scripts (`web_documents_do_the_needful_new.py`) on developer machines

### Decision

1. **Remove `pytubefix` from `lenie_all_layer`** — the layer now contains only: `urllib3`, `requests`, `beautifulsoup4`, `python-dotenv`.
2. **Document this as a permanent Lambda constraint** — `pytubefix` (and any package depending on `nodejs-wheel-binaries`) cannot be used in Lambda layers.
3. **Defer the compute model decision** for serverless YouTube processing to a future sprint (see B-67 in backlog).

### Constraint: Lambda Layer Size Limits

| Limit | Value |
|-------|-------|
| Layer ZIP (compressed) | 50 MB |
| Layer unzipped | 250 MB |
| All layers combined (unzipped) | 250 MB |
| Lambda container image | 10 GB |

Packages that exceed these limits cannot be included in layers. Alternative approaches:

| Option | Max Size | Cold Start | Cost Model |
|--------|----------|------------|------------|
| Lambda layer | 50 MB zipped | ~100-500 ms | Per-invocation |
| Lambda container image | 10 GB | ~5-10 s | Per-invocation |
| ECS Fargate task (on-demand) | Unlimited | ~30-60 s | Per-second (vCPU + memory) |
| ECS Fargate service | Unlimited | Always warm | Per-second (continuous) |

### Consequences

- **Positive:** `lenie_all_layer` reduced from 66 MB to 1.6 MB — well within Lambda limits.
- **Positive:** No impact on current Lambda functions — none of them use YouTube processing.
- **Negative:** YouTube processing in the serverless path is blocked until an alternative compute model is chosen and implemented.
- **Negative:** If a future feature requires YouTube metadata in a Lambda-triggered workflow, it will need either a Lambda container image (~10 GB limit, longer cold starts) or ECS Fargate task (more infrastructure to manage).

### Related Artifacts

- `infra/aws/serverless/lambda_layers/layer_create_lenie_all.sh` — layer build script (pytubefix removed)
- `infra/aws/serverless/CLAUDE.md` — "Known Limitations" section
- `infra/aws/CLAUDE.md` — "Lambda Serverless Constraints" section
- `_bmad-output/planning-artifacts/epics/backlog.md` — B-67: Choose Compute Model for Serverless YouTube Processing
- `backend/library/stalker_youtube_file.py` — pytubefix consumer
- `backend/library/youtube_processing.py` — pytubefix consumer (via stalker_youtube_file)

---

## ADR-008: ruamel.yaml for Round-Trip YAML Preservation in Variable Classification SSOT

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

---

## ADR-009: PostgreSQL Search Strategy — `unaccent` + `pg_trgm` for Structured Fields, Embeddings for Content

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

Project Lenie is evolving toward a personal CRM capability — linking contacts from Google Contacts with notes and documents in the database and Obsidian. The key use case: *"I met person X, we talked about Y — I want to find this quickly before the next meeting."*

This requires effective search across two dimensions:

1. **Structured fields** — names (`Michał Śliwiński` vs `Michal Sliwinski`), cities (`Łódź` vs `Lodz`, `w Warszawie` vs `Warszawa`), and other metadata with Polish diacritics and variant spellings.
2. **Content/notes** — free-text notes and document content where semantic understanding matters (e.g., finding notes about "Warsaw" when the text says "warszawski meetup").

Four PostgreSQL search mechanisms were evaluated:

| Mechanism | Strengths | Weaknesses for this use case |
|-----------|-----------|------------------------------|
| `simple` dictionary | Trivial setup, lowercase normalization | No diacritic handling, no fuzzy matching |
| `unaccent` extension | Normalizes diacritics (`ł→l`, `ą→a`, `ź→z`) | Exact match only, no fuzzy/typo tolerance |
| `pg_trgm` extension | Fuzzy matching via trigram similarity, handles typos and partial matches | Doesn't understand semantics |
| Hunspell `pl_PL` | Polish stemming for common words | Poor with proper nouns (names, small towns not in dictionary), complex setup, high maintenance |
| pgvector embeddings | Semantic understanding, handles inflection naturally | Already implemented; overkill for exact name lookups |

### Decision

Adopt a **three-layer search strategy**:

1. **`unaccent` extension** — for diacritic-insensitive matching on structured fields (names, cities, authors). Solves the primary problem of `Michał` vs `Michal`, `Łódź` vs `Lodz`.

2. **`pg_trgm` extension** — for fuzzy/approximate matching on structured fields. Handles typos (`karboviak` → `Karbowiak`), partial matches, and Polish case inflection at the trigram level (`Warszawa` ↔ `Warszawie` share 5/7 trigrams, similarity ~0.6).

3. **pgvector embeddings** (existing) — for semantic content search in notes and documents. Already handles Polish inflection, synonyms, and meaning-based retrieval naturally.

**Rejected alternative:** Hunspell/Ispell Polish stemmer. While it handles inflection for common Polish words well, it fails for proper nouns — names like `Karbowiaka` (genitive) and small towns like `Pcim Dolny` or `Huta Dłutowska` are not in the dictionary. The setup and maintenance cost (dictionary files, custom text search configuration) is not justified given that embeddings already solve the content search problem and `pg_trgm` provides sufficient fuzzy matching for names.

### Implementation

Add to database init scripts:

```sql
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Example usage patterns:

```sql
-- Diacritic-insensitive name search
SELECT * FROM contacts
WHERE unaccent(lower(name)) LIKE '%' || unaccent(lower('Michal')) || '%';

-- Fuzzy city matching (handles typos and partial inflection)
SELECT * FROM contacts
WHERE similarity(unaccent(lower(address_1_city)), unaccent(lower('Łódź'))) > 0.3;

-- Semantic content search (existing pgvector mechanism)
SELECT * FROM websites_embeddings
WHERE embedding <=> query_embedding < 0.3;
```

### Consequences

- **Positive:** Covers all search scenarios — exact names, fuzzy names, diacritics, semantic content — with minimal new infrastructure.
- **Positive:** `unaccent` and `pg_trgm` are built-in PostgreSQL extensions — no external dependencies or dictionary files to manage.
- **Positive:** Both extensions are lightweight and have negligible impact on database performance.
- **Positive:** Works with existing PostgreSQL 16/18 deployments (both Docker and AWS RDS support these extensions).
- **Negative:** `pg_trgm` similarity threshold (0.3) may need tuning per use case — too low gives false positives, too high misses valid matches.
- **Negative:** Neither `unaccent` nor `pg_trgm` solves full Polish inflection (e.g., `Pcim Dolny` → `w Pcimiu Dolnym`) — but embeddings handle this for content search.

### Related Artifacts

- `backend/database/init/02-create-extension.sql` — extension installation (to be updated)
- `backend/database/init/03-create-table.sql` — `web_documents` table
- `backend/database/init/04-create-table.sql` — `websites_embeddings` table (pgvector)
- `backend/tmp/sql_data/lenie_aws-2026_01_23_05_00_40-dump.sql` — AWS dump showing `unaccent` and `polish` text search config already present
- `docs/architecture-decisions.md` — ADR-001 (native-language embeddings decision)

---

## ADR-010: Database Lookup Tables with Foreign Keys for Enum-Like Fields

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The project uses three Python enums to define constrained value sets for `web_documents` columns:

| Python Enum | Column | Values |
|-------------|--------|--------|
| `StalkerDocumentStatus` | `document_state` | 16 states (ERROR → TEMPORARY_ERROR) |
| `StalkerDocumentStatusError` | `document_state_error` | 17 error types |
| `StalkerDocumentType` | `document_type` | 6 types (movie, youtube, link, webpage, text_message, text) |

Additionally, `websites_embeddings.model` stores embedding model names as free-text `varchar`.

The AWS production database (dump from 2026-01-23) already has four lookup tables with FK constraints enforcing these values at the database level:

- `document_status_types` (FK on `web_documents.document_state`)
- `document_status_error_types` (FK on `web_documents.document_state_error`)
- `document_types` (FK on `web_documents.document_type`)
- `embedding_models` (FK on `websites_embeddings.model` and `embeddings_cache.model`)

The Docker init scripts (`03-create-table.sql`, `04-create-table.sql`) do **not** create these lookup tables — they store enum values as plain `varchar` strings with no FK constraints. The Python code comments confirm this gap: `# Those errors status are also defined in Postgresql table: document_status_types`.

The current SQLAlchemy ORM models (`db/models.py`) use `SAEnum(..., native_enum=False)` which stores values as VARCHAR with application-level validation only — the database does not enforce valid values.

### Decision

Create database lookup tables with FK constraints to enforce data integrity at the database level, matching the existing AWS production schema:

1. **`document_status_types`** — lookup for `web_documents.document_state`
2. **`document_status_error_types`** — lookup for `web_documents.document_state_error`
3. **`document_types`** — lookup for `web_documents.document_type`
4. **`embedding_models`** — lookup for `websites_embeddings.model` (and future `embeddings_cache.model`)

Each lookup table has `id SERIAL PRIMARY KEY` and `name VARCHAR UNIQUE NOT NULL`. FK constraints reference the `name` column (not `id`) for readability of raw queries and data exports.

Python enums (`StalkerDocumentStatus`, `StalkerDocumentStatusError`, `StalkerDocumentType`) remain the **source of truth** for values — an Alembic migration or init script seeds the lookup tables from the enum definitions.

### Rationale

1. **Data integrity.** Without FK constraints, a bug or manual SQL could insert `document_state = 'EMBEDING_EXIST'` (typo) and the database would accept it silently. FK constraints catch this immediately.

2. **Consistency with production.** The AWS database already has these tables and constraints. The Docker development environment should match production schema to avoid "works locally, breaks in prod" issues.

3. **ORM alignment.** SQLAlchemy supports FK-backed enums naturally. The ORM can be updated to define proper `relationship()` mappings to lookup tables, enabling JOIN queries (e.g., statistics per document type).

4. **Extensibility.** Adding a new document type or status becomes: (a) add to Python enum, (b) INSERT into lookup table (via Alembic migration). The FK constraint ensures both stay in sync.

5. **Query clarity.** `SELECT DISTINCT document_state FROM web_documents` is fragile (shows only used values). `SELECT name FROM document_status_types` shows all valid values regardless of usage.

### Implementation

**Phase 1 — Lookup tables & seed data (init scripts + Alembic migration):**

```sql
CREATE TABLE IF NOT EXISTS document_status_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_status_error_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS document_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);
```

Seed with values from Python enums. Add FK constraints:

```sql
ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_type
    FOREIGN KEY (document_type) REFERENCES document_types(name);

ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_state
    FOREIGN KEY (document_state) REFERENCES document_status_types(name);

ALTER TABLE web_documents
    ADD CONSTRAINT fk_document_state_error
    FOREIGN KEY (document_state_error) REFERENCES document_status_error_types(name);

ALTER TABLE websites_embeddings
    ADD CONSTRAINT model_fk
    FOREIGN KEY (model) REFERENCES embedding_models(name) ON UPDATE CASCADE ON DELETE CASCADE;
```

**Phase 2 — ORM model updates:**

Update SQLAlchemy models to reflect FK relationships. Replace `SAEnum(..., native_enum=False)` with `String` + `ForeignKey` + `relationship()`.

**Phase 3 — Sync mechanism:**

Add a startup check or Alembic migration that inserts missing enum values into lookup tables, ensuring Python enums and database stay in sync.

### Consequences

- **Positive:** Database enforces valid values — impossible to insert invalid states, types, or models.
- **Positive:** Docker and AWS schemas converge — reduces environment-specific bugs.
- **Positive:** Lookup tables serve as queryable documentation of valid values.
- **Positive:** Enables future features like status/type metadata (descriptions, display order, active/deprecated flags).
- **Negative:** Adding a new enum value now requires both a code change and a database migration (INSERT into lookup table).
- **Negative:** FK constraints may complicate bulk data imports if values are inserted before lookup tables are populated.
- **Trade-off:** FK references `name` (not `id`) — more readable in raw SQL but slightly less efficient for joins. Acceptable for the table sizes involved (< 20 rows each).

### Why Python Enums Are Kept Alongside DB FK Constraints (B-96)

After completing Phase 2 (ORM model updates with `String` + `ForeignKey`), the question arose: why keep Python enums (`StalkerDocumentType`, `StalkerDocumentStatus`, `StalkerDocumentStatusError`) if the database already enforces valid values via FK constraints?

**Decision:** Keep Python enums as the source of truth. Reasons:

1. **Early validation.** Setter methods (`set_document_type()`, `set_document_state()`, `set_document_state_error()`) raise `ValueError` immediately when called with invalid input. Without enums, the error would only surface at `session.commit()` as an `IntegrityError` — harder to debug and further from the source of the bug.

2. **Input aliases.** Setters accept aliases like `"website"` → `"webpage"`, `"sms"` → `"text_message"`, `"ERROR_DOWNLOAD"` → `"ERROR"`. The database FK cannot handle this mapping — it only validates exact values.

3. **IDE autocomplete.** `StalkerDocumentStatus.EMBEDDING_EXIST` provides autocomplete and typo detection in editors. Raw strings like `"EMBEDDING_EXIST"` do not.

4. **Two-layer defense.** Python enums catch bugs at application level; FK constraints catch bugs at data level (manual SQL, import scripts, other clients). Neither layer alone covers all cases.

The ORM columns store the enum `.name` string (e.g., `StalkerDocumentStatus.ERROR.name` → `"ERROR"`). This keeps the database portable and human-readable while maintaining Python-level type safety.

### Related Artifacts

- `backend/library/models/stalker_document_status.py` — 16 document states
- `backend/library/models/stalker_document_status_error.py` — 17 error types
- `backend/library/models/stalker_document_type.py` — 6 document types
- `backend/library/db/models.py` — SQLAlchemy ORM models with `String` + `ForeignKey` (B-96)
- `backend/database/init/03-create-table.sql` — `web_documents` table (no FK constraints)
- `backend/database/init/04-create-table.sql` — `websites_embeddings` table (no FK constraints)
- `backend/tmp/sql_data/lenie_aws-2026_01_23_05_00_40-dump.sql` — AWS dump with lookup tables and FK constraints
- [ADR-004a](../../docs/architecture-decisions.md#adr-004a-migrate-to-sqlalchemy-orm--pydantic-schemas) — SQLAlchemy ORM migration
- [B-92](#b-92-migrate-database-layer-to-sqlalchemy-orm--pydantic-schemas) — ORM migration backlog item

---

## ADR-011: Remove AWS Transcribe — Use AssemblyAI as Sole Transcription Provider

**Date:** 2026-03-12
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The transcription subsystem supports two providers: AWS Transcribe and AssemblyAI. The routing is handled by `backend/library/transcript.py` with a `provider` parameter (`aws` or `assemblyai`). In practice, **AWS Transcribe has never been used** — AssemblyAI is the default and only provider configured in any environment.

Cost comparison per minute of audio:

| Provider | Cost/min | Cost/hr |
|----------|----------|---------|
| AWS Transcribe | $0.0240 | $1.44 |
| AssemblyAI Universal-3 Pro | $0.0035 | $0.21 |
| AssemblyAI Universal-2 | $0.0025 | $0.15 |

AWS Transcribe is **6.9x–9.6x more expensive** than AssemblyAI with no quality advantage for this use case (Polish and English speech-to-text of YouTube videos).

Additionally, the AWS Transcribe flow requires uploading video files to S3 first (`AWS_S3_TRANSCRIPT` bucket), adding latency and S3 storage costs. AssemblyAI accepts local file uploads directly.

### Decision

1. **Remove all AWS Transcribe code** from the codebase.
2. **AssemblyAI is the sole transcription provider** — no provider routing needed.
3. **Keep the `provider` column** in the new `transcription_log` table for future extensibility (if a cheaper/better provider appears).

### Files Affected

| File | Change |
|------|--------|
| `backend/library/api/aws/transcript.py` | **DELETE** — entire module |
| `backend/library/transcript.py` | Remove AWS import, pricing, and routing branch |
| `backend/library/youtube_processing.py` | Remove AWS Transcribe branch (lines 277-311), S3 upload logic, boto3/requests imports |
| `backend/web_documents_do_the_needful_new.py` | Remove `AWS_S3_TRANSCRIPT` validation check |
| `scripts/vars-classification.yaml` | Mark `AWS_S3_TRANSCRIPT` as deprecated, simplify `TRANSCRIPT_PROVIDER` |
| `infra/kubernetes/kustomize/overlays/gke-dev/server_configmap.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `infra/kubernetes/helm/lenie-ai-server/values.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `infra/kubernetes/helm/lenie-ai-server/templates/configmap.yaml` | Remove `AWS_S3_TRANSCRIPT` |
| `backend/library/CLAUDE.md` | Update documentation |

### Rationale

1. **Cost.** At $1.44/hr vs $0.21/hr, AWS Transcribe is prohibitively expensive for a personal project with a $50 transcription budget. The same budget buys ~35 hours on AWS Transcribe vs ~238 hours on AssemblyAI.

2. **Dead code.** The AWS Transcribe path has never been executed in production. Keeping it increases maintenance burden and cognitive load without any benefit.

3. **Simpler architecture.** Removing the provider routing logic, S3 upload step, and `AWS_S3_TRANSCRIPT` configuration simplifies both the code and the deployment.

4. **No lock-in risk.** The `transcription_log` table retains a `provider` column. If a better option appears in the future, the logging infrastructure is ready. The actual transcription code can be added back with a new provider module.

### Consequences

- **Positive:** Simpler codebase — one provider, no routing logic, no S3 upload step.
- **Positive:** Fewer environment variables to configure (`AWS_S3_TRANSCRIPT`, `TRANSCRIPT_PROVIDER` becomes optional).
- **Positive:** Removes dependency on S3 bucket for transcription workflow.
- **Negative:** No fallback provider — if AssemblyAI is down or changes pricing, transcription is blocked until an alternative is implemented.
- **Negative:** Loss of AWS Transcribe multi-language auto-detection feature (not currently used).

### Related Artifacts

- `_bmad-output/implementation-artifacts/stories-assemblyai-usage-tracking.md` — Story 6: Remove AWS Transcribe Dead Code
- [ADR-007](#adr-007-pytubefix-excluded-from-lambda--serverless-youtube-processing-requires-alternative-compute) — Lambda constraints (YouTube processing already excluded from Lambda)
- `backend/library/api/asemblyai/asemblyai_transcript.py` — remaining transcription implementation

---

## ADR-012: No Google Cloud Model Armor — Defensive Prompting for Prompt Injection Protection

**Date:** 2026-03-15
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

Project Lenie ingests content from untrusted external sources (RSS feeds, web pages, YouTube transcripts, emails) and processes it through LLMs for summarization, embedding generation, and analysis. This creates a potential **prompt injection** attack surface — malicious content embedded in an article or email could manipulate LLM behavior when Lenie processes it.

[Google Cloud Model Armor](https://cloud.google.com/security/products/model-armor) was evaluated as a dedicated sanitization layer. It scans prompts and API responses for prompt injection, content safety violations, and adversarial inputs. Integration is available via the Google Workspace CLI (`gws modelarmor +sanitize-prompt`, `gws modelarmor +sanitize-response`) or directly via the Model Armor API.

### Decision

**Do not integrate Google Cloud Model Armor.** Instead, rely on a combination of defensive prompting, input sanitization, and content-as-data separation already present in the codebase.

### Rationale

1. **Disproportionate complexity for the threat model.** Model Armor requires a GCP project, template configuration, API calls per document, and ongoing cost. For a single-user personal project processing public RSS feeds and web pages, the attack surface is low — an attacker would need to compromise a specific RSS feed that Lenie monitors to inject adversarial content.

2. **Existing mitigations are sufficient.** The codebase already implements several layers of defense (see [`docs/security/prompt-injection-defense.md`](security/prompt-injection-defense.md)):
   - HTML stripping and content sanitization before LLM processing
   - Content treated as data (not instructions) in LLM prompts
   - Skip filters removing suspicious content patterns at import time
   - No autonomous agent actions — LLM outputs are stored, not executed

3. **Cost.** Model Armor API calls add per-document cost. Given Lenie processes hundreds of articles weekly, this would be a recurring expense with marginal security benefit for the current threat model.

4. **Vendor lock-in.** Integrating Model Armor ties the security layer to GCP. Lenie currently uses a multi-cloud approach (AWS, OpenAI, AssemblyAI) and adding a GCP dependency for security scanning contradicts the project's flexibility goals.

5. **Revisit trigger.** This decision should be reconsidered if:
   - Lenie becomes multi-user (untrusted users submitting content)
   - LLM outputs start triggering autonomous actions (API calls, database modifications, email sending)
   - A prompt injection incident occurs through the current feed/import pipeline

### Consequences

- **Positive:** No additional infrastructure, cost, or GCP dependency.
- **Positive:** Simpler architecture — security handled by existing code patterns.
- **Negative:** No dedicated prompt injection detection layer — relies on defense-in-depth rather than a specialized scanner.
- **Negative:** If the threat model changes (multi-user, autonomous actions), this decision must be revisited promptly.

### Related Artifacts

- [`docs/security/prompt-injection-defense.md`](security/prompt-injection-defense.md) — detailed description of current defenses
- [`docs/security/pre-commit-verification.md`](security/pre-commit-verification.md) — secret detection (related security control)
- `backend/imports/feed_monitor.py` — `strip_html()`, `apply_skip_filters()` — input sanitization
- `backend/library/ai.py` — LLM interaction layer
- [ADR-005](#adr-005-remove-ai_ask-endpoint--delegate-ai-analysis-to-claude-desktop-via-mcp) — MCP architecture (Claude Desktop handles AI analysis, reducing in-app LLM attack surface)

---

## ADR-013: Custom LLM Provider Abstraction — Keep Own Interface, Evaluate LiteLLM for Future

**Date:** 2026-03 (Sprint 6)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The project uses a custom abstraction layer for LLM API calls:
- `backend/library/ai.py` — `ai_ask()` routes requests to the correct provider based on model name
- `backend/library/embedding.py` — `get_embedding()` routes to the correct embedding provider
- Per-provider integrations: OpenAI SDK (`openai`), AWS Bedrock (`boto3`), Google Vertex AI (`vertexai`), CloudFerro Sherlock (OpenAI-compatible), ArkLabs (OpenAI-compatible)

The question arose whether to replace this custom layer with a framework like **LangChain** or a lightweight proxy like **LiteLLM**.

### Alternatives Considered

**1. LangChain**
- Zunifikowany interfejs dla wszystkich providerów (`langchain_openai`, `langchain_aws`, `langchain_google_vertexai`)
- Bogaty ekosystem: agenty, chainy, RAG pipeline, integracja z pgvector
- Natywna integracja z LangSmith i Langfuse (callback handler)
- **Odrzucony, ponieważ:**
  - Ciężka zależność — duża biblioteka z częstymi breaking changes między wersjami
  - Projekt nie buduje agentów, chainów ani złożonych pipeline'ów — wzorzec użycia to proste zapytanie→odpowiedź
  - Dodaje warstwę abstrakcji i "magii" utrudniającą debugowanie
  - Overhead niewspółmierny do aktualnych potrzeb (5 providerów, prosty routing)

**2. LiteLLM**
- Lekka biblioteka — jeden interfejs (kompatybilny z OpenAI) dla 100+ providerów
- `litellm.completion(model="bedrock/amazon.nova-pro", messages=[...])` — zero konfiguracji per-provider
- Wbudowana integracja z Langfuse
- Nie narzuca frameworka — zastępuje tylko warstwę transportową
- **Rozważany jako przyszła opcja** — sensowny gdy liczba providerów wzrośnie lub gdy utrzymanie własnego kodu stanie się kosztowne

**3. Pozostanie przy własnej implementacji (wybrane)**
- Obecna warstwa jest prosta, działa i pokrywa wszystkie 5 providerów
- Zero zewnętrznych zależności na warstwie routingu
- Pełna kontrola nad zachowaniem — brak "magii"
- Debugowanie proste — bezpośrednie wywołania SDK

### Decision

1. **Pozostać przy własnej warstwie abstrakcji** (`ai.py`, `embedding.py`) jako primary interface dla LLM calls.
2. **Nie wprowadzać LangChain** — projekt nie wymaga agentów, chainów ani złożonych pipeline'ów.
3. **Rozważyć migrację do LiteLLM** gdy:
   - Liczba obsługiwanych providerów wzrośnie powyżej 7-8
   - Pojawi się potrzeba obsługi nowych API (np. streaming, function calling) wymagającej znacznych zmian w każdym providerze
   - Koszt utrzymania per-provider integrations stanie się istotny
4. **Aktywować Langfuse** jako narzędzie observability dla LLM calls (osobna decyzja — patrz `docs/observability.md`, sekcja "LLM Observability").

### Rationale

- **YAGNI** — obecny wzorzec użycia (prompt→odpowiedź, 5 providerów) nie uzasadnia wprowadzenia frameworka
- **Koszt utrzymania jest niski** — dodanie nowego providera to ~50 linii kodu w osobnym pliku + 5 linii routingu w `ai.py`
- **LiteLLM jako ewolucja, nie rewolucja** — gdyby migracja była potrzebna, LiteLLM jest drop-in replacement dla `ai_ask()` z minimalnym ryzykiem. Interfejs jest kompatybilny z OpenAI SDK, więc integracja z Langfuse nie zmienia się.
- **LangChain opłaca się dopiero przy złożonych workflow** — agenty z narzędziami, pamięcią, wielokrokowymi chainami, zaawansowany RAG. Żaden z tych wzorców nie jest aktualnie potrzebny.

### Consequences

- **Positive:** Brak dodatkowej zależności — mniej ryzyka breaking changes, mniejszy rozmiar deploymentu
- **Positive:** Pełna kontrola nad retry logic, error handling, token counting per provider
- **Positive:** Jasna ścieżka migracji do LiteLLM gdy zajdzie potrzeba
- **Negative:** Każdy nowy provider wymaga ręcznej integracji (~50 LOC)
- **Negative:** Brak gotowych abstrakcji na streaming, function calling — trzeba implementować samodzielnie per provider gdy będą potrzebne

### Related Artifacts

- `backend/library/ai.py` — LLM routing layer (`ai_ask()`)
- `backend/library/embedding.py` — Embedding routing layer (`get_embedding()`)
- `backend/library/api/openai/openai_my.py` — OpenAI integration
- `backend/library/api/aws/bedrock_ask.py` — AWS Bedrock integration
- `backend/library/api/google/google_vertexai.py` — Google Vertex AI integration
- `backend/library/api/cloudferro/sherlock/sherlock.py` — CloudFerro Bielik integration
- `backend/library/api/arklabs/arklabs_embedding.py` — ArkLabs embedding integration
- `docs/observability.md` — LLM observability strategy (Langfuse)
- `docs/technology-choices.md` — Multi-provider abstraction rationale
