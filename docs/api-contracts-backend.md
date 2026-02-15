# API Contracts — Backend

> Generated: 2026-02-13 | Part: backend | Type: REST API (Flask)

## Overview

Flask REST API with **19 endpoints**. Version 0.3.13.0. All routes except health checks require `x-api-key` header validated against `STALKER_API_KEY` environment variable.

**Base URL**: `http://localhost:5000` (Docker) or AWS API Gateway endpoint (serverless)

**Authentication**: `x-api-key` header on all requests (except `/startup`, `/readiness`, `/liveness`, `/version`, `/healthz`)

## Document CRUD

### POST /url_add
Add a new document (URL) to the system.

- **Request**: JSON body
  ```json
  {
    "url": "https://example.com/article",
    "type": "webpage|link|youtube|movie|text_message",
    "note": "User note",
    "text": "Raw text content",
    "html": "Full page HTML",
    "title": "Page Title",
    "language": "pl|en|other",
    "paywall": false,
    "source": "own|twitter|etc",
    "ai_summary": false,
    "ai_correction": false,
    "chapter_list": ""
  }
  ```
- **Response**: `{status, message, document_id}`
- **Note**: In AWS serverless, replaced by `sqs-weblink-put-into` Lambda (S3 + DynamoDB + SQS flow)

### GET /website_list
List documents with filters.

- **Parameters**: `type`, `document_state`, `search_in_document`, `limit`, `offset`
- **Response**: `{status, websites[], all_results_count}`

### GET /website_get
Get a single document by ID.

- **Parameters**: `id` (required)
- **Response**: Document dict with 28 fields (see Data Models)

### POST /website_save
Save/update a document.

- **Request**: Form data — `url`, `id`, `document_state`, `text`, `text_english`, `title`, `language`, `tags`, `summary`, `source`, `author`, `note`, `document_type`
- **Response**: `{status, message}`
- **Side effect**: Calls `.analyze()` on saved document

### GET /website_delete
Delete a document by ID.

- **Parameters**: `id` (required)
- **Response**: `{status, message}`

### GET /website_get_next_to_correct
Get next document to review.

- **Parameters**: `id` (required)
- **Response**: `{status, next_id, next_type}`

### POST /website_exist
Check if URL already exists.

- **Parameters**: `url`
- **Response**: `{status, exists}`

## Content Processing

### POST /website_download_text_content
Download and extract text content from a URL.

- **Request**: Form/JSON — `url`
- **Response**: `{status, text, content, title, summary, language, url}`
- **Calls**: `download_raw_html()` → `webpage_raw_parse()`

### POST /website_text_remove_not_needed
Clean boilerplate text from content using site-specific rules.

- **Request**: Form — `text`, `url`
- **Response**: `{status, text, message}`
- **Calls**: `webpage_text_clean(url, text)` — applies regex rules from `data/site_rules.json`

### POST /website_split_for_embedding
Split text into chunks suitable for embedding.

- **Request**: Form — `text`, `chapter_list`
- **Response**: `{status, text[], message}`
- **Calls**: `chapters_text_to_list()`, `split_text_for_embedding()`

### POST /website_is_paid
Check if a URL is behind a paywall.

- **Request**: Form/JSON/GET — `url`
- **Response**: `{status, is_paid, url}`

## AI Operations

### POST /ai_get_embedding
Generate embedding vector for text.

- **Request**: Form/JSON/GET — `search`
- **Response**: `{status, text, embedding[], message}`
- **Calls**: `library.embedding.get_embedding()`
- **Supported models**: text-embedding-ada-002, amazon.titan-embed-text-v1/v2, BAAI/bge-multilingual-gemma2

### POST /website_similar
Find documents similar to query text.

- **Request**: Form/JSON/GET — `search`, `limit`
- **Response**: `{status, websites[], text, message}`
- **Calls**: `embedding.get_embedding()` → `websites.get_similar()` (pgvector cosine similarity)

### POST /ai_ask
Ask an AI model a question or process text.

- **Request**: Form — `text`, `query`, `model`
- **Response**: `{status, text, model, message}`
- **Supported models**: gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4o-mini, amazon.titan-tg1-large, amazon.nova-micro/pro, Bielik-11B, gemini-2.0-flash-lite

## Health & Information

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/` | GET | No | `{status, message, app_version, build_time}` |
| `/healthz` | GET | No | `{status: "OK", message}` |
| `/startup` | GET | No | K8s startup probe |
| `/readiness` | GET | No | K8s readiness probe |
| `/liveness` | GET | No | K8s liveness probe |
| `/version` | GET | No | `{status, app_version, build_time}` |
| `/metrics` | GET | No | Prometheus format (not implemented) |

## AWS Serverless Split

In the AWS Lambda deployment, endpoints are split across two functions:

**app-server-db** (runs inside VPC — PostgreSQL access):
`/website_list`, `/website_get`, `/website_save`, `/website_delete`, `/website_is_paid`, `/website_get_next_to_correct`, `/website_similar`, `/website_split_for_embedding`

**app-server-internet** (runs outside VPC — internet access):
`/translate`, `/website_download_text_content`, `/ai_embedding_get`, `/ai_ask`

**sqs-weblink-put-into** (replaces `/url_add`):
Receives URL data via API Gateway → stores content in S3, metadata in DynamoDB → sends message to SQS
