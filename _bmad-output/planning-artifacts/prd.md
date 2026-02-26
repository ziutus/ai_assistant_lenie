---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
  - step-e-01-discovery
  - step-e-02-review
  - step-e-03-edit
  - step-e-01-discovery
  - step-e-02-review
  - step-e-03-edit
  - step-e-01-discovery
  - step-e-02-review
  - step-e-03-edit
classification:
  projectType: web_app
  domain: personal_ai_knowledge_management
  complexity: low
  projectContext: brownfield
inputDocuments:
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture-backend.md
  - docs/architecture-infra.md
  - docs/api-contracts-backend.md
  - docs/data-models-backend.md
  - docs/integration-architecture.md
  - docs/architecture-web_interface_react.md
  - docs/architecture-web_chrome_extension.md
  - docs/source-tree-analysis.md
  - docs/development-guide.md
  - _bmad-output/implementation-artifacts/epic-1-6-retro-2026-02-15.md
  - _bmad-output/implementation-artifacts/epic-7-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-8-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-9-retro-2026-02-16.md
  - _bmad-output/implementation-artifacts/epic-10-retro-2026-02-18.md
  - _bmad-output/implementation-artifacts/epic-11-retro-2026-02-18.md
  - _bmad-output/implementation-artifacts/epic-12-retro-2026-02-18.md
workflowType: 'prd'
lastEdited: '2026-02-26'
editHistory:
  - date: '2026-02-16'
    changes: 'Updated from Sprint 2 (Cleanup & Vision) to Sprint 3 (Code Cleanup). Rewrote all sections. Applied validation fixes.'
  - date: '2026-02-19'
    changes: 'Updated from Sprint 3 (Code Cleanup) to Sprint 4 (AWS Infrastructure Consolidation & Tooling). 6 backlog stories: B-4, B-5, B-11, B-12, B-14, B-19. Added API Gateway Architecture Principle section.'
  - date: '2026-02-21'
    changes: 'Removed all references to web_add_url_react (archived and deleted from project). Chrome extension is the sole content submission interface. Removed FR17 (add-url app URL update). Updated NFR5, risk mitigation, user journeys, and technical context.'
  - date: '2026-02-23'
    changes: 'Added landing page (www.lenie-ai.eu) and app2 infrastructure (app2.dev.lenie-ai.eu) to Technical Context. Updated Phase 7 with app2 multi-user UI infrastructure readiness. Updated deploy.ini counts (30 templates in [dev], 3 in [common]). Added web_interface_target reference layout info.'
  - date: '2026-02-23'
    changes: 'Added Phase 5 (RSS & Slack Integration) with 3 backlog items: B-40 (Slack workspace + webhooks for notifications), B-41 (RSS feed ingestion with LLM filtering, starting with AWS Whats New), B-42 (Slack Bot for user queries via Socket Mode). Renumbered Obsidian → Phase 6, LLM Text Analysis → Phase 7, Multiuser → Phase 8.'
  - date: '2026-02-25'
    changes: 'Added Phase 2.5 (API Contract & Type Safety) with B-49 (shared TS types — done), B-50 (Pydantic→OpenAPI→TS pipeline — backlog), B-51 (frontend deploy scripts — done). Epic 19 all 4 stories completed. Non-BMad changes reconciled.'
  - date: '2026-02-26'
    changes: 'Added B-63 (Migrate .env to secret managers) to Phase 2 current sprint. Docker/NAS → HashiCorp Vault, AWS → SSM/Secrets Manager. Added FR33-FR39 and NFR16-NFR17. Epic 20 with 5 stories.'
---

# Product Requirements Document - lenie-server-2025

**Author:** Ziutus
**Date:** 2026-02-19
**Sprint:** 4 — AWS Infrastructure Consolidation & Tooling

## Executive Summary

Lenie-server-2025 is a personal AI knowledge management system for collecting, managing, and searching press articles, web content, and YouTube transcriptions using LLMs and vector similarity search (PostgreSQL + pgvector).

**This sprint** executes Phase 2 of the five-phase strategic plan: Infrastructure Consolidation & Tooling. Following the principle "Clean first -> Consolidate -> Secure -> Build new," Sprint 4 consolidates AWS infrastructure and improves operational tooling after Sprint 3 completed code cleanup. Sprint 1 achieved 100% IaC coverage (6 epics, 10 stories). Sprint 2 removed unused AWS resources and documented project vision (3 epics, 5 stories). Sprint 3 removed 3 endpoints, 1 dead function, and applied 6 CloudFormation improvements (3 epics, 33 stories total across sprints). Sprint 4 addresses 7 backlog items: remove Elastic IP from EC2 (B-4), fix redundant Lambda function names (B-5), consolidate the duplicate api-gw-url-add template into api-gw-app (B-14), add AWS account info to deployment script (B-11), verify CRLF git config for parameter files (B-12), consolidate duplicated documentation metrics (B-19), and migrate .env configuration to secret managers (B-63).

**Target vision:** Private knowledge base in Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP server. This sprint consolidates infrastructure to reduce AWS costs and operational friction before security hardening and feature development.

## Success Criteria

### User Success (Developer Experience)

- Developer sees clean Lambda function names following `${ProjectCode}-${Environment}-<description>` pattern with zero redundancy
- Developer deploys via `zip_to_s3.sh` with visible AWS account ID confirmation before any upload
- Developer manages 2 API Gateway templates instead of 3 (removed duplicate api-gw-url-add.yaml); note: url-add.yaml retains its own REST API — 3 REST APIs total in AWS, with clear separation principle documented
- Developer finds documentation metrics (endpoint counts, template counts) in a single source of truth with zero cross-file discrepancies

### Business Success

- Lower AWS costs: ~$3.65/month saved by removing idle Elastic IP
- Reduced API Gateway templates from 3 to 2 (removed duplicate api-gw-url-add.yaml) simplifies infrastructure management
- Documentation accuracy eliminates confusion about system scope (previously: 12 vs 18 endpoints, 29 vs 34 templates)
- Foundation prepared for Phase 3 (Security hardening) and Phase 4 (MCP Server implementation)

### Technical Success

- EC2 `ElasticIP` and `EIPAssociation` resources removed from `ec2-lenie.yaml`; Route53 A record updated dynamically via `aws_ec2_route53.py`
- Lambda `FunctionName` in `lambda-rds-start.yaml` changed from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start` (eliminates `lenie-dev-lambda-rds-start-rds-start-function` redundancy)
- `api-gw-url-add.yaml` merged into `api-gw-app.yaml`; Chrome extension updated with new endpoint URL
- `zip_to_s3.sh` displays AWS account ID and requires confirmation before deployment
- `.gitattributes` coverage verified for parameter files; documented if current config is adequate
- Single-source documentation metrics file created with automated drift verification

### Measurable Outcomes

- 2 CloudFormation resources removed from `ec2-lenie.yaml` (`ElasticIP`, `EIPAssociation`)
- API Gateway templates reduced from 3 to 2 (removed duplicate api-gw-url-add.yaml); 3 REST APIs remain in AWS (app, infra, url-add)
- 0 Lambda functions with redundant names (all follow `${ProjectCode}-${Environment}-<description>`)
- `zip_to_s3.sh` outputs AWS account ID on every run
- 0 discrepancies between documentation metric counts and actual infrastructure counts
- 0 parameter files with CRLF line endings

## Product Scope

### Phase 2 — This Sprint (Infrastructure Consolidation & Tooling)

1. **B-4: Remove Elastic IP from EC2** — Remove `ElasticIP` (AWS::EC2::EIP) and `EIPAssociation` resources from `infra/aws/cloudformation/templates/ec2-lenie.yaml`. EC2 launches with dynamic public IP; Route53 A record updated via `infra/aws/tools/aws_ec2_route53.py` on each start. Update `Outputs` section to reference dynamic IP instead of EIP. Saves ~$3.65/month.

2. **B-5: Fix redundant Lambda function names** — Fix `FunctionName` properties that produce redundant names when `${AWS::StackName}` is used (e.g., `lenie-dev-lambda-rds-start-rds-start-function`). Replace with `${ProjectCode}-${Environment}-<description>` pattern. Affected template: `lambda-rds-start.yaml` (confirmed: uses `${AWS::StackName}-rds-start-function`). Verify all other Lambda templates already use the clean pattern. Update all consumers: API Gateway integrations, Step Function definitions, IAM policies, parameter files referencing the old function name.

3. **B-14: Consolidate api-gw-url-add into api-gw-app** — Merge the `/url_add` endpoint from `api-gw-url-add.yaml` into `api-gw-app.yaml`. Remove or archive `api-gw-url-add.yaml` template and its parameter file `parameters/dev/api-gw-url-add.json`. Migrate API key, usage plan, and Lambda permission resources. Update Chrome extension default endpoint URL (currently `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add`). The `api-gw-infra.yaml` template is not affected.

4. **B-11: Add AWS account info to zip-to-s3 script** — Script `infra/aws/serverless/zip_to_s3.sh` sources `env.sh` by default (account `008971653395`, the current production account). Add: display `AWS_ACCOUNT_ID` during execution, display which env file is sourced, warn/confirm before proceeding with deployment. Two env configs: `env.sh` (account `008971653395`, current production) and `env_lenie_2025.sh` (account `049706517731`, target migration account).

5. **B-12: Fix CRLF git config for parameter files** — Verify parameter files in `infra/aws/cloudformation/parameters/dev/` (29 JSON files) have correct LF line endings. `.gitattributes` already enforces LF for `*.json`. Sprint 3 story 7-2 found CRLF warning was due to Windows `core.autocrlf` setting, not file content. Verify current state, update `.gitattributes` if needed, or document that current config is adequate.

6. **B-19: Consolidate duplicated documentation counts** — Same metrics (endpoint counts, template counts, Lambda function counts) are duplicated across 7+ files with known discrepancies: `api-gw-app` documented as "12 endpoints" (actual: 10), `api-gw-infra` as "9 endpoints" (actual: 8), total templates documented as "29" (actual: 34). Affected files: `CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`. Create single source of truth file. Add automated verification script to catch future drift.

7. **B-63: Migrate .env configuration to secret managers** — Move all configuration from `.env` files to environment-appropriate secret managers. **Docker/NAS:** HashiCorp Vault (already installed on NAS) — backend reads all config from Vault at startup. **AWS:** SSM Parameter Store (non-secret config) + AWS Secrets Manager (credentials, API keys) — Lambda functions and EC2 read config from SSM/Secrets Manager. Only minimal bootstrap configuration remains in `.env`: Vault address (Docker), AWS region/secrets mechanism (AWS), `ENV_DATA` environment identifier. Variables to migrate: database credentials (`POSTGRESQL_*`), API keys (`OPENAI_API_KEY`, `STALKER_API_KEY`), external service tokens (AssemblyAI, Firecrawl), LLM config (`LLM_PROVIDER`, `EMBEDDING_MODEL`), and all remaining non-secret config. Scope: config loader module in backend supporting both Vault and SSM/Secrets Manager, update `server.py` and Lambda handlers, update `.env_example` to bootstrap-only vars, documentation of new config flow.

### Phase 2.5 (Future — API Contract & Type Safety)

Formalize the API contract between backend and frontend to eliminate type drift and enable safe refactoring.

- ~~**B-49: Extract shared TypeScript types to shared/ package**~~ ✅ DONE (2026-02-25) — `shared/` package with domain types, constants, factory values. Both frontends use `@lenie/shared` alias.
- **B-50: API type synchronization pipeline (Pydantic → OpenAPI → TS)** — Multi-phase: (1) Pydantic v2 response models in `backend/library/models/schemas/`, (2) integrate into Flask routes, (3) generate `docs/openapi.json`, (4) generate `shared/types/generated.ts` via `openapi-typescript`, (5) CI drift check. Known drift: `id` type mismatch (TS `string` vs Python `int`), 13 missing fields in `WebDocument`, 5 missing in `ListItem`, 7 missing in `SearchResult`, untyped enums. Strategy: `docs/api-type-sync-strategy.md`. Incremental migration — start with `/website_get`.
- ~~**B-51: Frontend deployment scripts with SSM**~~ ✅ DONE (2026-02-25) — Deploy scripts for both frontends, SSM Parameter Store integration.

### Phase 3 (Future — Security Hardening & AWS Cleanup)

- **B-13: Parameterize stage description for multi-environment** — Enable multi-env support in CloudFormation templates.
- **B-19: Convert EC2 to Spot with ASG 0-1** — Reduce EC2 costs by switching to Spot instances with Auto Scaling Group (min 0, max 1).
- **B-22: Add max retry limit to aws_ec2_route53 script** — Prevent infinite loops in Route53 update script.
- **B-23: Consolidate Lambdas with VPC IPv6 dual-stack** — Merge app-server-db + app-server-internet into one Lambda. ⚠️ BLOCKER: OpenAI API has no IPv6.
- **B-39: Delegate DNS subzones per environment** — Split lenie-ai.eu into delegated subzones (dev, prod). Enables multi-account + multi-cloud. $0.50/month per subzone.
- **B-46: Define strict SCP policies for lenie account** — Granular SCPs for 008971653395: restrict unused services, enforce encryption defaults, block public S3, limit regions.
- **B-52: Lambda Layer security audit** — Lambda Layer dependencies ~1.5+ years old. Audit, update, rebuild layer ZIP.
- **B-53: CORS hardening** — Replace wildcard `Access-Control-Allow-Origin: '*'` with explicit allowed origins.
- **B-54: Lambda function CloudFormation management** — Replace hardcoded Lambda ARNs with CloudFormation-managed references (SSM/Fn::GetAtt).
- **B-55: Remove stale API Gateway deployments** — Remove 36 stale API Gateway deployments left from manual/ad-hoc deploys.

### Phase 4 (Future — MCP Server Foundation)

- **B-56: Database abstraction layer** — Separate raw psycopg2 queries from business logic. Prerequisite for MCP server and testability.
- **B-57: Implement MCP server protocol** — Expose search/retrieve endpoints as MCP tools. Follow MCP specification.
- **B-58: Claude Desktop integration** — Configure Lenie-AI as MCP server in Claude Desktop. Test search and retrieve workflows.
- **B-59: API adaptation for MCP tool consumption** — Adapt API response formats for MCP tool consumption patterns.

### Phase 5 (Future — RSS & Slack Integration)

Bidirectional communication channel (Slack) and new automated data source (RSS feeds). Enables proactive notifications about errors and interesting content, and allows querying the system from mobile via Slack. Phased: webhooks first (simple, serverless-friendly), then Slack Bot (requires persistent process or Socket Mode).

- **B-40: Slack Workspace & Incoming Webhooks** — Create Slack workspace (free plan). Configure Incoming Webhook for a `#notifications` channel. Integrate webhook into existing error handling pipeline (alongside SNS email). Send notifications on: document processing errors, SQS DLQ messages. Store webhook URL in Secrets Manager (or SSM SecureString). Add CloudFormation parameter for webhook URL.
- ~~**B-43: Fix app2 domain — move from `app2.lenie-ai.eu` to `app2.dev.lenie-ai.eu`**~~ ✅ DONE (2026-02-24) — CloudFront alias updated to `app2.dev.lenie-ai.eu`, Route53 A record migrated, ACM certificate switched to `*.dev.lenie-ai.eu` wildcard. Also: wired up TopBar logout button, replaced language options with English/Polish.

### Phase 6 (Future — Obsidian Integration)

- **B-60: Obsidian vault integration** — Synchronization between Lenie-AI and Obsidian vault — linking, note creation, bidirectional sync.
- **B-61: Semantic search from Obsidian** — Semantic search from within Obsidian via Claude Desktop + MCP server (depends on B-57, B-58).
- **B-62: Advanced vector search refinements** — Advanced vector search refinements for personal knowledge management — filtering, ranking, hybrid search.

### Phase 7 (Future — Extending Functionality)

Non-MVP features for expanding data sources and interaction channels. Not required for core product but valuable for personal knowledge management workflow.

- **B-41: RSS Feed Ingestion with LLM Filtering** — New data source: RSS feeds (starting with AWS "What's New" — `https://aws.amazon.com/about-aws/whats-new/recent/feed/`). Daily scheduled Lambda (EventBridge cron) fetches RSS, parses entries, sends each to LLM for relevance scoring (prompt: "Is this relevant to: serverless, containers, PostgreSQL, AI/ML, security?"). Relevant entries are submitted to the existing document pipeline (`/url_add` flow via SQS). Store last-processed entry timestamp in DynamoDB to avoid duplicates. Notify via Slack webhook when interesting articles are found.
- **B-42: Slack Bot for User Queries (Socket Mode)** — Slack App with Bot user using Socket Mode (no public endpoint required). Bot listens for messages and supports commands: `search <query>` (calls `/website_similar` for vector search), `status` (returns SQS queue size, RDS status), `recent` (lists last N processed documents). Deploy as systemd service on existing `lenie-dev-ec2` instance (t4g.micro) — zero additional infrastructure cost. Bot runs during EC2 uptime (~12h on working days). Slack Socket Mode handles disconnects gracefully (auto-reconnect when EC2 starts).
- **B-44: Storytel Audiobook Tracking** — Automatically track audiobooks listened on storytel.com. Scrape or integrate with Storytel to capture book metadata (title, author, genre, listening progress/completion). Store as documents in the existing pipeline (new content type: `audiobook`). Enable searching and managing audiobook history alongside other collected data. Explore Storytel API or web scraping for data extraction.
- **B-45: YouTube Movie Description Fetching** — Automatically fetch and store video descriptions, metadata (title, channel, duration, publish date, tags) for YouTube videos added to the system. Extend existing YouTube content type with richer metadata beyond transcript. Use YouTube Data API v3 or yt-dlp for extraction.
- **B-47: WhatsApp Conversation Analysis** — Import exported WhatsApp conversations and analyze them via LLM. Extract key topics, mentioned contacts, decisions, action items, and important dates. Store as documents in the existing pipeline (new content type: `whatsapp`). Support WhatsApp's text export format (.txt).
- **B-48: Google Contacts Integration** — Integrate with Google People API to sync address book data. Link contacts to documents and conversations stored in the system. Enable searching documents by contact name. OAuth 2.0 authentication for Google API access.

### Phase 8 (Future — LLM Text Analysis)


Realizowane po MVP (po fazach Security, MCP Server, Obsidian). Automatyczna analiza tekstu dokumentów przez LLM, zwracająca ustrukturyzowany JSON z metadanymi.

- **B-29: Endpoint analizy tekstu przez LLM** — Nowy endpoint API wysyłający tekst dokumentu do LLM z promptem ekstrakcyjnym. LLM zwraca JSON z polami: autor, temat/tematy, państwa których dotyczy, źródło danych (np. BBC, Reuters), data publikacji, typ treści (news, opinia, analiza), osoby wymienione, organizacje. Obsługa wielu providerów LLM (OpenAI, Bedrock, Vertex) zgodnie z istniejącą konfiguracją `LLM_PROVIDER`.
- **B-30: Schemat JSON analizy i przechowywanie w bazie** — Definicja schematu JSON dla wyników analizy. Nowa kolumna `ai_analysis` (JSONB) w tabeli `web_documents` lub dedykowana tabela `web_documents_analysis`. Indeksy GIN na polach JSONB do wyszukiwania po autorze, temacie, kraju.
- **B-31: UI wyników analizy we frontendzie** — Wyświetlanie wyników analizy na stronie edycji dokumentu. Możliwość ręcznej korekty wyników. Filtrowanie listy dokumentów po metadanych z analizy (autor, kraj, temat).
- **B-32: Batch analysis istniejących dokumentów** — Skrypt przetwarzający dokumenty bez analizy (analogiczny do `web_documents_do_the_needful_new.py`). Nowy status dokumentu w pipeline (np. `ANALYSIS_NEEDED` → `ANALYSIS_DONE`). Integracja z Step Function/SQS na AWS.

### Phase 9 (Future — Multiuser Support on AWS)

Realizowane na samym końcu, po zakończeniu wszystkich pozostałych faz. Umożliwi korzystanie z systemu przez wielu użytkowników na infrastrukturze AWS.

**Infrastructure status (2026-02-23):** app2 hosting infrastructure is ready — S3 bucket (`s3-app2-web.yaml`) and CloudFront distribution (`cloudfront-app2.yaml`) templates created and added to deploy.ini. Target domain: `app2.dev.lenie-ai.eu`. Admin panel (`web_interface_app2/`) scaffolded from a purchased layout with API key authentication already implemented. Tech stack: Vite 6, React 18, Redux, React Bootstrap, TypeScript, Sass. See Epic 19 in `epics.md`.

- **B-33: Uwierzytelnianie użytkowników (AWS Cognito)** — Wdrożenie AWS Cognito User Pool do rejestracji i logowania użytkowników. Integracja z API Gateway (Cognito Authorizer) zamiast obecnego statycznego klucza API.
- **B-34: Własność danych w bazie** — Dodanie kolumny `user_id` (owner) do tabel `web_documents` i `websites_embeddings`. Migracja istniejących danych do domyślnego użytkownika. Indeksy uwzględniające `user_id`.
- **B-35: Izolacja danych per użytkownik w API** — Wszystkie endpointy filtrują dane po `user_id` z tokena Cognito. Użytkownik widzi i modyfikuje tylko swoje dokumenty.
- **B-36: Zamiana wspólnego klucza API na tokeny per użytkownik** — Usunięcie mechanizmu `x-api-key` na rzecz JWT z Cognito. Aktualizacja wszystkich klientów (frontend, Chrome extension).
- **B-37: UI logowania/wylogowania** — Ekrany logowania i rejestracji w aplikacjach frontendowych (app2). Obsługa sesji użytkownika i odświeżania tokenów.
- **B-38: Panel administracyjny użytkowników** — Zarządzanie użytkownikami (lista, blokowanie, usuwanie). Widoczność statystyk per użytkownik (liczba dokumentów, zużycie embeddingów).
- **B-39: Multi-user Admin Interface (app2)** — **URGENT:** app2 jest publicznie dostępna bez uwierzytelniania. Pierwszym krokiem jest dodanie prostego logowania (hardcoded credentials z env vars: `APP2_AUTH_USERNAME`, `APP2_AUTH_PASSWORD`) i ochrona wszystkich tras. Następnie: scaffold projektu (Vite + React 18 + TypeScript + Redux Toolkit + React Bootstrap), layout i nawigacja wzorowane na zakupionym szablonie, podpięcie istniejącego backend API. Infrastruktura S3 + CloudFront wdrożona. Docelowo migracja na AWS Cognito (B-33).

## User Journeys

### Journey 1: Developer Infrastructure Consolidation Sprint

**Persona:** Ziutus — sole developer and project owner, intermediate skill level.

**Opening Scene:** Ziutus opens the project after completing Sprint 3 (Code Cleanup). The codebase is clean — no dead endpoints or unused functions. However, infrastructure has accumulated debt: an idle Elastic IP costs $3.65/month, Lambda function names contain redundant segments (`lenie-dev-lambda-rds-start-rds-start-function`), three API Gateways exist where two suffice, the deployment script does not show which AWS account it targets, and documentation metrics are inconsistent across 7+ files.

**Rising Action:** Ziutus removes the Elastic IP from `ec2-lenie.yaml` and verifies that `aws_ec2_route53.py` correctly updates Route53 with the dynamic public IP on each EC2 start. Ziutus fixes the Lambda function name in `lambda-rds-start.yaml` from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start` and updates all consumers. Ziutus merges the `/url_add` endpoint from `api-gw-url-add.yaml` into `api-gw-app.yaml`, updates the Chrome extension's default endpoint URL, then removes the standalone template. Ziutus adds account ID display and confirmation to `zip_to_s3.sh`. Ziutus verifies parameter file line endings and documents the finding. Ziutus creates a single-source metrics file and an automated verification script, then fixes all discrepancies across documentation files.

**Climax:** After deployment — EC2 starts with dynamic IP and Route53 updates automatically. Lambda functions have clean names. The duplicate api-gw-url-add template is removed; api-gw-app now serves 11 endpoints (including `/url_add`), api-gw-infra serves 7 endpoints, and url-add.yaml retains its own API Gateway (3 REST APIs total). The deployment script clearly shows target account `008971653395` before proceeding. Documentation metrics match actual infrastructure with zero discrepancies. The verification script confirms consistency.

**Resolution:** Infrastructure is consolidated. Monthly costs are reduced. Operational safety is improved (account visibility in deployment). Documentation is accurate and maintainable. The project is ready for Phase 3 (Security Hardening).

### Journey 2: Developer Deploying Lambda Code

**Persona:** Ziutus deploying updated Lambda code to AWS.

**Opening Scene:** Ziutus runs `./zip_to_s3.sh simple` from `infra/aws/serverless/`.

**Rising Action:** The script displays: sourcing `env.sh`, AWS account ID `008971653395`, profile `default`, environment `dev`, S3 bucket `lenie-dev-cloudformation`. Ziutus reviews the information and confirms deployment. The script packages each Lambda function and uploads to S3.

**Resolution:** Ziutus has full visibility into which AWS account receives the deployment. No accidental cross-account deployments. If `env_lenie_2025.sh` were sourced instead, the script would display account `049706517731` and profile `lenie-ai-2025-admin`, making the difference immediately visible.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| Infra Consolidation | Remove ElasticIP and EIPAssociation from ec2-lenie.yaml |
| Infra Consolidation | Update ec2-lenie.yaml Outputs to reference dynamic public IP |
| Infra Consolidation | Fix Lambda FunctionName in lambda-rds-start.yaml to clean pattern |
| Infra Consolidation | Update all consumers of renamed Lambda function |
| Infra Consolidation | Merge api-gw-url-add.yaml /url_add endpoint into api-gw-app.yaml |
| Infra Consolidation | Update Chrome extension endpoint URL |
| Infra Consolidation | Remove or archive api-gw-url-add.yaml template |
| Infra Consolidation | Add account ID display and confirmation to zip_to_s3.sh |
| Infra Consolidation | Verify parameter file line endings in .gitattributes |
| Infra Consolidation | Create single-source documentation metrics file |
| Infra Consolidation | Add automated verification script for documentation drift |
| Lambda Deployment | See AWS account ID before deployment proceeds |
| Lambda Deployment | Confirm deployment target before uploads begin |

## API Gateway Architecture Principle

The project uses two categories of API Gateway:

1. **Application API Gateway (`api-gw-app.yaml`)** — Endpoints that serve application functionality: document CRUD, search, AI operations, content download, URL submission. These endpoints correspond to Flask `server.py` routes and Lambda functions (`app-server-db`, `app-server-internet`, `sqs-weblink-put-into`).

2. **Infrastructure API Gateway (`api-gw-infra.yaml`)** — Endpoints that manage AWS infrastructure: RDS start/stop/status, EC2 start/stop/status, SQS queue size. These endpoints have no equivalent in the Flask `server.py` and exist only in the AWS serverless deployment.

**Rationale:** This separation enables direct comparison between deployment targets. Application endpoints exist in Docker (server.py), AWS Lambda, and future GCP deployments. Infrastructure endpoints are AWS-specific and have no cross-platform equivalent. Keeping them in separate API Gateways makes this boundary explicit.

**Consolidation decision:** The Chrome extension API (`api-gw-url-add.yaml`) was a duplicate template serving the `/url_add` endpoint, which is application-level functionality (document submission). It belongs in `api-gw-app.yaml`, not in a standalone API Gateway template. Sprint 4 merges the endpoint definition into `api-gw-app.yaml` and removes the duplicate `api-gw-url-add.yaml` template and its CF stack. Note: `url-add.yaml` (the Lambda function template) retains its own REST API Gateway — this is a separate template, not the duplicate that was removed.

**Post-consolidation state:**
- `api-gw-app.yaml` — 11 endpoints: `/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`, `/website_download_text_content`, `/ai_embedding_get`, `/url_add`
- `api-gw-infra.yaml` — 7 endpoints: `/infra/sqs/size`, `/infra/vpn_server/start`, `/infra/vpn_server/stop`, `/infra/vpn_server/status`, `/infra/database/start`, `/infra/database/stop`, `/infra/database/status`
- `url-add.yaml` — 1 endpoint: `/url_add` (Lambda function template with its own REST API Gateway, still active in deploy.ini)
- **Total: 2 API Gateway templates (`api-gw-*`) + 1 Lambda template with embedded API GW (`url-add.yaml`) = 3 REST APIs in AWS**

## Web App Technical Context

Brownfield web application: React 18 SPA (Amplify) + Flask REST API (API Gateway + Lambda) + PostgreSQL 17 with pgvector (RDS). Sprint 4 modifies CloudFormation templates, deployment scripts, and client endpoint configurations — no backend application code changes.

**API Gateway template size:** `api-gw-app.yaml` is under the 51200 byte CloudFormation inline limit after Sprint 3 endpoint removal. Adding the `/url_add` endpoint (POST + OPTIONS with CORS, ~60 lines of OpenAPI) will increase size. Monitor that merged template stays under the inline limit. If exceeded, switch to S3-based template deployment (`aws cloudformation package`).

**Chrome extension endpoint URL:** Currently hardcoded in `web_chrome_extension/popup.html` as `https://jg40fjwz61.execute-api.us-east-1.amazonaws.com/v1/url_add`. After API Gateway consolidation, this URL changes to the `api-gw-app` gateway URL. The extension allows user override via the settings field.

**Lambda function naming:** Stack naming convention is `<PROJECT_CODE>-<STAGE>-<template_name>`. The `lambda-rds-start.yaml` template uses `${AWS::StackName}` in `FunctionName`, producing `lenie-dev-lambda-rds-start-rds-start-function` (stack name `lenie-dev-lambda-rds-start` + suffix `-rds-start-function`). Other Lambda templates already use the clean `${ProjectCode}-${Environment}-<description>` pattern directly: `sqs-to-rds-lambda.yaml` produces `lenie-dev-sqs-to-rds-lambda`, `lambda-weblink-put-into-sqs.yaml` produces `lenie-dev-weblink-put-into-sqs`.

**AWS accounts:**
- `008971653395` — CURRENT production account (all active infrastructure runs here)
- `049706517731` — TARGET migration account (will be used after full migration including RDS data)

**Deployment script:** `infra/aws/serverless/zip_to_s3.sh` sources `env.sh` by default, which targets account `008971653395`. The script currently provides no account visibility — a developer could source the wrong env file and deploy to the wrong account without warning.

**Frontend deployments (current state as of 2026-02-23):**
- **React admin app** (`web_interface_react/`): `app.dev.lenie-ai.eu` — S3 + CloudFront, active single-user interface
- **Landing page** (`web_landing_page/`): `www.lenie-ai.eu` — S3 + CloudFront, Next.js 14.2 + TypeScript static export, **LIVE**
- **Admin panel** (`web_interface_app2/`): `app2.dev.lenie-ai.eu` — S3 + CloudFront, Vite 6 + React 18 + TypeScript admin panel with API key authentication. Originally scaffolded from a purchased layout (visual/structural reference only, now removed from repo).

**CloudFormation state:** 30 templates in deploy.ini [dev] + 3 in [common] (organization, SCPs). Total 38 .yaml files in templates/.

## Risk Mitigation

**Technical Risks:**
- *EC2 unreachable after EIP removal* — Mitigated by verifying `aws_ec2_route53.py` updates Route53 A record with dynamic IP on each EC2 start. TTL is 300 seconds. Makefile target `aws-start-openvpn` already uses this script.
- *Lambda function rename breaks API Gateway integrations* — Mitigated by: (1) verifying `api-gw-infra.yaml` already references `${ProjectCode}-${Environment}-rds-start` (confirmed from codebase), (2) updating Step Function definitions and parameter files that reference the old name, (3) deploying Lambda template before API Gateway template.
- *API Gateway consolidation breaks Chrome extension* — Mitigated by: (1) updating hardcoded URL in Chrome extension, (2) migrating API key and usage plan resources, (3) testing `/url_add` endpoint on new gateway before removing old gateway.
- *`api-gw-app.yaml` exceeds 51200 byte inline limit after adding /url_add* — Mitigated by checking template size after merge. Fallback: use `aws cloudformation package` for S3-based deployment.
- *Wrong AWS account deployment* — Mitigated by adding explicit account display and confirmation prompt to `zip_to_s3.sh`.

**Resource Risks:**
- *Context loss between sessions* — Mitigated by detailed story files and BMad Method tracking
- *Documentation drift reoccurs after consolidation* — Mitigated by automated verification script that compares documented counts against actual infrastructure
- *CloudFormation validation failures* — Mitigated by cfn-lint validation before every deployment

**Process Risks:**
- *Retro action items not tracked* — Mitigated by adding retro commitments to sprint-status.yaml
- *Old API Gateway left running after consolidation* — Mitigated by story requiring explicit deletion or decommission step for api-gw-url-add stack

## Functional Requirements

### B-4: Remove Elastic IP from EC2

- FR1: Developer can remove `ElasticIP` (AWS::EC2::EIP) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR2: Developer can remove `EIPAssociation` (AWS::EC2::EIPAssociation) resource from `infra/aws/cloudformation/templates/ec2-lenie.yaml`
- FR3: Developer can update `Outputs.PublicIP` in `ec2-lenie.yaml` to reference the EC2 instance dynamic public IP instead of the Elastic IP
- FR4: Developer can verify `infra/aws/tools/aws_ec2_route53.py` updates Route53 A record with the EC2 dynamic public IP on each instance start
- FR5: Developer can verify EC2 instance launches with a dynamic public IP via the public subnet's `MapPublicIpOnLaunch: 'true'` setting in `infra/aws/cloudformation/templates/vpc.yaml` (lines 83, 98)

### B-5: Fix Redundant Lambda Function Names

- FR6: Developer can change `FunctionName` in `infra/aws/cloudformation/templates/lambda-rds-start.yaml` from `${AWS::StackName}-rds-start-function` to `${ProjectCode}-${Environment}-rds-start`
- FR7: Developer can verify all other Lambda templates already use the `${ProjectCode}-${Environment}-<description>` naming pattern (no `${AWS::StackName}` usage)
- FR8: Developer can update `infra/aws/cloudformation/parameters/dev/lambda-rds-start.json` if any parameter references the old function name
- FR9: Developer can verify `SqsToRdsLambdaFunctionName` parameter in `infra/aws/cloudformation/parameters/dev/sqs-to-rds-step-function.json` (currently `lenie-dev-sqs-to-rds-lambda`) does not reference the renamed Lambda function and update if needed
- FR10: Developer can verify `api-gw-infra.yaml` Lambda function references (FunctionName properties) resolve correctly after the rename
- FR11: Developer can verify the renamed Lambda function is invocable by the Step Function defined in `sqs-to-rds-step-function.yaml`

### B-14: Consolidate api-gw-url-add into api-gw-app

- FR12: Developer can add the `/url_add` POST endpoint definition (with Lambda proxy integration) from `api-gw-url-add.yaml` into the OpenAPI Body of `api-gw-app.yaml`
- FR13: Developer can add the `/url_add` OPTIONS endpoint definition (CORS mock integration) from `api-gw-url-add.yaml` into `api-gw-app.yaml`
- FR14: Developer can add the Lambda permission resource for the `url-add` Lambda function to `api-gw-app.yaml`
- FR15: Developer can verify the merged `api-gw-app.yaml` template size remains under the 51200 byte CloudFormation inline limit
- FR16: Developer can update the default endpoint URL in `web_chrome_extension/popup.html` to the `api-gw-app` gateway URL
- FR17: Developer can remove or archive the `api-gw-url-add.yaml` template from `infra/aws/cloudformation/templates/`
- FR19: Developer can remove the `api-gw-url-add.json` parameter file from `infra/aws/cloudformation/parameters/dev/`
- FR20: Developer can delete the `lenie-dev-api-gw-url-add` CloudFormation stack from AWS after the consolidated gateway is deployed and verified
- FR21: Developer can verify the `/url_add` endpoint on the consolidated `api-gw-app` gateway returns successful responses with the existing API key

### B-11: Add AWS Account Info to zip-to-s3 Script

- FR22: Developer can see the sourced environment file name (`env.sh` or `env_lenie_2025.sh`) displayed when running `infra/aws/serverless/zip_to_s3.sh`
- FR23: Developer can see the AWS account ID (`AWS_ACCOUNT_ID` variable) displayed when running `zip_to_s3.sh`
- FR24: Developer can see the AWS profile name, environment, and S3 bucket name displayed before deployment begins
- FR25: Developer can confirm or abort deployment after reviewing the displayed account information

### B-12: Fix CRLF Git Config for Parameter Files

- FR26: Developer can verify all 29 parameter files in `infra/aws/cloudformation/parameters/dev/` have LF line endings
- FR27: Developer can verify `.gitattributes` rules cover `*.json` files with `text eol=lf`
- FR28: Developer can document the verification result — either update `.gitattributes` with additional rules, or confirm current config is adequate with explanation

### B-19: Consolidate Duplicated Documentation Counts

- FR29: Developer can create a single-source metrics file at `docs/infrastructure-metrics.md` containing authoritative counts for: API Gateway endpoints (per gateway), CloudFormation templates, Lambda functions, server.py endpoints
- FR30: Developer can fix all discrepancies across documentation files (`CLAUDE.md`, `README.md`, `backend/CLAUDE.md`, `docs/index.md`, `docs/api-contracts-backend.md`, `infra/aws/CLAUDE.md`, `infra/aws/cloudformation/CLAUDE.md`) to reference the single-source file or use consistent correct values
- FR31: Developer can run an automated verification script that compares documented counts against actual infrastructure counts and reports any discrepancies
- FR32: Developer can verify zero discrepancies between documented and actual counts after running the verification script

### B-63: Migrate .env Configuration to Secret Managers

- FR33: Developer can create a config loader module in `backend/library/` that abstracts secret retrieval behind a unified interface, supporting HashiCorp Vault (Docker/NAS) and AWS SSM Parameter Store / Secrets Manager (AWS)
- FR34: Developer can configure the config loader via minimal bootstrap `.env` variables: `SECRETS_BACKEND` (`vault` or `aws`), `VAULT_ADDR` (Vault endpoint for Docker), `AWS_REGION` (for AWS), `ENV_DATA` (environment identifier)
- FR35: Developer can store all application configuration (database credentials, API keys, LLM config, service tokens) in HashiCorp Vault for the Docker/NAS environment and verify the backend reads them at startup
- FR36: Developer can store all application configuration in AWS SSM Parameter Store (non-secret config) and AWS Secrets Manager (credentials, API keys) for the AWS environment and verify Lambda functions and EC2 read them at startup
- FR37: Developer can update `server.py` to use the config loader module instead of reading directly from `os.environ` / `.env`
- FR38: Developer can update Lambda handlers to use the config loader module instead of reading directly from environment variables
- FR39: Developer can update `.env_example` to contain only bootstrap variables with documentation explaining the new config flow

## Non-Functional Requirements

### Reliability & Safety

- NFR1: Existing API Gateway endpoints continue to function correctly after `api-gw-url-add` consolidation into `api-gw-app`, verified by `infra/aws/cloudformation/smoke-test-url-add.sh` passing with exit code 0 (tests API Gateway → Lambda → DynamoDB flow)
- NFR2: EC2 instance remains accessible via SSH and HTTP/HTTPS after Elastic IP removal, with Route53 A record updated within 5 minutes of instance start
- NFR3: No actively used CloudFormation resources are removed — only resources being consolidated or replaced
- NFR4: All infrastructure changes preserve rollback capability through version control (git) and CloudFormation stack operations
- NFR5: Chrome extension successfully submits URLs via the consolidated API Gateway endpoint

### IaC Quality & Validation

- NFR6: All modified CloudFormation templates pass cfn-lint validation with zero errors before deployment
- NFR7: All Lambda functions follow the naming convention `${ProjectCode}-${Environment}-<description>` with zero `${AWS::StackName}` usage in FunctionName properties
- NFR8: The consolidated `api-gw-app.yaml` template remains under the 51200 byte CloudFormation inline limit
- NFR9: CloudFormation deployment order in `deploy.ini` remains correct after template removal (no dangling dependencies)

### Operational Safety

- NFR10: `zip_to_s3.sh` displays AWS account ID, profile, and environment on every execution before any S3 upload or Lambda update occurs
- NFR11: `zip_to_s3.sh` requires explicit user confirmation before proceeding with deployment to prevent accidental cross-account deployments
- NFR12: Parameter files in `infra/aws/cloudformation/parameters/dev/` have consistent LF line endings verified by `.gitattributes` enforcement

### Documentation Quality

- NFR13: Documentation metrics (endpoint counts, template counts, Lambda function counts) have a single source of truth with zero cross-file discrepancies
- NFR14: An automated verification script exists that detects documentation metric drift and can be run as part of CI or manual review
- NFR15: All documentation files reference post-consolidation state: 2 API Gateway templates (app + infra) with url-add.yaml retaining its own REST API (3 total), correct endpoint counts per gateway (app: 11, infra: 7, url-add: 1), correct total template count

### Secrets Management

- NFR16: No secrets (API keys, passwords, tokens) remain in `.env` files after migration — only bootstrap variables (Vault address, AWS region, secrets backend selector, environment identifier)
- NFR17: Backend starts successfully in both Docker (Vault) and AWS (SSM/Secrets Manager) environments using the unified config loader, with clear error messages if the secret backend is unreachable
