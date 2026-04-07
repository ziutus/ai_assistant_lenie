# Backlog Reference

Quick reference of all backlog items. For full specifications (acceptance criteria, technical notes, user stories), see the [main backlog](./../_bmad-output/planning-artifacts/epics/backlog.md).

## Sprint 6: Security Verification

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-64 | Verify Pre-Commit Secret Detection | backlog | — |

## Frontend Architecture & API Contract

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-49 | Extract Shared TypeScript Types to shared/ Package | DONE (2026-02-25) | — |
| B-50 | API Type Synchronization Pipeline (Pydantic -> OpenAPI -> TypeScript) | backlog | B-49 |
| B-51 | Frontend Deployment Scripts with SSM | DONE (2026-02-25) | — |

## Infrastructure — Vault

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-78 | Vault Auto-Unseal via AWS KMS for NAS Deployment | DONE (2026-02-27) | — |

## Architecture Decisions

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-67 | Choose Compute Model for Serverless YouTube Processing | backlog | — |

## Config Loader Improvements

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-65 | Handle Empty String Values in Config.require() | backlog | — |
| B-66 | Add Tests for env_to_vault.py Script | subsumed by Story 20-6 | — |

## Technology Upgrades

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-68 | Upgrade Python Runtime in Lambda to 3.12+ | backlog | — |
| B-69 | Upgrade Docker/NAS PostgreSQL from 17 to 18 | DONE (2026-03-07) | — |
| B-75 | Standardize Node.js Version to 24 LTS | backlog | — |
| B-77 | Upgrade React to 19 and Vite to 7 in Main Frontends | backlog | — |

## CI/CD Pipeline

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-70 | Restore CI/CD — Common Prerequisites | backlog | — |
| B-71 | CI/CD — GitHub Actions Pipeline | backlog | B-70 |
| B-72 | CI/CD — CircleCI Pipeline | backlog | B-70 |
| B-73 | CI/CD — GitLab CI Pipeline | backlog | B-70 |
| B-74 | CI/CD — Jenkins Pipeline | backlog | B-70 |
| B-76 | Restore pytest-html for CI/CD Test Reports | backlog | B-70 |

## Security — CodeQL & SAST Findings

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-86 | Triage CodeQL Clear-Text Logging Alerts (12 HIGH) | backlog | — |
| B-87 | Fix Stack Trace Exposure in server.py Error Handlers (7 MEDIUM) | backlog | — |
| B-88 | Review Reflected XSS Alerts in server.py (8 MEDIUM) | backlog | — |
| B-89 | Fix ReDoS Vulnerability in webdocument_prepare_regexp_by_ai.py | backlog | — |
| B-90 | Add Timeout to All requests Calls (6 locations) | backlog | — |
| B-91 | Migrate SQL F-Strings to Parameterized Queries | backlog | — | **Note:** Migration to psycopg3 would solve this — psycopg3 uses server-side parameter binding by default, making f-string SQL construction unnecessary. Consider combining with psycopg2→psycopg3 migration. See [technology-choices.md](technology-choices.md#psycopg2-raw-sql-no-orm). |

## Document Processing Pipeline Consolidation

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-103 | Consolidate Document Processing Pipeline (do_the_needful + md_decode + article_browser) | backlog | — |

**Epic B-103** — Trzy skrypty (`web_documents_do_the_needful_new.py`, `webdocument_md_decode.py`, `imports/article_browser.py`) mają nakładające się odpowiedzialności w ekstrakcji artykułów z markdown. Główne problemy:

1. **`text_md` zapisywany z pełnym markdown** (cała strona z nawigacją) zamiast wyekstrahowanego artykułu — `do_the_needful` Step 2b zapisuje surowy markdown, a `md_decode` Step 2 wyciąga sam artykuł ale tylko do cache, nie nadpisuje `text_md`
2. **Duplikacja ekstrakcji** — `md_decode` ma ekstrakcję regexp+LLM, `article_browser` ma własną ekstrakcję LLM (niezależną)
3. **Brak jednego pipeline** — flow: `dynamodb_sync` → `do_the_needful` → `md_decode` → `article_browser` wymaga ręcznego uruchamiania 4 skryptów

Cel: jeden spójny pipeline gdzie `text_md` zawiera wyekstrahowany artykuł (z formatowaniem h1/h2/h3), a `text` czystą treść. Ekstrakcja (regexp + LLM fallback) w jednym miejscu, reużywana przez wszystkie skrypty.

## Data Architecture — Graph Relationships

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| B-102 | Evaluate Neo4j AuraDB Free for Document Relationship Graph | backlog | B-92 |
