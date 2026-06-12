# Data Models — Backend

> Generated: 2026-02-13 | Part: backend | Database: PostgreSQL 18 + pgvector

## Database Schema

### Table: web_documents (29 columns)

Primary document storage table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | serial | PK | Auto-increment identifier |
| `url` | text | NOT NULL | Source URL |
| `document_type` | varchar(50) | NOT NULL | movie, youtube, link, webpage, text_message, text, email, social_media_post |
| `document_state` | varchar(50) | NOT NULL, DEFAULT 'URL_ADDED' | Processing state (15 states) |
| `document_state_error` | text | — | Error details when state=ERROR |
| `title` | text | — | Original title |
| `title_english` | text | — | Translated title |
| `text` | text | — | Cleaned extracted text |
| `text_raw` | text | — | Raw text before cleanup |
| `text_english` | text | — | Translated text |
| `text_md` | text | — | Markdown version |
| `summary` | text | — | AI-generated summary |
| `summary_english` | text | — | Translated summary |
| `language` | varchar(10) | — | Detected language code |
| `tags` | text | — | Comma-separated tags |
| `source` | text | — | How the user discovered this content (e.g. "own", "unknow.news", "friend") — used to evaluate recommendation quality |
| `author` | text | — | Content creator (YouTube channel name, article author) — metadata about who made the content |
| `note` | text | — | User notes |
| `paywall` | boolean | DEFAULT false | Paywall indicator |
| `date_from` | date | — | Publication date |
| `created_at` | timestamp | DEFAULT CURRENT_TIMESTAMP | Row creation time |
| `document_length` | integer | — | Text length in characters |
| `chapter_list` | text | — | Chapter/section list (JSON format for videos) |
| `video_description` | text | — | Full YouTube video description (used for auto-parsing chapter timestamps) |
| `original_id` | text | — | External ID (YouTube video ID, etc.) |
| `transcript_job_id` | text | — | Transcription service job ID |
| `ai_summary_needed` | boolean | DEFAULT false | Flag for AI summary generation |
| `uuid` | varchar(100) | NOT NULL DEFAULT gen_random_uuid(), UNIQUE | Global document identifier (ADR-015) |
| `project` | varchar(100) | — | Project/collection grouping |

**Indexes**: document_type, document_state, created_at, url, project, source, date_from, paywall, ai_summary_needed

### Table: websites_embeddings (8 columns)

Vector embeddings for similarity search.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | serial | PK | Auto-increment identifier |
| `website_id` | integer | FK → web_documents.id (CASCADE) | Document reference |
| `langauge` | varchar(10) | — | Language code (intentional typo kept for compatibility) |
| `text` | text | — | Processed text that was embedded |
| `text_original` | text | — | Original text before translation |
| `embedding` | vector | — | Dimensionless vector (supports multiple models: ada-002=1536, Titan v2=1024, bge-m3=1024) |
| `model` | varchar(100) | NOT NULL | Embedding model identifier |
| `created_at` | timestamp | DEFAULT CURRENT_TIMESTAMP | Timestamp |

**Indexes**: website_id, model, IVFFlat index on embedding (cosine similarity)

## Document Processing States

15 states in `StalkerDocumentStatus` enum (`library/models/stalker_document_status.py`):

| ID | State | Description |
|----|-------|-------------|
| 1 | ERROR | Processing error occurred |
| 2 | URL_ADDED | Initial state after URL submission |
| 3 | NEED_TRANSCRIPTION | Audio/video needs transcription |
| 4 | TRANSCRIPTION_IN_PROGRESS | Transcription running |
| 5 | TRANSCRIPTION_DONE | Transcription completed |
| 6 | TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS | Transcription split by chapters |
| 7 | NEED_MANUAL_REVIEW | Automatic text cleanup failed — needs manual removal of ads/comments/spam |
| 8 | READY_FOR_TRANSLATION | Text ready for translation |
| 9 | READY_FOR_EMBEDDING | Content ready for embedding generation |
| 10 | EMBEDDING_EXIST | Final state — embeddings generated |
| 11 | DOCUMENT_INTO_DATABASE | Document stored in database |
| 12 | NEED_CLEAN_TEXT | Text needs cleanup |
| 13 | NEED_CLEAN_MD | Markdown needs cleanup |
| 14 | TEXT_TO_MD_DONE | Text to markdown conversion done |
| 15 | MD_SIMPLIFIED | Markdown simplified |

**Typical flow**: URL_ADDED → DOCUMENT_INTO_DATABASE → NEED_MANUAL_REVIEW → READY_FOR_TRANSLATION → READY_FOR_EMBEDDING → EMBEDDING_EXIST

## Document Status Errors

14 error states in `StalkerDocumentStatusError` enum:

| ID | Error | Description |
|----|-------|-------------|
| 1 | NONE | No error |
| 2 | ERROR_DOWNLOAD | Download failed |
| 3 | LINK_SUMMARY_MISSING | Summary missing for link |
| 4 | TITLE_MISSING | Title not found |
| 5 | TITLE_TRANSLATION_ERROR | Title translation failed |
| 6 | TEXT_MISSING | No text content |
| 7 | TEXT_TRANSLATION_ERROR | Text translation failed |
| 8 | SUMMARY_TRANSLATION_ERROR | Summary translation failed |
| 9 | NO_URL_ERROR | URL missing |
| 10 | EMBEDDING_ERROR | Embedding generation failed |
| 11 | MISSING_TRANSLATION | Translation missing |
| 12 | TRANSLATION_ERROR | Translation failed |
| 13 | REGEX_ERROR | Regex processing error |
| 14 | TEXT_TO_MD_ERROR | Markdown conversion error |

## Document Types

6 types in `StalkerDocumentType` enum:

| ID | Type | Description |
|----|------|-------------|
| 1 | movie | Movie/audio transcript |
| 2 | youtube | YouTube video transcript |
| 3 | link | Bookmark/link (metadata only) |
| 4 | webpage | Full webpage content |
| 5 | text_message | Text message/note |
| 6 | text | Plain text document |

## Domain Models (Python)

### StalkerWebDocument (base class)

Core document model with ~30 attributes matching `web_documents` table. Key methods:
- `set_document_type(str)` — set type from string
- `set_document_state(str)` — set state from string
- `analyze()` — run content analysis
- `validate()` — validate document data

### StalkerWebDocumentDB (extends StalkerWebDocument)

Adds database persistence via raw psycopg2:
- `save() → int | None` — insert or update, returns document ID
- `delete()` — remove from database
- `embedding_add_simple(vector, model)` — add embedding
- `embedding_delete(model)` — remove embeddings
- `dict() → dict` — serialize to JSON

### WebsitesDBPostgreSQL (query layer)

Static query methods:
- `get_list(limit, offset, document_type, document_state, ...) → list[dict]`
- `get_similar(embedding_vector, model, limit) → list[dict]` — pgvector cosine search
- `get_next_to_correct(website_id, document_type, document_state) → [int, str]`
- `get_count(document_type, document_state) → int`

### Supporting Models

- **AiResponse** — LLM response: query, model, response_text, token counts, temperature
- **EmbeddingResult** — embedding result: text, embedding (dimensions vary by model), status, model_id
- **WebPageParseResult** — parsed webpage: url, text_raw, text, title, summary, language

## AWS DynamoDB (Serverless)

Used in AWS serverless deployment for always-available metadata storage:

- **Partition Key (pk)**: 'DOCUMENT' (String)
- **Sort Key (sk)**: `{timestamp}#{uuid}` (String)
- **GSI**: DateIndex on `created_date`
- **Billing**: PAY_PER_REQUEST
- **PITR**: Enabled for prod, disabled for dev/qa

## Data Access Pattern

Raw `psycopg2` queries (no ORM). Connection via environment variables:
- `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`
