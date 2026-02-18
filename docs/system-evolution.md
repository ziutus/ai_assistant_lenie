# System Evolution

A brief history of how Project Lenie evolved — key turning points, lessons learned, and why things are the way they are.

## From English-Only Embeddings to Multilingual

In the early days, embedding models only worked well with English text. Since most of the documents collected by Lenie are in Polish (news articles, social media posts, books), the system needed a translation step before generating embeddings. That's why the `/translate` endpoint existed and why the document processing pipeline includes a `READY_FOR_TRANSLATION` state.

The approach was: download article → clean text → translate to English → generate embedding → store.

This changed when multilingual embedding models became mature enough. AWS Titan Embed v2 and CloudFerro's BGE Multilingual Gemma2 can embed Polish text directly, with quality comparable to the old translate-then-embed approach.

The decision to drop translation wasn't just about convenience. Translation is a form of interpretation — the translator (whether human or AI) makes choices about meaning, and those choices subtly alter the text. For a system that helps assess information reliability, preserving the author's exact words matters. The system should not silently interpret content on the user's behalf.

There's a theoretical risk: without translation to a common language, the same content in Polish and English would produce different embeddings, potentially causing duplicate documents to go undetected. In practice, this doesn't apply to Lenie — the system collects news articles, books, and social media messages. The same article simply doesn't appear in multiple languages in the collection.

The `/translate` endpoint was removed in Sprint 3 (February 2026). The `READY_FOR_TRANSLATION` processing state still exists in the database for backward compatibility with existing records.

## From Built-in AI to MCP-Based Knowledge Pipeline

The `/ai_ask` endpoint was one of the original features — it let the React frontend send a question to an LLM and display the response. It worked, but it was a dead end architecturally. A single request-response API call is a poor interface for serious text analysis: no conversation memory, no multi-document synthesis, no structured output.

The turning point was realizing that the primary workflow had shifted. Lenie's job is to collect and organize documents — news articles, books, social media posts. But the actual *thinking* about those documents happens in Claude Desktop, which offers multi-turn reasoning, tool use, and the ability to work across multiple documents at once.

This led to a new architecture built around the Model Context Protocol (MCP):

1. **Lenie AI** is the knowledge base — it collects, stores, and retrieves documents. An MCP server exposes Lenie's search and retrieval capabilities to Claude.
2. **Claude Desktop / Claude Code** is the analytical layer — it pulls documents from Lenie via MCP, performs analysis (summarization, comparison, fact-checking), and produces structured output.
3. **Obsidian** is the knowledge output system — Claude Code pushes organized, summarized notes into Obsidian via a separate MCP server, creating a personal knowledge base from the analyzed material.

The pipeline is: **collect (Lenie) → analyze (Claude) → organize (Obsidian)**.

The `/ai_ask` endpoint was removed in Sprint 3 because it no longer fit this model. The internal `ai_ask()` function in `backend/library/ai.py` was preserved — it's still used by `youtube_processing.py` to generate AI summaries of video transcriptions during the ingestion phase.

## Three Sprints of Infrastructure Cleanup

### Sprint 1: IaC Coverage & Migration (Epics 1-6)

The project started with manual AWS resource creation. Sprint 1 brought everything under CloudFormation: DynamoDB tables, S3 buckets, Lambda layers, CloudFront distribution, API Gateway. The most complex piece was Story 4.2 — codifying the API Gateway, which had 23 live endpoints versus 11 documented ones. The template nearly exceeded CloudFormation's 51200-byte inline limit.

### Sprint 2: Cleanup & Vision (Epics 7-9)

With infrastructure codified, Sprint 2 focused on removing unnecessary resources. The Step Function schedule was updated from UTC to Warsaw time. The `/url_add2` duplicate endpoint was removed. DynamoDB cache tables (superseded by S3+SQS) were deleted along with all related code. Project vision and roadmap documentation were created.

### Sprint 3: Code Cleanup (Epics 10-12)

Sprint 3 tackled dead code. Three endpoints were removed (`/ai_ask`, `/translate`, `/infra/ip-allow`), one dead function was deleted (`ai_describe_image`), and CloudFormation templates were improved (tagging, parameterization, deployment patterns). The sprint concluded with a codebase-wide verification (Story 12.1) confirming zero stale references remained.

## Cost-Driven Architecture

Lenie is a hobby project with an $8/month AWS budget target. This constraint drives several architectural decisions:

- **No NAT Gateway** ($30/month saved) — Lambda functions are split between VPC (database access) and non-VPC (internet access).
- **RDS on demand** — PostgreSQL starts only when there's work to do, controlled by Step Functions with SQS queue monitoring.
- **DynamoDB PAY_PER_REQUEST** — acts as an always-available buffer for incoming documents while RDS sleeps.
- **API Gateway with API keys** — no need to maintain and patch internet-facing servers.

## Multi-Cloud as a Learning Tool

The project intentionally uses multiple IaC tools (CloudFormation, Terraform, Kubernetes/Kustomize/Helm) not because the workload requires it, but as a hands-on comparison. CloudFormation manages the majority of resources. Terraform handles VPC and bastion host. Kubernetes provides an alternative deployment target. Each approach has its own subdirectory and documentation, making it easy to compare patterns and trade-offs.
