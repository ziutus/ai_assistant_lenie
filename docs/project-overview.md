# Project Overview — Lenie Server 2025

> Generated: 2026-02-13 | Version: 0.3.13.0 | Status: Active Development

## Executive Summary

**Project Lenie** is a personal AI assistant for collecting, managing, and searching data using LLMs. Named after the protagonist from Peter Watts' novel "Starfish," it helps users collect links/references, download and store webpage content, transcribe YouTube videos, and assess information reliability using AI.

The system consists of a Python/Flask REST API backend, two React frontend applications, a Chrome browser extension, and multi-cloud infrastructure (AWS, GCloud, Kubernetes).

## Repository Structure

| Property | Value |
|----------|-------|
| **Type** | Multi-part Monorepo |
| **Parts** | 5 (backend, main frontend, add URL app, browser extension, infrastructure) |
| **Primary Language** | Python 3.11 (backend), JavaScript/React 18 (frontends) |
| **Architecture** | Layered REST API + SPA + Serverless |
| **Database** | PostgreSQL 17 + pgvector |
| **Version** | 0.3.13.0 |
| **License** | MIT |

## Parts Summary

### Backend API (`backend/`)
Flask REST API with 19 endpoints for document CRUD, AI operations (LLM queries, embedding generation, similarity search), and content processing (webpage download, text cleanup, YouTube transcription). Multi-provider LLM abstraction supporting OpenAI, AWS Bedrock, Google Vertex AI, and CloudFerro Bielik.

### Main Frontend (`web_interface_react/`)
React 18 SPA with 7 pages for document management. Features include document list with filtering, vector similarity search, and per-type editors (link, webpage, youtube, movie) with AI tools (correct, translate, split for embedding, clean text). Supports two backend modes: AWS Serverless and Docker.

### Add URL App (`web_add_url_react/`)
Minimal single-page React app for submitting new URLs via `POST /url_add`. No routing, no document browsing — just a form with URL, type, source, language, note, and text fields. API key can be pre-populated from `?apikey=` query parameter.

### Browser Extension (`web_chrome_extension/`)
Chrome/Kiwi browser extension (Manifest v3) for capturing webpages and sending to backend. Auto-extracts title, description, language, and full content (text + HTML). Supports content types: webpage, link, youtube, movie. No build step.

### Infrastructure (`infra/`)
Multi-cloud IaC supporting Docker Compose (local), AWS (CloudFormation + Lambda), Kubernetes (GKE with Kustomize/Helm), and GCloud (Terraform). Includes 29 CloudFormation templates, 12 Lambda functions, and CI/CD pipelines (CircleCI, GitLab CI, Jenkins).

## Technology Stack

| Category | Technologies |
|----------|-------------|
| **Backend** | Python 3.11, Flask, psycopg2, uv |
| **Frontend** | React 18, CRA, React Router v6, Formik, axios |
| **Database** | PostgreSQL 17, pgvector (1536-dim vectors) |
| **AI/LLM** | OpenAI (GPT-4o), AWS Bedrock (Titan, Nova), Google Vertex (Gemini), CloudFerro (Bielik) |
| **Embeddings** | text-embedding-ada-002, amazon.titan-embed-text, BAAI/bge-multilingual-gemma2 |
| **Content** | BeautifulSoup4, Markdownify, Firecrawl, YouTube Transcript API |
| **Speech** | AssemblyAI, AWS Transcribe |
| **Cloud** | AWS (Lambda, RDS, SQS, DynamoDB, API Gateway, S3), GCP (Cloud Run, Terraform) |
| **Container** | Docker, Docker Compose, Kubernetes (GKE) |
| **CI/CD** | CircleCI, GitLab CI, Jenkins |
| **Security** | pre-commit, TruffleHog, Semgrep, Bandit, pip-audit |
| **Secrets** | HashiCorp Vault (hvac) |

## Deployment Modes

1. **Local/Docker**: Docker Compose stack — Flask (5000), PostgreSQL (5433), React (3000)
2. **AWS Serverless**: Lambda functions + API Gateway + SQS + DynamoDB + RDS
3. **Kubernetes**: GKE deployment with Kustomize overlays and Helm charts
4. **GCloud**: Cloud Run + Terraform

## Key Design Decisions

- **No ORM**: Raw psycopg2 for PostgreSQL access (direct control over queries)
- **Multi-provider LLM**: Abstract layer routing to OpenAI/Bedrock/Vertex/Sherlock based on model ID
- **Lambda split**: Two Lambda functions (VPC for DB, public for internet) to avoid NAT Gateway costs
- **SQS ingestion**: Asynchronous document processing via SQS queue instead of direct DB writes
- **DynamoDB cache**: Always-available metadata storage for cloud-local synchronization
- **Site-specific cleanup**: JSON-based regex rules per Polish news portal domain
