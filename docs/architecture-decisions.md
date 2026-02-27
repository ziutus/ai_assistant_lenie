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
