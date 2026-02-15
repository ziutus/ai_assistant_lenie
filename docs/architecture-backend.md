# Architecture — Backend API

> Generated: 2026-02-13 | Part: backend | Type: REST API | Framework: Flask

## Architecture Pattern

**Layered API with Service Pattern**: Flask routes → library services → database layer

```
HTTP Request
  ↓
Flask Route (server.py) → check_auth_header() → x-api-key validation
  ↓
Library Service (library/*.py) → business logic, LLM routing, text processing
  ↓
Data Access (stalker_web_document_db.py, stalker_web_documents_db_postgresql.py) → raw psycopg2
  ↓
PostgreSQL 17 + pgvector
```

## Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| Language | Python | >= 3.11 |
| Framework | Flask + Flask-CORS | latest |
| Database | PostgreSQL + pgvector | 17 |
| ORM | None (raw psycopg2) | — |
| Package Manager | uv (hatchling build) | latest |
| LLM | OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik | multi-provider |
| Embeddings | ada-002, Titan v1/v2, BAAI/bge-multilingual | 1536-dim |
| Content | BeautifulSoup4, Markdownify, Firecrawl | latest |
| Speech | AssemblyAI, AWS Transcribe | latest |
| Cloud SDK | boto3 (AWS), google-api-python-client | latest |
| Secrets | hvac (HashiCorp Vault) | latest |
| Monitoring | Langfuse, AWS X-Ray SDK | latest |
| Testing | pytest + pytest-html | latest |
| Linting | ruff (line-length=120) | latest |

## Core Architecture

### LLM Abstraction Layer

`library/ai.py` acts as a router for 11+ models across 4 providers:

| Provider | Models | Module |
|----------|--------|--------|
| OpenAI | gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4o-mini | `api/openai/openai_my.py` |
| AWS Bedrock | amazon.titan-tg1-large, amazon.nova-micro/pro | `api/aws/bedrock_ask.py` |
| Google Vertex AI | gemini-2.0-flash-lite-001 | `api/google/google_vertexai.py` |
| CloudFerro | Bielik-11B-v2.3-Instruct | `api/cloudferro/sherlock/sherlock.py` |

Entry point: `ai_ask(query, model, temperature, max_token_count, top_p) → AiResponse`

### Embedding Abstraction Layer

`library/embedding.py` routes to 4 embedding models:

| Provider | Model | Dimensions |
|----------|-------|-----------|
| OpenAI | text-embedding-ada-002 | 1536 |
| AWS Bedrock | amazon.titan-embed-text-v1 | 1536 |
| AWS Bedrock | amazon.titan-embed-text-v2:0 | 1536 |
| CloudFerro | BAAI/bge-multilingual-gemma2 | varies |

Entry point: `get_embedding(model, text) → EmbeddingResult`

### Domain Model

```
StalkerWebDocument (base, 30 attrs)
  └── StalkerWebDocumentDB (+ save/delete/embedding ops)
       └── Uses WebsitesDBPostgreSQL (query layer)
```

### Content Processing Pipeline

1. **Download**: `download_raw_html(url)` → raw bytes
2. **Parse**: `webpage_raw_parse(url, html)` → WebPageParseResult (text, title, summary, language)
3. **Clean**: `webpage_text_clean(url, text)` → cleaned text (site-specific regex rules)
4. **Split**: `split_text_for_embedding(text, titles, max_words)` → text chunks
5. **Embed**: `get_embedding(model, chunk)` → vector (1536 dims)
6. **Store**: `StalkerWebDocumentDB.save()` + `embedding_add_simple(vector, model)`

### Batch Processing

Standalone scripts for bulk operations (not part of Flask API):

| Script | Pipeline |
|--------|----------|
| `web_documents_do_the_needful_new.py` | SQS polling → DB insert → YouTube processing → language detection → embedding |
| `webdocument_md_decode.py` | Markdown decoding → link extraction → correction → embedding |
| `youtube_add.py` | CLI: YouTube URL → metadata → transcript → optional AI summary → DB |
| `markdown_to_embedding.py` | Local markdown files → embedding generation |

## Data Architecture

### PostgreSQL Schema

- **web_documents** (28 columns): Document storage with content, metadata, multilingual fields, processing state
- **websites_embeddings** (8 columns): Vector embeddings with IVFFlat cosine similarity index

### Document Lifecycle

```
URL_ADDED → DOCUMENT_INTO_DATABASE → NEED_MANUAL_REVIEW → READY_FOR_TRANSLATION → READY_FOR_EMBEDDING → EMBEDDING_EXIST
```

15 processing states, 14 error states, 6 document types (movie, youtube, link, webpage, text_message, text)

## API Design

19 REST endpoints organized in 4 categories:
- **Document CRUD** (7): url_add, website_list, website_get, website_save, website_delete, website_get_next_to_correct, website_exist
- **Content Processing** (4): website_download_text_content, website_text_remove_not_needed, website_split_for_embedding, website_is_paid
- **AI Operations** (3): ai_get_embedding, website_similar, ai_ask
- **Health & Info** (5): healthz, startup, readiness, liveness, version

Authentication: `x-api-key` header on all routes except health checks.

## Testing Strategy

- **Unit tests** (9 files): Text processing, markdown operations, paywall detection — no external dependencies
- **Integration tests** (5 files): REST API endpoint testing — requires PostgreSQL
- **Framework**: pytest with unittest.TestCase
- **Config**: `pyproject.toml [tool.pytest.ini_options]`

## Deployment

### Docker
- Base: python:3.11-slim, package manager: uv
- Installs: `uv sync --frozen --extra docker --no-dev`
- Copies only `library/` and `server.py`
- Port 5000, user: lenie-ai-client (UID 1000)

### AWS Lambda
- Split into two functions (VPC vs public) to avoid NAT Gateway costs
- Shared code via Lambda layers (psycopg2, lenie_all, openai)
- `/url_add` replaced by SQS-based async flow
