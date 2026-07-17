# Backend Database — CLAUDE.md

PostgreSQL database schema for Project Lenie. Init scripts are executed automatically by the `postgres` Docker image on first container startup (when the data volume is empty).

## Directory Structure

```
database/
└── init/                                        # Docker entrypoint init scripts (run in alphabetical order)
    ├── 01-create-database.sql                    # Creates the "lenie-ai" database
    ├── 02-create-extension.sql                   # Installs pgvector extension
    ├── 03-create-table.sql                       # Creates web_documents table + indexes
    ├── 04-create-table.sql                       # Creates websites_embeddings table + indexes
    ├── 05-migrate-ready-for-translation.sql
    ├── 06-drop-english-columns.sql
    ├── 07-add-transcript-needed.sql
    ├── 08-fix-language-typo.sql                  # websites_embeddings.langauge → language
    ├── 09-create-lookup-tables.sql
    ├── 10-add-foreign-keys.sql
    ├── 11-create-transcription-log.sql
    ├── 12-add-video-description.sql
    ├── 13-create-analysis-tables.sql             # document_analysis_runs, document_chunks, document_topic_sections
    ├── 14-add-speakers-to-analysis-runs.sql
    ├── 15-add-analysis-run-workflow-columns.sql  # mode, status, scope on document_analysis_runs
    ├── 16-add-chunk-id-to-embeddings.sql         # websites_embeddings.chunk_id FK
    ├── 17-add-text-extracted-to-web-documents.sql
    ├── 18-create-document-removed-lines.sql
    ├── 19-create-reader-user-tables.sql          # users, user_reading_progress, user_document_notes
    ├── 20-create-api-keys.sql                    # api_keys
    ├── 21-create-document-entities.sql           # document_entities (raw NER persons/places)
    ├── 22-create-geocode-cache.sql               # geocode_cache + document_entities.geocode_id
    ├── 23-create-persons-tables.sql              # persons, person_aliases, document_persons
    ├── 24-create-ner-exclusions.sql              # ner_exclusions (NER false-positive suppressions)
    ├── 25-create-infra-geometries.sql            # infra_geometries (Overpass pipeline-route cache)
    ├── 26-create-document-references.sql         # document_references (book footnotes extracted from text_md)
    ├── 27-create-document-events.sql             # document_events (LLM-extracted document timeline)
    └── 28-create-sources.sql                     # sources lookup + fk_source on web_documents.source
```

## How Init Scripts Are Used

The scripts in `init/` are copied into `/docker-entrypoint-initdb.d` inside the PostgreSQL container (see `infra/docker/Postgresql/Dockerfile`). PostgreSQL's official Docker image executes all `.sql` files in that directory **once** — only when the data directory is empty (first run). Re-running the container with an existing volume will **not** re-execute the scripts.

To re-initialize the database, delete the named volume (`lenie-ai-db-data-3`) and restart the container.

## Database: `lenie-ai`

PostgreSQL 18 with the **pgvector** extension for vector similarity search.

### Table: `public.web_documents`

Main document storage. Each row represents a collected web resource (article, video, transcript, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `url` | `text NOT NULL` | Source URL |
| `document_type` | `varchar(50) NOT NULL` | One of: movie, youtube, link, webpage, text_message, text |
| `document_state` | `varchar(50) NOT NULL` | Processing state (default: `URL_ADDED`) |
| `document_state_error` | `text` | Error details when `document_state = ERROR` |
| `title` | `text` | Original title |
| `title_english` | `text` | English translation of title |
| `text` | `text` | Cleaned text content |
| `text_raw` | `text` | Raw extracted text before cleanup |
| `text_english` | `text` | English translation of text |
| `text_md` | `text` | Markdown version of text |
| `text_extracted` | `text` | Raw LLM article extraction output (pre `clean_article_text()`), diagnostic only — not exposed via API |
| `summary` | `text` | AI-generated summary |
| `summary_english` | `text` | English translation of summary |
| `language` | `varchar(10)` | Detected language code |
| `tags` | `text` | Comma-separated tags |
| `source` | `text` | Discovery source (how the user found the document) — FK → `sources.name` (`fk_source`, `ON UPDATE CASCADE`); unknown values are auto-created by the ORM `before_flush` hook |
| `author` | `text` | Document author |
| `note` | `text` | User notes |
| `paywall` | `boolean` | Whether content is behind a paywall (default: false) |
| `date_from` | `date` | Publication date |
| `created_at` | `timestamp` | Row creation timestamp |
| `document_length` | `integer` | Text length in characters |
| `chapter_list` | `text` | Chapter/section list (for videos/transcripts) |
| `original_id` | `text` | External identifier (e.g. YouTube video ID) |
| `transcript_job_id` | `text` | Transcription service job ID |
| `ai_summary_needed` | `boolean` | Flag: needs AI summary (default: false) |
| `uuid` | `varchar(100) NOT NULL DEFAULT gen_random_uuid()` | Global document identifier (ADR-015), UNIQUE |
| `project` | `varchar(100)` | Project/collection grouping |

**Indexes:** `document_type`, `document_state`, `created_at`, `url`, `project`, `source`, `date_from`, `paywall`, `ai_summary_needed`.

### Table: `public.websites_embeddings`

Vector embeddings for document chunks used in similarity search.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `website_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `language` | `varchar(10)` | Language of the embedded text |
| `text` | `text` | Translated/processed text that was embedded |
| `text_original` | `text` | Original text before translation |
| `embedding` | `vector` | Vector embedding (dimensionless — supports multiple models with different dimensions) |
| `model` | `varchar(100) NOT NULL` | Embedding model used |
| `chunk_id` | `integer` | FK → `document_chunks.id` (`ON DELETE SET NULL`), NULL for embeddings generated directly from the document (fallback path when no reviewed chunk run exists) |
| `created_at` | `timestamp` | Row creation timestamp |

**Indexes:** `website_id`, `model`, HNSW partial indexes on `embedding` per model (cosine similarity). Each embedding model has its own partial index to support different vector dimensions.

### Table: `public.document_analysis_runs`

One row per chunk-analysis pass over a document (`library/document_analysis_service.py`, `POST /document/<id>/analyze_chunks`). A document can have several runs — e.g. a book typically has one `split_only` run over the whole text plus one `article` run per chapter.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `model` | `varchar(100) NOT NULL` | LLM model used for the analysis |
| `chunk_size` | `integer NOT NULL DEFAULT 5000` | Target chunk size in characters |
| `synthesis` | `text` | LLM-generated overview of the whole run (shown as a collapsible "Synteza" panel in `/chunks/:id`) |
| `speakers` | `jsonb NOT NULL DEFAULT '[]'` | Detected speaker list, `mode=transcript` only |
| `mode` | `varchar(20) NOT NULL DEFAULT 'transcript'` | `transcript` (YouTube/movie STT — LLM rewrite + speaker labeling, split by sentence) or `article` (webpage/link/text/book chapters — no rewrite, source markdown already clean so every chunk's `corrected_text` is `NULL` by design; split by markdown headings) |
| `status` | `varchar(20) NOT NULL DEFAULT 'created'` | Run review workflow: `created` → `in_review` → `reviewed`; `superseded` = abandoned run replaced by a newer run of the same `document_id`+`scope` (set by `document_analysis_service.supersede_unfinished_runs`) |
| `scope` | `varchar(200)` | Human-readable analysed range (e.g. a book chapter title); `NULL` = whole document |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.document_chunks`

One row per chunk produced by a run.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `run_id` | `integer NOT NULL` | FK → `document_analysis_runs.id` (CASCADE delete) |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `position` | `smallint NOT NULL` | 1-based order within the run |
| `type` | `varchar(20) NOT NULL` | `TEMAT` (on-topic) / `REKLAMA` (sponsored) / `SZUM` (extraction junk — portal nav, cookie banners; auto-approved, excluded from note-writing) |
| `topic` | `varchar(500)` | Short topic label |
| `original_text` | `text NOT NULL` | Source text of the chunk |
| `corrected_text` | `text` | LLM-rewritten text — populated only for `mode=transcript`; always `NULL` for `mode=article` (no rewrite step, not a data quality issue) |
| `summary` | `text` | 2-3 sentence LLM summary |
| `seg_start` / `seg_end` | `integer` | Segment index range within the transcript (`mode=transcript` only) |
| `rewrite_ratio` | `smallint` | STT rewrite change ratio (`mode=transcript` only) |
| `status` | `varchar(30) NOT NULL DEFAULT 'pending'` | `pending` / `approved` / `needs_reanalysis` / `split_requested` / `split` / `skipped` |
| `split_at_seg` | `integer` | Segment offset for a pending manual split |
| `split_first_type` / `split_second_type` | `varchar(20)` | Resulting types after executing a split |
| `created_at` / `updated_at` | `timestamp` | Row timestamps |
| `obsidian_note_paths` | `text[] NOT NULL DEFAULT '{}'` | Vault-relative paths of notes written from this chunk (populated by the `/obsidian-note` skill) |

### Table: `public.document_topic_sections`

LLM-synthesized grouping of a run's chunks by topic — drives the book/chapter drill-down accordion in `/chunks/:id` (used once a run exceeds the UI's `SECTION_VIEW_THRESHOLD`). Coverage of a run's chunks is partial by design — LLM synthesis doesn't always assign every chunk to a section.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `run_id` | `integer NOT NULL` | FK → `document_analysis_runs.id` (CASCADE delete) |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `position` | `smallint NOT NULL` | Order within the run |
| `type` | `varchar(20) NOT NULL` | `TEMAT` / `REKLAMA` / `SZUM` |
| `title` | `varchar(500)` | Section title (editable via `PATCH /topic_section/<id>`) |
| `summary` | `text` | LLM summary of the section |
| `chunk_positions` | `integer[] NOT NULL` | Positions of the `document_chunks` rows belonging to this section |
| `created_at` / `updated_at` | `timestamp` | Row timestamps |

### Table: `public.document_removed_lines`

Training data for `article_cleaner.py`: lines a human manually removed from a chunk or document during review. Survives run/chunk deletion (`run_id`/`chunk_id` are `SET NULL`, not `CASCADE`) so aggregate queries (e.g. most-removed lines per portal, joined on `web_documents.url`) keep working after runs are re-created.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `run_id` | `integer` | FK → `document_analysis_runs.id` (`SET NULL` on delete) |
| `chunk_id` | `integer` | FK → `document_chunks.id` (`SET NULL` on delete) |
| `source` | `varchar(20) NOT NULL` | `manual` (removed in chunk-review UI) or `szum_chunk` (whole SZUM/REKLAMA chunk dropped by "Wyczyść dokument") |
| `line_text` | `text NOT NULL` | The removed line/block |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.document_entities`

Raw NER entities (person/place mentions) per document — MVP of [`docs/ner-integration-plan.md`](../../docs/ner-integration-plan.md). Populated by `library/entity_service.py` from the NER microservice (`ner_service/`, via `library/ner_client.py`). Rows are derived data: a refresh **replaces** the document's rows (unlike `tags`, which accumulates). Deliberately no disambiguation columns — persons get dedicated tables in a later stage ([`docs/person-ner-plan.md`](../../docs/person-ner-plan.md)), places get verification + tags ([`docs/geo-place-ner-plan.md`](../../docs/geo-place-ner-plan.md)).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `entity_type` | `varchar(20) NOT NULL` | `persName` / `geogName` / `placeName` (spaCy `pl_core_news_lg` labels) |
| `entity_text` | `text NOT NULL` | Base form of the mention (lemma when available — inflected variants aggregate into one row) |
| `mention_count` | `integer NOT NULL DEFAULT 1` | Number of mentions aggregated into this row |
| `variants` | `text[] NOT NULL DEFAULT '{}'` | Distinct surface forms as seen in the text ("Kijów", "Kijowa") — matched by the chapter-scoped entity filter (`entity_service.filter_entities_to_text`) regardless of inflection; empty = row predates the column (refilled on next refresh) |
| `geocode_id` | `integer` | FK → `geocode_cache.id` (`SET NULL` on delete) — stage-3 geocoder verdict for place entities; `NULL` = not checked yet |
| `created_at` | `timestamp` | Row creation timestamp |

**Constraints/indexes:** UNIQUE `(document_id, entity_type, entity_text)`; indexes on `document_id`, `entity_type` and `geocode_id`.

### Table: `public.document_references`

Footnotes/references extracted out of a book's `text_md` (`library/references.py`, CLI: `imports/extract_references.py`). OCR-ed books carry footnote lines inline where they fell on the scanned page — they interrupt reading and pollute NER/embeddings (footnote URLs used to become person entities). Replace semantics per document; the reader renders a per-chapter "Przypisy" section from these rows (`GET /document/<id>/chapter/<pos>` → `references`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `chapter_position` | `integer` | 1-based, matches `detect_chapters()`; `NULL` = unassigned |
| `marker` | `varchar(10) NOT NULL` | Footnote number as printed ("18" — superscript markers normalized to digits) |
| `ref_text` | `text NOT NULL` | Full footnote text |
| `url` | `text` | First URL found in the footnote, normalized to `https://` |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.document_events`

Timeline events discussed in a document, extracted chapter by chapter by `library/timeline_events.py` and managed
with replace semantics by `imports/extract_events.py`. LLM output is accepted only when its anchor quote occurs in the
source fragment; Polish exact and coarse dates are normalized for chronological sorting.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK to `web_documents.id` (CASCADE delete) |
| `chapter_position` | `integer` | 1-based position from `detect_chapters()`; `NULL` for chapterless documents |
| `event_date` | `date` | Exact date or beginning of a normalized range |
| `event_date_end` | `date` | End of a normalized month/year/decade/century range |
| `date_precision` | `varchar(10) NOT NULL` | `day`, `month`, `year`, `decade`, `century`, `era`, or `unknown` |
| `date_text` | `text NOT NULL` | Original date expression returned from the source text |
| `sort_year` | `integer` | Sort key, including approximate years for coarse expressions |
| `description` | `text NOT NULL` | One-sentence factual event description |
| `anchor_quote` | `text` | Short exact quote grounding the event in the source fragment |
| `created_at` | `timestamp` | Row creation timestamp |

**Index:** `(document_id, sort_year)`.

### Table: `public.document_time_periods`

Historical periods a document's content is about (e.g. "starożytny Egipt", "zimna wojna", "współczesność"),
classified by `library/time_periods.py` — per reader chapter for books, one whole-document row set for chapterless
documents — and managed with replace semantics by `imports/extract_time_periods.py`. Year ranges enable future
search filtering by period ("texts about the 1980s" = range overlap); BCE years are stored as negative integers.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK to `web_documents.id` (CASCADE delete) |
| `chapter_position` | `integer` | 1-based position from `detect_chapters()`; `NULL` for chapterless documents |
| `position` | `integer NOT NULL` | Order within the chapter, `0` = main period |
| `period_label` | `varchar(100) NOT NULL` | Short Polish period name returned by the LLM |
| `period_start_year` | `integer` | Approximate first year; negative = BCE |
| `period_end_year` | `integer` | Approximate last year; negative = BCE |
| `confidence` | `varchar(10) NOT NULL` | `high`, `medium`, or `low` |
| `evidence` | `text` | One LLM sentence: what in the text grounds the classification |
| `created_at` | `timestamp` | Row creation timestamp |

**Indexes:** `(document_id, chapter_position)`, `(period_start_year, period_end_year)`.

### Table: `public.document_tones`

Emotional tone and language register of a chapter, classified by `library/tones.py` — per reader chapter for
books, one whole-document row for chapterless documents — and managed with replace semantics by
`imports/extract_tones.py`. Emotion ("radosny") and register ("dziecinny") are deliberately separate axes:
mixing them into one label made the LLM drop the register. All labels come from closed Polish lists validated
in Python (LLM output with stripped diacritics is canonicalized, e.g. "srednia" → "średnia"); one row per chapter.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `document_id` | `integer NOT NULL` | FK to `web_documents.id` (CASCADE delete) |
| `chapter_position` | `integer` | 1-based position from `detect_chapters()`; `NULL` for chapterless documents |
| `emotion` | `varchar(20) NOT NULL` | Main emotion: `neutralny`, `radosny`, `smutny`, `gniewny`, `alarmistyczny`, `podniosły`, `refleksyjny` |
| `secondary_emotions` | `varchar(100)` | Up to 2 extra emotions from the same list, comma-separated |
| `sentiment` | `varchar(10) NOT NULL` | `pozytywne`, `negatywne`, `neutralne`, or `mieszane` |
| `intensity` | `varchar(10) NOT NULL` | `niska`, `średnia`, or `wysoka` |
| `registers` | `varchar(100)` | Up to 2 language registers (`formalny`, `potoczny`, `dziecinny`, `wulgarny`, `obraźliwy`, `ironiczny`), comma-separated |
| `evidence` | `text` | One LLM sentence grounding the classification |
| `created_at` | `timestamp` | Row creation timestamp |

**Index:** `(document_id, chapter_position)`.

### Table: `public.infra_geometries`

Overpass API lookup cache for linear infrastructure (`library/overpass_client.py`) — same philosophy as `geocode_cache`: one live call ever per distinct query string, clean misses cached as `resolved=false` (transport failures are NOT cached). Populated during `POST /website_entities` for place entities the geocoder checked but rejected ("Baltic Pipe" has no point hit but has an OSM route).

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `query` | `text NOT NULL UNIQUE` | Entity name as queried |
| `resolved` | `boolean NOT NULL` | Overpass matched a named pipeline |
| `kind` | `varchar(30)` | `pipeline` (future: power_line, …) |
| `substance` | `varchar(30)` | OSM `substance` tag: `gas` / `oil` / … |
| `name` | `text` | OSM name of the matched feature |
| `wikidata_qid` | `varchar(20)` | OSM `wikidata` tag when present |
| `geojson` | `jsonb` | Simplified GeoJSON MultiLineString (≤200 points per line) rendered on the reader map |
| `provider` | `varchar(20) DEFAULT 'overpass'` | Data source |
| `created_at` | `timestamp` | Row creation timestamp |

### Table: `public.geocode_cache`

Geocoder response cache (NER stage 3, `library/place_verification.py` + `library/locationiq_client.py`). One row per distinct query string ever sent to LocationIQ (free tier: 5000 req/day) — negative results are cached too, so a name is never geocoded twice.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `query` | `text NOT NULL UNIQUE` | The place name as queried (entity base form) |
| `resolved` | `boolean NOT NULL` | Geocoder returned a hit AND it passed the match-quality check (`is_plausible_match()` — rare Polish exonyms fuzzy-match to wrong places, so a bare hit is not proof) |
| `display_name` | `text` | Hierarchical name from the geocoder (e.g. "Kyiv, Ukraine") |
| `lat` / `lon` | `numeric(9,6)` | Coordinates (map markers in `/read/:id`) |
| `osm_class` / `osm_type` | `varchar(50)` | OSM classification of the hit |
| `importance` | `real` | Geocoder relevance score |
| `raw` | `jsonb` | First hit as returned by the provider (diagnostics/tuning) |
| `provider` | `varchar(20) NOT NULL DEFAULT 'locationiq'` | Geocoding provider |
| `created_at` | `timestamp` | Row creation timestamp |

### Tables: `public.persons`, `public.person_aliases`, `public.document_persons`

Person entity model (NER stage 4, `library/person_registry.py` + `library/wikidata_client.py` — see [`docs/person-ner-plan.md`](../../docs/person-ner-plan.md)). A relational model instead of tags because two people can share a name and one person appears under many spelling variants.

- **`persons`** — one row per real person: `uuid` (unique), `canonical_name` (pg_trgm GIN index), `wikidata_qid` (unique, NULL for people without a Wikidata entry), `description` (occupation/known-for — disambiguation context), `created_at`.
- **`person_aliases`** — spelling variants seen in articles (inflection, initials): `person_id` FK (CASCADE), `alias` (pg_trgm GIN index), UNIQUE `(person_id, alias)`.
- **`document_persons`** — document↔person M:N + extraction metadata: `document_id`/`person_id` FKs (CASCADE), `raw_mention` (base form detected by NER), `confidence` (`wikidata_matched` — Wikidata human entity + LLM context match / `alias_matched` — existing alias or canonical name matched / `manual_review` — new or uncertain person, review queue / `manual_confirmed` — human approved), UNIQUE `(document_id, person_id)`.

### Table: `public.ner_exclusions`

NER false-positive suppression dictionary, applied in `library/entity_service.py` at entity-refresh time — a matched entity is dropped before it lands in `document_entities`, so it never reaches person resolution or place verification. Typical rules: "Taliban" detected as `persName` (an organization), STT artifacts like "Starling"/"starlinek" (the Starlink device). Managed via `GET/POST/DELETE /ner_exclusions`; rules are added from the editor's EntitiesPanel (🚫 button) and reviewed on `/persons-review`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `entity_text` | `text NOT NULL` | Matched case-insensitively against the aggregated entity base form |
| `entity_type` | `varchar(20) NOT NULL DEFAULT '*'` | `persName` / `geogName` / `placeName` / `*` (all types) |
| `scope` | `varchar(10) NOT NULL DEFAULT 'global'` | `global` (every document) or `author` (only documents whose `web_documents.author` matches) |
| `author` | `text` | Author the rule is limited to (required when `scope='author'`, CHECK constraint) |
| `note` | `text` | Optional human note (why excluded) |
| `created_at` | `timestamp` | Row creation timestamp |

**Indexes:** unique on `(LOWER(entity_text), entity_type, scope, COALESCE(LOWER(author), ''))`.

### Table: `public.sources`

Discovery-source lookup — how the user found a document (`own`, a newsletter, a friend); a recommendation channel, NOT the content author. `web_documents.source` references `name` (ADR-010) with `ON UPDATE CASCADE`, so renaming a source rewrites all documents atomically; deletes are restricted (API allows DELETE only when no documents use the source — deactivate instead). Managed via `GET/POST /sources`, `PATCH/DELETE /sources/<id>` and the React `/sources` page; the Chrome extension loads the active list and can add new sources. Unknown values arriving through any ORM write path (imports, feeds, DynamoDB sync) are auto-created by the `before_flush` hook in `library/db/models.py`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `name` | `varchar UNIQUE NOT NULL` | Source name (FK target of `web_documents.source`) |
| `description` | `text` | Optional human note (what the source is) |
| `url` | `text` | Optional source website |
| `is_active` | `boolean NOT NULL DEFAULT TRUE` | Inactive sources stay valid on existing documents but disappear from pickers (`GET /sources?active=1`) |

Reader identity and API key tables (`users`, `user_reading_progress`, `user_document_notes`, `api_keys` — init scripts 19-20) are out of scope for this section; see `library/reader_routes.py`, `library/auth.py` and `library/db/models.py` for their definitions.

## Document Processing States

The `document_state` column tracks a document through its processing pipeline (defined in `backend/library/models/stalker_document_status.py`):

```
URL_ADDED → DOCUMENT_INTO_DATABASE → NEED_CLEAN_TEXT → NEED_CLEAN_MD → TEXT_TO_MD_DONE
    → MD_SIMPLIFIED → READY_FOR_TRANSLATION → READY_FOR_EMBEDDING → EMBEDDING_EXIST
```

Special states:
- `NEED_TRANSCRIPTION` / `TRANSCRIPTION_IN_PROGRESS` / `TRANSCRIPTION_DONE` — for audio/video content
- `NEED_MANUAL_REVIEW` — automatic text cleanup failed; needs manual removal of ads, comments, and spam
- `ERROR` / `TEMPORARY_ERROR` — processing failed (details in `document_state_error`)

**Invariant — `document_state_error` must be reset on every successful transition.** The field only means something while the document is in an error state (`ERROR`/`TEMPORARY_ERROR`); once a retry succeeds and `document_state` moves on, any code that sets `document_state_error` on failure MUST also clear it (`StalkerDocumentStatusError.NONE.name`) on the corresponding success path in the same function. Otherwise the error becomes sticky forever — a later retry that succeeds leaves the stale value in place because nothing overwrites it. `WebDocument.validate()` in `db/models.py` follows this correctly (resets to `NONE` at the top before re-evaluating). `library/youtube_processing.py` did **not** follow it for `CAPTIONS_FETCH_ERROR`/transcription errors until this was fixed (2026-07-04) — a retry that fetched captions successfully left `CAPTIONS_FETCH_ERROR` from an earlier failed attempt in place indefinitely. When adding a new failure/retry branch to any pipeline step, always pair the error-setting line with a reset on the success path.

## Document Types

The `document_type` column (defined in `backend/library/models/stalker_document_type.py`):
- `movie` — video content
- `youtube` — YouTube video
- `link` — bookmark/reference link
- `webpage` — full webpage content
- `text_message` — plain text input
- `text` — generic text document

## Docker Setup

**Image:** Custom image built from `postgres:18-bookworm` with `postgresql-18-pgvector` package installed (see `infra/docker/Postgresql/Dockerfile`).

**Compose service** (`infra/docker/compose.yaml`):
- Image: `lenie-ai-db:latest` (must be built locally first)
- Port mapping: `5433:5432` (host:container)
- Volume: `lenie-ai-db-data-3` for persistent storage
- Default password: `postgres` (development only)

Build the database image:
```bash
docker build -f infra/docker/Postgresql/Dockerfile -t lenie-ai-db:latest .
```

## Application Access

The backend accesses the database via SQLAlchemy ORM. Key files:
- `backend/library/db/models.py` — ORM models (`WebDocument`, `WebsiteEmbedding`, lookup table models)
- `backend/library/db/engine.py` — engine & session factories (`get_session`, `get_scoped_session`)
- `backend/library/stalker_web_documents_db_postgresql.py` — query layer (list, search, vector similarity)

Connection configured via environment variables: `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`.

## Known Issues

- The `langauge` typo in `websites_embeddings` was fixed — column renamed to `language` (migration: `08-fix-language-typo.sql`).
- The `embedding` column uses dimensionless `vector` type to support multiple embedding models with different dimensions (e.g. OpenAI ada-002: 1536, Titan v2: 1024, BAAI/bge-multilingual-gemma2: 3584). Each model has a dedicated HNSW partial index. When adding a new embedding model, create a new partial index in `04-create-table.sql`.
