# Integration Architecture

> Generated: 2026-02-13 | Project: lenie-server-2025 | Type: Multi-part Monorepo

## Integration Overview

4 parts communicate primarily via REST API. The backend serves as the central hub, with the frontend and the extension acting as API clients.

```
┌─────────────────────┐     ┌─────────────────────┐
│  web_interface_react │     │ web_chrome_extension │
│  (React 18 SPA)     │     │ (Chrome Manifest v3) │
│  Port: 3000         │     │ Browser popup        │
└─────────┬───────────┘     └──────────┬───────────┘
          │ axios                       │ fetch
          │ 19+ endpoints              │ POST /url_add
          │ x-api-key                   │ x-api-key
          ▼                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
│  Docker: Flask server.py (port 5000)                                        │
│  AWS: API Gateway → Lambda (app-server-db + app-server-internet)            │
│  K8s: Flask Deployment (port 5000) via Ingress                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│ PostgreSQL 17   │    │ External APIs    │    │ AWS Services         │
│ + pgvector      │    │ OpenAI, Bedrock  │    │ S3, SQS, DynamoDB    │
│ (web_documents, │    │ Vertex AI        │    │ Transcribe           │
│  embeddings)    │    │ AssemblyAI       │    │                      │
└─────────────────┘    └──────────────────┘    └──────────────────────┘
```

## Integration Points

### 1. web_interface_react → backend

| Integration | Details |
|------------|---------|
| **Type** | REST API (axios HTTP client) |
| **Auth** | `x-api-key` header |
| **Content-Type** | `application/x-www-form-urlencoded` (most), `multipart/form-data` (file upload) |
| **Endpoints** | 19+ (Document CRUD, AI operations, content processing, infrastructure control) |
| **Backend modes** | AWS Serverless (two Lambda endpoints) or Docker (single Flask) |
| **Toggle** | UI dropdown in Authorization panel switches `apiType` |

Key differences between AWS and Docker modes:
- **Search**: AWS uses two calls (`/ai_embedding_get` → `/website_similar`), Docker uses one call
- **Infrastructure**: `/infra/*` endpoints only work in AWS mode

### 2. web_chrome_extension → backend

| Integration | Details |
|------------|---------|
| **Type** | REST API (fetch API) |
| **Auth** | `x-api-key` header (stored in chrome.storage.sync) |
| **Content-Type** | `application/json` |
| **Endpoint** | `POST /url_add` (configurable server URL) |
| **Default URL** | AWS API Gateway endpoint |
| **Extra data** | Sends page text (innerText) + HTML (outerHTML) |

### 3. infra → backend (Deployment)

| Target | Mechanism |
|--------|-----------|
| Docker Compose | `compose.yaml` builds from `backend/Dockerfile` |
| AWS Lambda | `zip_to_s3.sh` packages `backend/library/` into Lambda zip |
| Kubernetes | Docker Hub image `lenieai/lenie-ai-server:latest` |

### 4. infra → web_interface_react (Deployment)

| Target | Mechanism |
|--------|-----------|
| Docker Compose | `compose.yaml` builds from `web_interface_react/Dockerfile` |
| Kubernetes | Docker Hub image `lenieai/lenie-ai-frontend:latest` |

## Data Flow: Document Ingestion

### Docker/Kubernetes Path
```
Client → POST /url_add → Flask server.py → StalkerWebDocumentDB.save() → PostgreSQL
```

### AWS Serverless Path
```
Client → API Gateway → Lambda (sqs-weblink-put-into)
  → S3 (text/HTML content)
  → DynamoDB (metadata: pk=DOCUMENT, sk=timestamp#uuid)
  → SQS (processing message, 14s delay)
Step Function → Lambda (rds-start) → Lambda (sqs-into-rds) → PostgreSQL → Lambda (rds-stop)
```

## Data Flow: Document Retrieval

```
React Frontend → GET /website_list or GET /website_get
  → Flask/Lambda → WebsitesDBPostgreSQL.get_list() → PostgreSQL → JSON response
```

## Data Flow: Vector Similarity Search

### Docker Path
```
React Frontend → POST /website_similar {search, model, limit}
  → Flask → get_embedding(model, search) → get_similar(vector, model, limit) → PostgreSQL pgvector
```

### AWS Serverless Path
```
React Frontend → POST /ai_embedding_get {text, model} → Lambda Internet → embedding vector
React Frontend → POST /website_similar {embedds, model, limit} → Lambda DB → PostgreSQL pgvector
```

## Shared Dependencies

- **API contract**: All clients use same `x-api-key` authentication
- **Document model**: All clients work with the same 28-field document structure
- **Content-Type**: Main frontend uses form-urlencoded, others use JSON
- **Backend library**: AWS Lambda functions import `backend/library/` as a layer
