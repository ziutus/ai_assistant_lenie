# Architecture Decision Records (ADR)

> Living document tracking key architectural decisions in Project Lenie.

## ADR-001: Remove `/translate` Endpoint and Use Native-Language Embeddings

**Date:** 2026-02 (Sprint 3, Epic 10)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-001-native-language-embeddings.md](adr/adr-001-native-language-embeddings.md)

### Summary

Remove the broken `/translate` endpoint and adopt native-language embeddings as the standard approach. Modern multilingual embedding models (AWS Titan Embed v2, CloudFerro Bielik/BGE) produce high-quality vector representations for Polish text, eliminating the need for translation before embedding. This simplifies the pipeline and preserves original text semantics.

## ADR-002: API Gateway as Security Boundary (No NAT Gateway)

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-002-api-gateway-security-boundary.md](adr/adr-002-api-gateway-security-boundary.md)

### Summary

Use AWS API Gateway as the single entry point with API key authentication, avoiding a NAT Gateway (~$30/month savings). Lambda functions are split into VPC (database access) and non-VPC (internet access) to work around the missing NAT Gateway, adding architectural complexity but keeping costs minimal.

## ADR-003: DynamoDB as Cloud-Local Synchronization Buffer

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-003-dynamodb-sync-buffer.md](adr/adr-003-dynamodb-sync-buffer.md)

### Summary

Use DynamoDB (PAY_PER_REQUEST) to buffer document metadata from mobile submissions while the PostgreSQL RDS database runs only on demand for cost optimization. S3 stores full content; the local PostgreSQL database synchronizes from DynamoDB/S3 when needed. Documents are never lost regardless of RDS state.

## ADR-004: Raw psycopg2 Instead of ORM

**Date:** 2025 (initial development)
**Status:** Superseded by ADR-004a
**Decision Makers:** Ziutus
**Full document:** [adr-004-raw-psycopg2.md](adr/adr-004-raw-psycopg2.md)

### Summary

Use raw `psycopg2` queries instead of an ORM for full control over pgvector-specific operations. This provided a simpler dependency tree but required manual SQL query construction and schema changes via DDL scripts. Superseded by ADR-004a when the approach became too painful as the schema grew.

## ADR-004a: Migrate to SQLAlchemy ORM + Pydantic Schemas

**Date:** 2026-03
**Status:** Accepted (supersedes ADR-004)
**Decision Makers:** Ziutus
**Full document:** [adr-004a-sqlalchemy-orm-migration.md](adr/adr-004a-sqlalchemy-orm-migration.md)

### Summary

Adopt a two-layer architecture: SQLAlchemy 2.x ORM for database access (define schema once, auto-generate SQL, Alembic migrations) and Pydantic v2 schemas for API serialization, OpenAPI generation, and structured AI outputs. This eliminates the DRY violations of raw psycopg2 (5+ places to update per column change) and enables the OpenAPI-to-TypeScript pipeline.

## ADR-005: Remove `/ai_ask` Endpoint — Delegate AI Analysis to Claude Desktop via MCP

**Date:** 2026-02 (Sprint 3, Epic 10)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-005-remove-ai-ask-mcp-architecture.md](adr/adr-005-remove-ai-ask-mcp-architecture.md)

### Summary

Remove the `/ai_ask` endpoint and adopt an MCP-based architecture where Lenie serves as the knowledge base (collect & retrieve), Claude Desktop/Code performs AI analysis, and Obsidian stores organized knowledge output. This provides dramatically better AI capabilities than a single API call and cleanly separates document management from AI analysis.

## ADR-006: Separate Infrastructure API Gateway from Application API Gateway

**Date:** 2026-02 (Sprint 3)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-006-separate-infra-api-gateway.md](adr/adr-006-separate-infra-api-gateway.md)

### Summary

Consolidate all infrastructure endpoints (RDS start/stop, VPN, SQS) into a dedicated `api-gw-infra.yaml` and remove them from `api-gw-app.yaml`, so the application API matches the Docker/K8s surface exactly. The frontend uses separate `infraApiUrl` in AWS Serverless mode. Also removed an unused duplicate Chrome extension API Gateway.

## ADR-007: pytubefix Excluded from Lambda — Serverless YouTube Processing Requires Alternative Compute

**Date:** 2026-02 (Sprint 6, Epic 20)
**Status:** Accepted (constraint identified), Decision Pending (future compute model)
**Decision Makers:** Ziutus
**Full document:** [adr-007-pytubefix-lambda-exclusion.md](adr/adr-007-pytubefix-lambda-exclusion.md)

### Summary

The `pytubefix` package has a ~60 MB transitive dependency (`nodejs-wheel-binaries`) that exceeds the Lambda layer size limit (50 MB zipped). Since no Lambda function currently uses YouTube processing, `pytubefix` was removed from the layer (66 MB down to 1.6 MB). The compute model for serverless YouTube processing is deferred to a future sprint.

## ADR-008: ruamel.yaml for Round-Trip YAML Preservation in Variable Classification SSOT

**Date:** 2026-02-27 (Sprint 6, Epic 20)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-008-ruamel-yaml-roundtrip.md](adr/adr-008-ruamel-yaml-roundtrip.md)

### Summary

Use `ruamel.yaml` instead of PyYAML for the `vars-classification.yaml` SSOT file, which is both machine-written and human-edited. ruamel.yaml preserves comments, key ordering, and formatting during round-trip operations, ensuring that machine writes (adding/removing variables) don't destroy human-authored comments or logical grouping.

## ADR-009: PostgreSQL Search Strategy — `unaccent` + `pg_trgm` for Structured Fields, Embeddings for Content

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-009-postgresql-search-strategy.md](adr/adr-009-postgresql-search-strategy.md)

### Summary

Adopt a three-layer search strategy: `unaccent` extension for diacritic-insensitive matching on structured fields (names, cities), `pg_trgm` for fuzzy/approximate matching (typos, partial inflection), and existing pgvector embeddings for semantic content search. Hunspell Polish stemmer was rejected due to poor handling of proper nouns and high maintenance cost.

## ADR-010: Database Lookup Tables with Foreign Keys for Enum-Like Fields

**Date:** 2026-03-10
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-010-database-lookup-tables.md](adr/adr-010-database-lookup-tables.md)

### Summary

Create database lookup tables (`document_status_types`, `document_status_error_types`, `document_types`, `embedding_models`) with FK constraints to enforce data integrity at the database level, matching the existing AWS production schema. Python enums remain the source of truth for values, with a two-layer defense: enums catch bugs at application level, FK constraints catch bugs at data level.

## ADR-011: Remove AWS Transcribe — Use AssemblyAI as Sole Transcription Provider

**Date:** 2026-03-12
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-011-assemblyai-sole-transcription.md](adr/adr-011-assemblyai-sole-transcription.md)

### Summary

Remove all AWS Transcribe code and use AssemblyAI as the sole transcription provider. AWS Transcribe is 6.9x-9.6x more expensive ($1.44/hr vs $0.21/hr) and has never been used in production. Removing it simplifies the codebase by eliminating provider routing logic and the S3 upload step.

## ADR-012: No Google Cloud Model Armor — Defensive Prompting for Prompt Injection Protection

**Date:** 2026-03-15
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-012-no-model-armor-defensive-prompting.md](adr/adr-012-no-model-armor-defensive-prompting.md)

### Summary

Do not integrate Google Cloud Model Armor for prompt injection protection. The complexity and cost are disproportionate for a single-user personal project. Existing mitigations (HTML stripping, content-as-data separation, skip filters, no autonomous agent actions) are sufficient for the current threat model. To be reconsidered if the project becomes multi-user or LLM outputs start triggering autonomous actions.

## ADR-013: Custom LLM Provider Abstraction — Keep Own Interface, Evaluate LiteLLM for Future

**Date:** 2026-03 (Sprint 6)
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-013-custom-llm-abstraction.md](adr/adr-013-custom-llm-abstraction.md)

### Summary

Keep the custom LLM abstraction layer (`ai.py`, `embedding.py`) instead of adopting LangChain or LiteLLM. The current usage pattern (simple prompt-to-response, 5 providers) doesn't justify a framework. LangChain was rejected as too heavy; LiteLLM is noted as a future option when provider count exceeds 7-8 or per-provider maintenance becomes costly.

## ADR-014: Article Review Tracking — Columns Now, Join Table for Multi-User

**Date:** 2026-03-28
**Status:** Accepted
**Decision Makers:** Ziutus
**Full document:** [adr-014-article-review-tracking.md](adr/adr-014-article-review-tracking.md)

### Summary

Track article review status and Obsidian note creation using two new columns on `web_documents` (`reviewed_at`, `obsidian_note_path`) for the current single-user system. Migrate to a `user_document_reviews` join table when multi-user authentication (B-33) is implemented in Phase 9. This avoids polluting the `document_state` processing pipeline with user-action states, which are orthogonal to technical document processing.

## ADR-016: CloudFormation as Primary IaC — Evaluate CDK for Future Comparison

**Date:** 2026-03-31
**Status:** Accepted (CloudFormation); Proposed (CDK evaluation)
**Decision Makers:** Ziutus
**Full document:** [adr-016-cloudformation-vs-cdk.md](adr/adr-016-cloudformation-vs-cdk.md)

### Summary

CloudFormation remains the primary IaC tool (29 battle-tested templates). A future CDK evaluation is planned — reimplement a self-contained pipeline (SQS + Lambda + DynamoDB) in CDK to compare developer experience, boilerplate, type safety, and testing. Not started — scheduled for Phase 5 of the [AWS Roadmap](aws-roadmap.md), after AWS restoration and CI/CD. See full document for evaluation plan and comparison criteria.
