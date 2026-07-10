# Backend Library — CLAUDE.md

Core library for Project Lenie providing document processing, LLM abstraction, embedding generation, and database persistence.

## Directory Structure

```
library/
├── db/               # SQLAlchemy ORM layer
│   ├── models.py     # WebDocument, WebsiteEmbedding ORM models
│   └── engine.py     # Engine & session factories (get_session, get_scoped_session)
├── models/           # Data classes and enums (domain objects)
├── website/          # HTML download, parsing, paywall detection, content cleanup
├── api/              # External service integrations
│   ├── openai/       # OpenAI chat completions & embeddings
│   ├── aws/          # Bedrock, S3, Comprehend
│   ├── google/       # Vertex AI (Gemini)
│   ├── cloudferro/sherlock/  # Bielik Polish LLM & embeddings
│   └── asemblyai/    # Speech-to-text transcription (sole provider, ADR-011)
├── ai.py             # LLM provider abstraction (routes to api/*)
├── embedding.py      # Embedding provider abstraction (routes to api/*)
├── document_analysis_service.py  # Chunk analysis pipeline: split (chapter-aware for YouTube) → LLM rewrite/summarize → topics → synthesis → tagging → DB
├── chunk_llm_analysis.py         # LLM chunk primitives: speaker extraction, rewrite, summarize
├── chunk_review_routes.py        # Flask blueprint: chunk analysis REST API (runs, chunks, topic sections)
├── analysis_exports.py           # Analysis run file exports (MD/JSON/debug/HTML) to .claude/exports/
├── article_extractor.py     # LLM-based article boundary extraction (Bielik markers + regex drafts)
├── article_pipeline.py      # Shared pipeline: step_1 raw markdown (cache/S3) + LLM article extraction
├── article_cleaner.py       # Portal artifact cleanup of extracted article markdown ([imgN]/[linkN] markers)
├── article_tagging.py       # LLM thematic tagging & country extraction (TAGGING_MODEL config)
├── country_gazetteer.py     # Non-LLM country-name detection (stem-based gazetteer, ~190 countries)
├── ner_client.py            # HTTP client for the NER microservice (ner_service/, NER_SERVICE_URL config)
├── entity_service.py        # Persist NER entities per document (document_entities table, replace semantics)
├── stalker_web_documents_db_postgresql.py  # Query layer (ORM, list, search, similarity)
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

- **`db/models.py`** — `WebDocument` SQLAlchemy ORM model: ~30 attributes covering URL, text content (raw/English/markdown), metadata, processing state. Methods: `get_by_id()`, `get_by_url()`, `populate_neighbors()`. `WebsiteEmbedding` model for vector embeddings — optional `chunk_id` FK to `DocumentChunk`, set when the embedding was generated from a reviewed chunk (`generate_embeddings_from_run()`) rather than the fallback whole-document split.
- **Chunk analysis models** (backing `chunk_review_routes.py` / `document_analysis_service.py`):
  - `DocumentAnalysisRun` — one row per analysis pass over a document. `mode`: `transcript` (YouTube/movie STT — LLM rewrite + speaker labeling, chunk splitting by sentence) or `article` (webpage/link/text/book chapters — no rewrite step, markdown is already clean, so every chunk's `corrected_text` stays `None` by design; split by markdown headings). `status`: run review workflow, `created` → `in_review` → `reviewed` (`PATCH /analysis_run/<id>`). `scope`: human-readable analysed range (e.g. a book chapter title), `NULL` = whole document — a document can have several runs (e.g. one `split_only` run over a whole book plus one `article` run per chapter).
  - `DocumentChunk` — one row per chunk of a run. `type`: `TEMAT` (on-topic) / `REKLAMA` (sponsored) / `SZUM` (extraction junk — portal nav, cookie banners; auto-approved, never sent to an LLM for note-writing). `status`: `pending` → `approved` (or `needs_reanalysis`/`split_requested`/`split`/`skipped`). `obsidian_note_paths` — array of vault-relative paths, populated by the `/obsidian-note` skill when a note is written from the chunk.
  - `DocumentTopicSection` — LLM-synthesized grouping of a run's chunks by topic (`chunk_positions` array of `DocumentChunk.position`). Drives the book/chapter drill-down view in `/chunks/:id` for runs above `SECTION_VIEW_THRESHOLD` chunks. Coverage is partial by design — LLM synthesis doesn't always assign every chunk to a section.
  - `DocumentRemovedLine` — training data for `article_cleaner.py`: lines a human removed from a chunk/document during review (`source`: `manual` or `szum_chunk`). Survives run/chunk deletion (`run_id`/`chunk_id` FKs are `SET NULL`) so aggregate queries (e.g. most-removed lines per portal) keep working after runs are re-created.
- **`db/engine.py`** — SQLAlchemy engine and session factories: `get_session()`, `get_scoped_session()`.
- **`stalker_web_documents_db_postgresql.py`** — `WebsitesDBPostgreSQL`: query layer using SQLAlchemy session. Requires `session` parameter. Methods: `get_list()` (paginated/filtered), `get_similar()` (pgvector cosine search), `get_next_to_correct()`, `get_count()`, `embedding_add()`, `embedding_delete()`.

**Database tables:** `public.web_documents` (30 columns), `public.websites_embeddings` (vector similarity, optional `chunk_id` FK), `public.document_analysis_runs`, `public.document_chunks`, `public.document_topic_sections`, `public.document_removed_lines` — see [`database/CLAUDE.md`](../database/CLAUDE.md) for full column definitions.

### Models (`models/`)

| File | Class/Enum | Purpose |
|------|------------|---------|
| `stalker_document_status.py` | `StalkerDocumentStatus` | 15 processing states (URL_ADDED → EMBEDDING_EXIST) |
| `stalker_document_status_error.py` | `StalkerDocumentStatusError` | 14 error types |
| `stalker_document_type.py` | `StalkerDocumentType` | 8 document types (movie, youtube, link, webpage, text_message, text, email, social_media_post) |
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

Helper: `ai_model_need_translation_to_english(model)` — checks if model requires English input.

### Embedding Abstraction (`embedding.py`)

Entry point: `get_embedding(model, text) → EmbeddingResult`

Supported models:
- **AWS Bedrock**: amazon.titan-embed-text-v1, amazon.titan-embed-text-v2:0
- **OpenAI**: text-embedding-ada-002
- **CloudFerro**: BAAI/bge-multilingual-gemma2

### Text Processing

- **`article_pipeline.py`** — shared pipeline used by `imports/dynamodb_sync.py` and `imports/article_browser.py`: `ensure_raw_markdown(doc, cache_dir)` (returns `{id}_step_1_all.md` from cache, or downloads HTML via `document_prepare.prepare_markdown` and persists it), `extract_article(doc, cache_dir, skip_llm, arklabs_first)` (raw markdown + `article_extractor.process_article_with_llm_fallback`; returns `(raw_markdown, extracted_article)` tuple). Dependencies imported lazily (markitdown is an optional extra). Unit-tested (`tests/unit/test_article_pipeline.py`).
- **`article_cleaner.py`** — `clean_article_text(text, url)`: cleans extracted article markdown from portal artifacts (ads, video player controls, premium sections). Replaces images/links with `[imgN]`/`[linkN]` markers and returns them as separate lists. Generic rules + per-portal rules (onet, money, wp). Unit-tested (`tests/unit/test_article_cleaner.py`).
- **`article_tagging.py`** — `tag_article_with_llm()` (thematic categories from `THEMATIC_TAGS`), `extract_countries_with_llm()` (open-ended LLM extraction, `kraj-*` tags), `extract_countries_hybrid()` (preferred: `country_gazetteer.detect_countries()` prescreen — no LLM call if no candidates — then a single LLM call to confirm which candidates are clearly discussed, constrained to the candidate list so the LLM cannot invent a country). Model configurable via `TAGGING_MODEL` (default: Bielik). `COUNTRY_TAG_TRIGGERS` — thematic tags that trigger automatic country extraction. Called from two places: `article_browser.py`'s `[w]`/`[k]` actions, and `document_analysis_service.create_run()` (`_apply_tags()`, step 11b) using the run's synthesis text (or concatenated topic summaries as fallback) as input — merges into `doc.tags` rather than overwriting, so repeat/per-chapter runs accumulate tags instead of clobbering them.
- **`ner_client.py`** — HTTP client for the internal NER microservice (`ner_service/`, spaCy `pl_core_news_lg`): `extract_entities(text)` (raw mentions with lemmas; empty list on any failure — service unavailability must never fail a pipeline), `aggregate_entities()` (groups by `(entity_type, lemma)` with counts — Polish inflected variants of the same name collapse into one row), `warmup_async()` (fire-and-forget background probe that pre-loads the spaCy model, called at the start of `article_browser.py --review` and the youtube analysis scripts so the ~90s post-restart model load overlaps with other work). Service URL from `NER_SERVICE_URL` config (default `http://lenie-ner-service:8090`). See [`docs/ner-integration-plan.md`](../../docs/ner-integration-plan.md).
- **`entity_service.py`** — `refresh_document_entities(session, doc_id, text)` (NER → aggregate → replace the document's `document_entities` rows; empty extraction leaves existing rows untouched), `get_document_entities(session, doc_id)` (grouped by type, most-mentioned first). Called from `document_analysis_service.create_run()` (step 11c, whole-document runs only), `article_browser.py` (`[w]`/`[e]` actions) and the `/website_entities` endpoints in `server.py`.
- **`country_gazetteer.py`** — `detect_countries(text) -> list[CountryEntry]`: rule-based (no LLM) country-name detection via word-stem regex matching on diacritic-stripped text (`unidecode`), covering ~190 UN member/observer states + Taiwan/Kosovo. A candidate generator, not a topic classifier — deliberately over-matches (adjectives, demonyms, passing mentions); callers filter further (see `extract_countries_hybrid()`). Capitals are not matched (ambiguity: e.g. Sofia is also a first name).
- **`text_functions.py`** — `split_text_for_embedding()`, regex-based text removal (`remove_last_occurrence_and_after`, `remove_before_regex`, `remove_after_regex`), SHA256 hashing.
- **`lenie_markdown.py`** — `md_split_for_emb()` (recursive hierarchical splitting: H1→H2→H3→bold→paragraphs→sentences), link/image extraction, markdown cleanup.
- **`document_markdown.py`** — `DocumentMarkDown` class: converts inline images and links to numbered references.
- **`text_transcript.py`** — Chapter/timestamp parsing, transcript splitting by chapters (for YouTube).

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
| `aws/text_detect_language_aws.py` | `detect_text_language_aws()` (Comprehend) | AWS credentials |
| `aws/credentionals.py` | `validate_credentials()` (STS) | AWS credentials |
| `google/google_vertexai.py` | `connect_to_google_llm_with_role()` | `GCP_PROJECT_ID`, `GCP_LOCATION` |
| `cloudferro/sherlock/sherlock.py` | `sherlock_get_completion()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `cloudferro/sherlock/sherlock_embedding.py` | `sherlock_create_embedding()`, `sherlock_create_embeddings()` | `CLOUDFERRO_SHERLOCK_KEY` |
| `asemblyai/asemblyai_transcript.py` | `transcript_assemblyai()` | `ASSEMBLYAI` |

### Other Modules

- **`transcript.py`** — Transcription via AssemblyAI (sole provider, ADR-011) + `transcript_price()` cost calculator + `get_assemblyai_price_per_minute()` per-model pricing.
- **`google_auth.py`** — Google OAuth 2.0 credential management with token caching.
- **`stalker_youtube_file.py`** — `StalkerYoutubeFile`: YouTube URL validation, metadata via `pytubefix`/`yt-dlp`, video download, transcript loading/splitting by chapters.

## Patterns & Conventions

- **Provider abstraction**: `ai.py` and `embedding.py` act as routers — they inspect the model name and delegate to the appropriate `api/*` module. New providers should follow this pattern.
- **SQLAlchemy ORM**: Database access uses SQLAlchemy ORM (`db/models.py`, `db/engine.py`). `WebDocument` model handles single-document CRUD; `WebsitesDBPostgreSQL` handles queries and vector search. Connection supports optional SSL via `POSTGRESQL_SSLMODE` env var (required for AWS RDS).
- **Data classes**: Models in `models/` are plain Python classes (not dataclasses or Pydantic). They use `__init__` with explicit attributes.
- **Environment-driven config**: All API keys and connection strings come from environment variables (loaded via `dotenv`).
- **Site-specific rules**: Website content cleanup uses regex rules defined in `data/site_rules.json` and `website/website_text_clean_regexp.py`, targeted at Polish news sites.

## Environment Variables

```
# Database
POSTGRESQL_HOST, POSTGRESQL_DATABASE, POSTGRESQL_USER, POSTGRESQL_PASSWORD, POSTGRESQL_PORT
POSTGRESQL_SSLMODE  # Optional: set to 'require' for RDS encrypted connections

# LLM / Embedding providers
OPENAI_API_KEY, OPENAI_ORGANIZATION
AWS_REGION
GCP_PROJECT_ID, GCP_LOCATION
CLOUDFERRO_SHERLOCK_KEY
ASSEMBLYAI

# App config
EMBEDDING_MODEL, TAGGING_MODEL, ENV_DATA, DEBUG
```
