# Project Documentation Index — Lenie Server 2025

> Generated: 2026-02-13 | Version: 0.3.13.0 | Scan: Exhaustive

## Project Overview

- **Type:** Multi-part Monorepo with 5 parts
- **Primary Languages:** Python 3.11 (backend), JavaScript/React 18 (frontends)
- **Architecture:** Layered REST API + SPA + Serverless + Multi-cloud IaC
- **Database:** PostgreSQL 17 + pgvector (1536-dim vector similarity search)

## Quick Reference

### Backend API (`backend/`)
- **Type:** REST API (Flask)
- **Tech Stack:** Python 3.11, Flask, psycopg2, uv
- **Entry Point:** `server.py` (18 endpoints)
- **Architecture:** Layered API with service pattern

### Main Frontend (`web_interface_react/`)
- **Type:** Web SPA
- **Tech Stack:** React 18, CRA, React Router v6, Formik, axios
- **Entry Point:** `src/index.js`
- **Architecture:** Context + Hooks + Pages

### Add URL App (`web_add_url_react/`)
- **Type:** Web SPA (minimal)
- **Tech Stack:** React 18, CRA, axios
- **Entry Point:** `src/App.js`
- **Architecture:** Single component

### Browser Extension (`web_chrome_extension/`)
- **Type:** Chrome Extension (Manifest v3)
- **Tech Stack:** Vanilla JavaScript, Bootstrap CSS
- **Entry Point:** `popup.js`
- **Architecture:** Single-file popup

### Infrastructure (`infra/`)
- **Type:** Infrastructure as Code
- **Tech Stack:** Docker Compose, AWS CloudFormation, Kustomize, Helm, Terraform
- **Entry Point:** `docker/compose.yaml`
- **Architecture:** Multi-cloud deployment

## Generated Documentation

### Overview & Structure
- [Project Overview](./project-overview.md) — Executive summary, tech stack, design decisions
- [Source Tree Analysis](./source-tree-analysis.md) — Annotated directory structure, critical folders, integration points
- [Integration Architecture](./integration-architecture.md) — How parts communicate, data flows, shared dependencies

### Architecture (per part)
- [Architecture — Backend](./architecture-backend.md) — Flask API layers, LLM abstraction, content pipeline
- [Architecture — Main Frontend](./architecture-web_interface_react.md) — React SPA, state management, hooks
- [Architecture — Browser Extension](./architecture-web_chrome_extension.md) — Manifest v3, content extraction
- [Architecture — Infrastructure](./architecture-infra.md) — Docker, AWS, Kubernetes, GCloud, CI/CD

### API & Data
- [API Contracts — Backend](./api-contracts-backend.md) — All 18 REST endpoints with request/response formats
- [Data Models — Backend](./data-models-backend.md) — PostgreSQL schema, enums, domain models, DynamoDB

### Components
- [Component Inventory — Main Frontend](./component-inventory-web_interface_react.md) — 7 pages, 6 reusable components, 7 hooks, state management

### Guides
- [Development Guide](./development-guide.md) — Prerequisites, setup, running, testing, code quality
- [Project Parts Metadata](./project-parts.json) — Machine-readable project structure

## Existing Documentation

### Root Level
- [README.md](../README.md) — Project overview
- [CLAUDE.md](../CLAUDE.md) — Claude Code guidance

### Backend
- [backend/CLAUDE.md](../backend/CLAUDE.md) — Backend API documentation
- [backend/library/CLAUDE.md](../backend/library/CLAUDE.md) — Core logic & integrations
- [backend/database/CLAUDE.md](../backend/database/CLAUDE.md) — PostgreSQL schema & states
- [backend/tests/CLAUDE.md](../backend/tests/CLAUDE.md) — Test suite documentation
- [backend/data/CLAUDE.md](../backend/data/CLAUDE.md) — Site cleanup rules
- [backend/imports/CLAUDE.md](../backend/imports/CLAUDE.md) — Bulk import scripts
- [backend/test_code/CLAUDE.md](../backend/test_code/CLAUDE.md) — Experimental scripts

### Frontends & Extension
- [web_interface_react/CLAUDE.md](../web_interface_react/CLAUDE.md) — Main frontend docs
- [web_add_url_react/CLAUDE.md](../web_add_url_react/CLAUDE.md) — Add URL app docs
- [web_chrome_extension/CLAUDE.md](../web_chrome_extension/CLAUDE.md) — Browser extension docs

### Infrastructure
- [infra/aws/README.md](../infra/aws/README.md) — AWS architecture (644 lines)
- [infra/aws/cloudformation/CLAUDE.md](../infra/aws/cloudformation/CLAUDE.md) — CloudFormation templates
- [infra/aws/serverless/CLAUDE.md](../infra/aws/serverless/CLAUDE.md) — Lambda functions
- [infra/aws/eks/CLAUDE.md](../infra/aws/eks/CLAUDE.md) — EKS documentation

### Operations
- [CI/CD Specification](./CI_CD.md) — Generic pipeline spec
- [CI/CD Tools](./CI_CD_Tools.md) — CircleCI, GitLab CI, Jenkins
- [Docker Local](./Docker_Local.md) — Local development with Docker
- [AWS Infrastructure](./AWS_Infrastructure.md) — AWS resource documentation
- [Code Quality](./Code_Quality.md) — Linting and security tools
- [Python Dependencies](./Python_Dependencies.md) — uv package management

## Getting Started

### For AI-Assisted Development
1. Start with this `index.md` as the primary entry point
2. Read [Project Overview](./project-overview.md) for high-level understanding
3. Check [Architecture docs](./architecture-backend.md) for the part you're working on
4. Reference [API Contracts](./api-contracts-backend.md) for endpoint details
5. Use [Data Models](./data-models-backend.md) for database schema

### For Local Development
1. Follow [Development Guide](./development-guide.md) for setup instructions
2. Run `make build && make dev` for Docker stack
3. Access: Backend at :5000, Frontend at :3000, Database at :5433

### For Feature Planning (Brownfield PRD)
When ready to plan new features, run the BMM PRD workflow and provide this index as input context. The documentation covers all parts, integration points, and existing patterns needed for informed feature planning.
