---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# lenie-server-2025 - Epic Breakdown

## Overview

This document serves as the index for all epics in lenie-server-2025. Individual epics are stored as separate files. Completed sprint epics are archived in `archive/`.

## Sprint History

### Sprint 1: IaC Coverage & Migration (DONE)

- Epic 1: Storage Layer IaC Coverage
- Epic 2: Compute Layer IaC Coverage
- Epic 3: S3 Content Migration
- Epic 4: Application Delivery IaC Coverage
- Epic 5: AWS Account Cleanup & Code Hygiene
- Epic 6: Deployment Orchestration & Documentation

### Sprint 2: Cleanup & Vision Documentation (DONE)

- Epic 7: Step Function Update & API Gateway Simplification
- Epic 8: DynamoDB Cache Table Removal
- Epic 9: Project Vision & Documentation Update

### Sprint 3: Code Cleanup — Endpoint & Dead Code Removal (DONE)

- Epic 10: Endpoint & Dead Code Removal
- Epic 11: CloudFormation Template Improvements
- Epic 12: Cross-Cutting Verification & Documentation

### Sprint 4: AWS Infrastructure Consolidation & Tooling (DONE)

- Epic 13: Operational Safety & Tooling — [archived](../archive/epics-sprint4-infra-consolidation-2026-02-26.md)
- Epic 14: Infrastructure Cost & Naming Cleanup — [archived](../archive/epics-sprint4-infra-consolidation-2026-02-26.md)
- Epic 15: API Gateway Consolidation — [archived](../archive/epics-sprint4-infra-consolidation-2026-02-26.md)
- Epic 16: Documentation Consolidation & Verification — [archived](../archive/epics-sprint4-infra-consolidation-2026-02-26.md)

### Sprint 5: Operational Fixes & Lambda Analysis (DONE)

- Epic 17: Operational Safety & Bug Fixes — [archived](../archive/epics-sprint5-ops-fixes-lambda-2026-02-26.md)
- Epic 18: Lambda Consolidation Analysis — [archived](../archive/epics-sprint5-ops-fixes-lambda-2026-02-26.md)

### Backlog (Completed)

- Epic 19: Multi-User Admin Interface (app2) — [archived](../archive/epics-app2-and-completed-backlog-2026-02-26.md)

### Sprint 6: Secrets Management & Security Verification (DONE)

- Epic 20: Secrets Management — Migrate .env to Vault & AWS SSM — [epic-20.md](epic-20.md)
- B-64: Verify Pre-Commit Secret Detection — [backlog.md](backlog.md#b-64-verify-pre-commit-secret-detection)

### Sprint 7: Slack Bot MVP & Config Loader Migration (IN PROGRESS)

- Epic 21: Slack Bot MVP — Slash Commands — [archived](../archive/epics-whole-2026-04-15.md#epic-21-slack-bot-mvp--slash-commands)
- B-79: Migrate Standalone Scripts to config_loader — [backlog.md](backlog.md#b-79-migrate-standalone-scripts-to-config-loader)

### Future Sprint 8: Slack Bot Enhancements

- Epic 22: Direct Message Interaction — [archived](../archive/epics-whole-2026-04-15.md#epic-22-direct-message-interaction)
- Epic 23: Channel App Mentions — [archived](../archive/epics-whole-2026-04-15.md#epic-23-channel-app-mentions)
- Epic 24: Conversational LLM Intelligence — [archived](../archive/epics-whole-2026-04-15.md#epic-24-conversational-llm-intelligence)
- Epic 25: Proactive Health Monitoring — [archived](../archive/epics-whole-2026-04-15.md#epic-25-proactive-health-monitoring)

### Sprint 9: SQLAlchemy ORM Migration

- Epic 26: ORM Foundation & Schema Management — [epic-26.md](epic-26.md)
- Epic 27: Document CRUD & API Serving — [epic-27.md](epic-27.md)
- Epic 28: Vector Embeddings & Similarity Search — [epic-28.md](epic-28.md)
- Epic 29: Data Pipeline Migration & Cleanup — [epic-29.md](epic-29.md)

### Sprint 10: Database Lookup Tables & Search Extensions (DONE)

- Epic 30: Database Lookup Tables & Search Extensions (B-93, B-94, B-95, B-96, B-97)

### Sprint 11: Code Quality, Security & Service Layer

- Epic 31: Security Fixes & Project Governance (B-87, B-85, B-86)
- Epic 32: Service Layer Extraction (B-56)
- Epic 33: Import Pipeline Maturity — Cache Consolidation, Operation Logging & Article Review Tracking — [epic-33.md](epic-33.md)

### Sprint 14: MCP Server MVP — Mobile Knowledge Workflow

- Epic 35 (MCP-A): MCP Server Foundation — Python SDK, Docker container — [epic-35.md](epic-35.md)
- Epic 36 (MCP-B): Lenie Read Tools — lenie_unreviewed_articles, lenie_get_article, lenie_search — [epic-36.md](epic-36.md)
- Epic 37 (MCP-C): Lenie Write Tools — lenie_delete_article, article-obsidian linking — [epic-37.md](epic-37.md)
- Epic 38 (MCP-D): Obsidian Tools + Version History — 5 narzędzi + obsidian_note_versions table — [epic-38.md](epic-38.md)
- Epic 39 (MCP-E): Cloudflare Infrastructure — domain, Tunnel, MCP Server Portal — [epic-39.md](epic-39.md)
- Epic 40 (MCP-F): End-to-End Integration — obsidian-headless, Custom Connector, MVP gate — [epic-40.md](epic-40.md)

## Backlog Items

- **B-50:** API Type Synchronization Pipeline (Pydantic → OpenAPI → TypeScript) — backlog
- **B-82:** Add MinIO as S3-Compatible Local Storage for NAS Development — in progress (step 1 done: MinIO on NAS)
- **B-105:** Scheduled Daily DynamoDB Sync on NAS (QTS cron) — backlog
- **Details:** [backlog.md](backlog.md)
