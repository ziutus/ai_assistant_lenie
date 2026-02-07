# Backend Library — CLAUDE.md

Core library for Project Lenie providing document processing, LLM abstraction, embedding generation, and database persistence.

## Directory Structure

```
library/
├── models/           # Data classes and enums (domain objects)
├── website/          # HTML download, parsing, paywall detection, content cleanup
├── api/              # External service integrations
│   ├── openai/       # OpenAI chat completions & embeddings
│   ├── aws/          # Bedrock, S3, Comprehend, Transcribe
│   ├── google/       # Vertex AI (Gemini)
│   ├── cloudferro/sherlock/  # Bielik Polish LLM & embeddings
│   └── asemblyai/    # Speech-to-text transcription
├── ai.py             # LLM provider abstraction (routes to api/*)
├── embedding.py      # Embedding provider abstraction (routes to api/*)
├── stalker_web_document.py      # Core document domain model
├── stalker_web_document_db.py   # Document model with DB persistence (extends above)
├── stalker_web_documents_db_postgresql.py  # Query layer (list, search, similarity)
├── text_functions.py        # Text processing & splitting utilities
├── text_detect_language.py  # Language detection abstraction
├── text_transcript.py       # Transcript/chapter parsing utilities
├── transcript.py            # Transcription service abstraction
├── lenie_markdown.py        # Markdown processing & splitting for embeddings
├── document_markdown.py     # Markdown image/link reference extraction
├── google_auth.py           # Google OAuth 2.0 utilities
└── stalker_youtube_file.py  # YouTube metadata extraction & download
```

## Key Modules

### Domain Model & Database

- **`stalker_web_document.py`** — `StalkerWebDocument` class: ~30 attributes covering URL, text content (raw/English/markdown), metadata, processing state. Methods: `validate()`, `set_document_type()`, `set_document_state()`.
- **`stalker_web_document_db.py`** — `StalkerWebDocumentDB(StalkerWebDocument)`: adds `save()`, `delete()`, `embedding_add_simple()`, `embedding_delete()`. Loads document from DB on construction. Custom ORM (no SQLAlchemy), uses `psycopg2` directly.
- **`stalker_web_documents_db_postgresql.py`** — `WebsitesDBPostgreSQL`: connection management + queries: `get_list()` (paginated/filtered), `get_similar()` (pgvector cosine search), `get_next_to_correct()`, `get_count()`.

**Database tables:** `public.web_documents` (28 columns), `public.websites_embeddings` (vector similarity).

### Models (`models/`)

| File | Class/Enum | Purpose |
|------|------------|---------|
| `stalker_document_status.py` | `StalkerDocumentStatus` | 15 processing states (URL_ADDED → EMBEDDING_EXIST) |
| `stalker_document_status_error.py` | `StalkerDocumentStatusError` | 14 error types |
| `stalker_document_type.py` | `StalkerDocumentType` | 6 document types (movie, youtube, link, webpage, text_message, text) |
| `ai_response.py` | `AiResponse` | LLM response container (text, tokens, model info) |
| `embedding_result.py` | `EmbeddingResult` | Single embedding result (vector, status, token count) |
| `embedding_results.py` | `EmbeddingResults` | Batch embedding results |
| `webpage_parse_result.py` | `WebPageParseResult` | HTML parse output (text, title, language, summary) |

### LLM Abstraction (`ai.py`)

Entry point: `ai_ask(query, model, temperature, max_token_count, top_p) → AiResponse`

Supported models:
- **OpenAI**: gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4o-mini
- **AWS Bedrock**: amazon.titan-tg1-large, amazon.nova-micro, amazon.nova-pro
- **Google Vertex AI**: gemini-2.0-flash-lite-001
- **CloudFerro**: Bielik-11B-v2.3-Instruct (Polish)
- **Bedrock Vision**: anthropic.claude-3-haiku (via `ai_describe_image()`)

Helper: `ai_model_need_translation_to_english(model)` — checks if model requires English input.

### Embedding Abstraction (`embedding.py`)

Entry point: `get_embedding(model, text) → EmbeddingResult`

Supported models:
- **AWS Bedrock**: amazon.titan-embed-text-v1, amazon.titan-embed-text-v2:0
- **OpenAI**: text-embedding-ada-002
- **CloudFerro**: BAAI/bge-multilingual-gemma2

### Text Processing

- **`text_functions.py`** — `split_text_for_embedding()`, regex-based text removal (`remove_last_occurrence_and_after`, `remove_before_regex`, `remove_after_regex`), SHA256 hashing.
- **`lenie_markdown.py`** — `md_split_for_emb()` (recursive hierarchical splitting: H1→H2→H3→bold→paragraphs→sentences), link/image extraction, markdown cleanup.
- **`document_markdown.py`** — `DocumentMarkDown` class: converts inline images and links to numbered references.
- **`text_transcript.py`** — Chapter/timestamp parsing, transcript splitting by chapters (for YouTube and AWS Transcribe).

### Website Processing (`website/`)

- **`website_download_context.py`** — `download_raw_html()`, `webpage_raw_parse()` (BeautifulSoup), `webpage_text_clean()` (applies site-specific rules from `data/site_rules.json`).
- **`website_paid.py`** — `website_is_paid(link)` — hard-coded paywall detection (wyborcza.pl, onet.pl premium paths).
- **`website_text_clean_regexp.py`** — Site-specific regex cleanup rules for Polish news sites (WP, Onet, Interia, Newsweek, BusinessInsider, etc.).

### API Integrations (`api/`)

| Subdir | Key Functions | Auth |
|--------|--------------|------|
| `openai/openai_my.py` | `OpenAIClient.get_completion()`, `get_completion_image()` | `OPENAI_API_KEY` |
| `openai/openai_embedding.py` | `get_embedding()` (ada-002) | `OPENAI_API_KEY` |
| `aws/bedrock_ask.py` | `query_aws_bedrock()`, `aws_bedrock_describe_image()` | AWS credentials |
| `aws/bedrock_embedding.py` | `get_embedding()` (Titan v1), `get_embedding2()` (Titan v2) | AWS credentials |
| `aws/s3_aws.py` | `s3_file_exist()`, `s3_take_file()` | AWS credentials |
| `aws/transcript.py` | `aws_transcript()` | AWS credentials |
| `aws/text_detect_language_aws.py` | `detect_text_language_aws()` (Comprehend) | AWS credentials |
| `aws/credentionals.py` | `validate_credentials()` (STS) | AWS credentials |
| `google/google_vertexai.py` | `connect_to_google_llm_with_role()` | `GCP_PROJECT_ID`, `GCP_LOCATION` |
| `cloudferro/sherlock/sherlock.py` | `sherlock_get_completion()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `cloudferro/sherlock/sherlock_embedding.py` | `sherlock_create_embedding()`, `sherlock_create_embeddings()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `asemblyai/asemblyai_transcript.py` | `transcript_assemblyai()` | `ASSEMBLYAI` |

### Other Modules

- **`transcript.py`** — Transcription router (`aws`, `assemblyai`, `local`) + `transcript_price()` cost calculator.
- **`google_auth.py`** — Google OAuth 2.0 credential management with token caching.
- **`stalker_youtube_file.py`** — `StalkerYoutubeFile`: YouTube URL validation, metadata via `pytube`/`yt-dlp`, video download, transcript loading/splitting by chapters.

## Patterns & Conventions

- **Provider abstraction**: `ai.py` and `embedding.py` act as routers — they inspect the model name and delegate to the appropriate `api/*` module. New providers should follow this pattern.
- **Custom ORM**: Database access uses raw `psycopg2` queries, not SQLAlchemy. `StalkerWebDocumentDB` handles single-document CRUD; `WebsitesDBPostgreSQL` handles queries and vector search.
- **Data classes**: Models in `models/` are plain Python classes (not dataclasses or Pydantic). They use `__init__` with explicit attributes.
- **Environment-driven config**: All API keys and connection strings come from environment variables (loaded via `dotenv`).
- **Site-specific rules**: Website content cleanup uses regex rules defined in `data/site_rules.json` and `website/website_text_clean_regexp.py`, targeted at Polish news sites.

## Environment Variables

```
# Database
POSTGRESQL_HOST, POSTGRESQL_DATABASE, POSTGRESQL_USER, POSTGRESQL_PASSWORD, POSTGRESQL_PORT

# LLM / Embedding providers
OPENAI_API_KEY, OPENAI_ORGANIZATION
AWS_REGION
GCP_PROJECT_ID, GCP_LOCATION
CLOUDFERRO_SHERLOCK_KEY
ASSEMBLYAI

# App config
EMBEDDING_MODEL, ENV_DATA, DEBUG
```
