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

### Sprint 6: Secrets Management & Security Verification (IN PROGRESS)

- Epic 20: Secrets Management — Migrate .env to Vault & AWS SSM — [epic-20.md](epic-20.md)
- B-64: Verify Pre-Commit Secret Detection — [backlog.md](backlog.md#b-64-verify-pre-commit-secret-detection)

## Backlog Items

- **B-50:** API Type Synchronization Pipeline (Pydantic → OpenAPI → TypeScript) — backlog
- **Details:** [backlog.md](backlog.md)
