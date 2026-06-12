# Architecture â€” Backend API

> Generated: 2026-02-13 | Part: backend | Type: REST API | Framework: Flask

## Architecture Pattern

**Layered API with Service Pattern**: Flask routes â†’ library services â†’ database layer

```
HTTP Request
  â†“
Flask Route (server.py) â†’ check_auth_header() â†’ x-api-key validation
  â†“
Library Service (library/*.py) â†’ business logic, LLM routing, text processing
  â†“
Data Access (stalker_web_document_db.py, stalker_web_documents_db_postgresql.py) â†’ raw psycopg2
  â†“
PostgreSQL 18 + pgvector
```

## Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| Language | Python | >= 3.11 |
| Framework | Flask + Flask-CORS | latest |
| Database | PostgreSQL + pgvector | 18 |
| ORM | None (raw psycopg2) | â€” |
| Package Manager | uv (hatchling build) | latest |
| LLM | OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik | multi-provider |
| Embeddings | ada-002, Titan v1/v2, BAAI/bge-multilingual | 1024-1536 dim (model-dependent) |
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

Entry point: `ai.ai_ask(query, model, temperature, max_token_count, top_p) â†’ AiResponse` (internal library function, not exposed as REST endpoint)

### Embedding Abstraction Layer

`library/embedding.py` routes to 4 embedding models:

| Provider | Model | Dimensions |
|----------|-------|-----------|
| OpenAI | text-embedding-ada-002 | 1536 |
| AWS Bedrock | amazon.titan-embed-text-v1 | 1536 |
| AWS Bedrock | amazon.titan-embed-text-v2:0 | 1024 |
| CloudFerro | BAAI/bge-multilingual-gemma2 | varies |

Entry point: `get_embedding(model, text) â†’ EmbeddingResult`

### Domain Model

```
StalkerWebDocument (base, 30 attrs)
  â””â”€â”€ StalkerWebDocumentDB (+ save/delete/embedding ops)
       â””â”€â”€ Uses WebsitesDBPostgreSQL (query layer)
```

### Content Processing Pipeline

1. **Download**: `download_raw_html(url)` â†’ raw bytes
2. **Parse**: `webpage_raw_parse(url, html)` â†’ WebPageParseResult (text, title, summary, language)
3. **Clean**: `webpage_text_clean(url, text)` â†’ cleaned text (site-specific regex rules)
4. **Split**: `split_text_for_embedding(text, titles, max_words)` â†’ text chunks
5. **Embed**: `get_embedding(model, chunk)` â†’ vector (dimensions vary by model)
6. **Store**: `StalkerWebDocumentDB.save()` + `embedding_add_simple(vector, model)`

### Batch Processing

Standalone scripts for bulk operations (not part of Flask API):

| Script | Pipeline |
|--------|----------|
| `web_documents_do_the_needful_new.py` | SQS polling â†’ DB insert â†’ YouTube processing â†’ language detection â†’ embedding |
| `webdocument_md_decode.py` | Markdown decoding â†’ link extraction â†’ correction â†’ embedding |
| `youtube_add.py` | CLI: YouTube URL â†’ metadata â†’ transcript â†’ optional AI summary â†’ DB |
| `markdown_to_embedding.py` | Local markdown files â†’ embedding generation |

## Data Architecture

### PostgreSQL Schema

- **web_documents** (29 columns): Document storage with content, metadata, multilingual fields, processing state
- **websites_embeddings** (8 columns): Vector embeddings with IVFFlat cosine similarity index

### Document Lifecycle

```
URL_ADDED â†’ DOCUMENT_INTO_DATABASE â†’ NEED_MANUAL_REVIEW â†’ READY_FOR_TRANSLATION â†’ READY_FOR_EMBEDDING â†’ EMBEDDING_EXIST
```

15 processing states, 14 error states, 8 document types (movie, youtube, link, webpage, text_message, text, email, social_media_post)

## API Design

19 REST endpoints organized in 5 categories:
- **Document CRUD** (5): url_add, website_list, website_get, website_save, website_delete
- **Content Processing** (3): website_download_text_content, website_text_remove_not_needed, website_split_for_embedding
- **AI Operations** (2): ai_get_embedding, website_similar
- **Metadata** (2): website_is_paid, website_get_next_to_correct
- **Health & Info** (7): / (root), healthz, metrics, startup, readiness, liveness, version

Authentication: `x-api-key` header on all routes except health checks.

## Testing Strategy

- **Unit tests** (9 files): Text processing, markdown operations, paywall detection â€” no external dependencies
- **Integration tests** (5 files): REST API endpoint testing â€” requires PostgreSQL
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
