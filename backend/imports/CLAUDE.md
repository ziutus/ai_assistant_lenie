# Backend Imports — CLAUDE.md

Standalone CLI scripts that add or manage documents in the Lenie database, bypassing the REST API. Covers single-item ad-hoc tools, bulk import pipelines, and a few standalone helper tools that do not touch the database at all.

## Directory Structure

```
imports/
├── book_import_pdf_twierdza_linux.py  # Import "Twierdza Linux" PDF into a Document — one script per book, see below
├── book_extract_images.py    # Backfill: extract images for a book PDF already imported (no text_md rewrite)
├── backfill_obsidian_content_groups.py  # One-off: enqueue Bielik content-group (Tematy) classification for already-imported obsidian_note documents
├── check_pdf_text_layer.py   # Check if a PDF has a usable text layer or needs OCR (no DB)
├── control_questions.py      # Filter control questions from an Obsidian markdown file by tags (no DB)
├── import_control_questions.py # Sync the Obsidian control-question bank into the control_questions DB table
├── select_control_questions.py # Cheap-LLM (Bielik) router: which control questions a document actually answers
├── dynamodb_sync.py          # Sync documents from DynamoDB + S3 to local PostgreSQL
├── extract_references.py     # Extract book footnotes from text_md into document_references
├── extract_time_periods.py   # Classify the historical period a document is about (per chapter for books)
├── extract_tones.py          # Classify emotional tone + language register per chapter
├── fix_duplicate_analysis_runs.py # One-off: supersede abandoned duplicate analysis runs (same document+scope, never reviewed)
├── fix_place_tags.py         # One-off: merge duplicate miejsce-* tags (inflected NER variants) via geocode_cache
├── freedom_house_import.py   # Query Freedom House country ratings via OWID API (no DB)
├── organization_descriptions_backfill.py  # One-off: LLM-generated short descriptions for organizations missing one (reader tooltip)
├── migrate_data_to_cache.py  # One-time migration: data/ files → CACHE_DIR convention
├── youtube_add.py            # Ad-hoc: process a single YouTube video (optionally + LLM analysis)
├── youtube_backfill_author.py # One-off: fetch channel name for existing videos missing 'byline'
└── youtube_batch_analyze.py  # Bielik LLM chunk analysis of an existing document (by ID)
```

## Scripts

### `check_pdf_text_layer.py`

Diagnostic for the book-PDF-import workflow: extracts text page-by-page with `pypdf` and reports what fraction of pages come back empty/near-empty. A high empty-page ratio means the PDF is scanned images with no embedded text layer and needs OCR (`test_code/ocr_mistral.py`, Mistral OCR API); a low ratio means the text layer can be used directly (no OCR cost/latency needed) before running it through `book_normalize.py` / `extract_references.py` and the rest of the chapter-based analysis pipeline. **Does not touch the Lenie database.**

**Running:**
```bash
cd backend
python imports/check_pdf_text_layer.py path/to/book.pdf                  # full scan, all pages
python imports/check_pdf_text_layer.py path/to/book.pdf --sample 40      # quick check, 40 evenly-spaced pages
python imports/check_pdf_text_layer.py path/to/book.pdf --show-sample 5  # also print 5 sample pages' text for manual QA
```

Exit code `0` when the text layer looks usable (`TEXT_LAYER_OK`), `1` otherwise (`OCR_NEEDED` or `UNCERTAIN`) — usable in scripts/CI-style checks.

### `book_import_pdf_<slug>.py` (one script per book)

Every book gets its own thin CLI script — `book_import_pdf_twierdza_linux.py` is the first/reference one. All the actual logic lives in `library/book_pdf_import.py` (pure functions on bytes/text with no filesystem assumptions beyond receiving the PDF as bytes, so the same code can later run from a worker/job instead of a developer machine — see `docs/deployment/nas/storage-and-jobs-migration-plan.md` Etap 3 "thin CLI wrapper" pattern) and is fully parameterized — there's no universal PDF signal for "this line marks a new chapter" or "this is a subheading", so each book's own script hardcodes its tuned values as CLI defaults (title, byline, `--chapter-regex`, `--heading-font-prefix`/`--heading-min-size`), all still overridable via CLI for one-off experiments. A new book means copying the pattern into `book_import_pdf_<slug>.py` with its own constants, not editing the shared library.

Extracts per-page text via **PyMuPDF (fitz)** (run [`check_pdf_text_layer.py`](#check_pdf_text_layerpy) first — no OCR step here; PyMuPDF was picked over `pypdf`/`pdfplumber` after a real comparison, see `docs/pdf-library-comparison.md` — notably PyMuPDF is AGPL-3.0/commercial-licensed, fine for this private non-SaaS use but flagged for re-evaluation before any hosted offering), detects chapter boundaries via a case-insensitive regex marker (`--chapter-regex`; `book_import_pdf_twierdza_linux.py`'s default matches the `// ROZDZIAŁ NNN //` / `// Rozdział NNN //` running-head style used by Sekurak books — small-caps fonts render as true mixed case in PyMuPDF, unlike `pypdf` which normalized to uppercase), strips repeated running heads/page numbers, joins words split by a soft hyphen (U+00AD) at a line wrap, inserts a paragraph break after a short line ending in sentence-final punctuation or before a bullet marker (additive only — never merges/drops a line, so code/config samples are never rewritten even where the heuristic misses a boundary), and **escapes any stray `#`/`##`-prefixed lines in body text** (shell/config code samples in technical books commonly start with `# comment` — without escaping, `library/text_functions.py`'s `detect_chapters()` mistakes hundreds of these for real H1 headers and swamps the real chapter markers; found the hard way importing doc 9332, "Twierdza Linux"). Also detects book subheadings via PDF font metadata (`detect_heading_texts(pdf_bytes, font_prefix, min_size)` — a line counts only when every span on it shares a distinct "display" font family at a size clearly above body text) and marks them `### <title>` so they don't visually blend into the surrounding paragraph in the reader — safely below `detect_chapters()`'s H1/H2 threshold. Creates a `Document` (`document_type='text'`, synthetic `url` like `file:///ksiazki/<slug>.pdf`) with the resulting chapter-marked markdown in `text_md`, and stores the original PDF bytes through `library/storage.py`'s `ObjectStorage` abstraction (not a raw file write) so switching `STORAGE_BACKEND` to MinIO later needs no pipeline changes.

**Image extraction** (`extract_page_images()`, on by default, `--no-images` to skip): pulls embedded illustrations out of the PDF via PyMuPDF, deduplicated by xref (a running-head logo/icon reused across dozens of pages keeps only its first occurrence) and filtered by minimum pixel dimensions/byte size to drop decorative furniture. Each kept image is stored via `ObjectStorage` under `documents/<uuid>/images/<n>.<ext>` and written to `document_images` (`storage_key`-sourced rows — see `library/document_images.py`) with a `[imgN]` marker inserted into `text_md` right before its page's figure caption line (detected by `caption_for_page()`, e.g. "Rysunek 5. ..."), or appended at the end of the page when no caption line is found. `chapter_position` on each image row is computed to match `library.text_functions.detect_chapters()`'s own numbering exactly (including its "(wstęp)" pseudo-chapter for front-matter text before the first real header) — a mismatch here means images attach to the wrong reader chapter.

**Data access: ORM (SQLAlchemy)** via `get_session()`, only when `--apply` is passed.

**Running:**
```bash
cd backend
python imports/book_import_pdf_twierdza_linux.py book.pdf                              # dry-run: chapter + image preview, no DB writes
python imports/book_import_pdf_twierdza_linux.py book.pdf --apply                       # creates the Document
python imports/book_import_pdf_twierdza_linux.py book.pdf --show 3
python imports/book_import_pdf_twierdza_linux.py book.pdf --no-images --apply           # skip image extraction
python imports/book_import_pdf_twierdza_linux.py other.pdf --title "..." --byline "..." --chapter-regex "..." --heading-font-prefix "..." --heading-min-size 11  # override for a one-off experiment
```

**Arguments** (defaults shown are `book_import_pdf_twierdza_linux.py`'s own; a new book's script hardcodes its own):
- `--title TEXT`, `--byline TEXT`, `--source NAME` (default `own`)
- `--url URL` — override the synthetic `file:///ksiazki/<slug>.pdf` URL
- `--chapter-regex REGEX` — override the chapter marker pattern
- `--heading-font-prefix TEXT` / `--heading-min-size FLOAT` — override subheading detection
- `--show N` — how many detected chapters to print in dry-run preview (default 5)
- `--no-images` — skip image extraction (default: extraction on)
- `--apply` — write to the database (default: dry-run only)

After import, run [`extract_references.py`](#extract_referencespy) for book footnotes, then the usual per-chapter analyses (`extract_time_periods.py`, `extract_tones.py`, `select_control_questions.py`) and chunk review via `/chunks/:id`.

### `book_extract_images.py`

Backfill counterpart to `book_import_pdf_<slug>.py`'s image extraction, for books imported before it existed. Re-derives per-page chapter positions by rebuilding markdown from the PDF (`build_book_markdown()`), but **never writes that markdown back** — the document's real `text_md` may already have been edited by `extract_references.py` (footnotes cut out), and overwriting it would lose that work. For the same reason this backfill never inserts `[imgN]` markers; images land in the reader's collapsible "Ilustracje" section instead of inline (`GET /document/<id>/chapter/<pos>`'s `inline` flag on each image). Also uploads the source PDF to storage if it isn't already there — a book imported while local storage writes were silently failing (permissions) never got its PDF saved at all. Uses `library/book_pdf_import.py`'s default heading font/size (Twierdza Linux's) — pass a different book's PDF and the subheading detection (cosmetic only, doesn't affect chapter_position) just won't match, which is harmless since this script never writes the rebuilt markdown anywhere.

**Data access: ORM (SQLAlchemy)** via `get_session()`, only when `--apply` is passed.

**Running:**
```bash
cd backend
python imports/book_extract_images.py --id 9332 --pdf "C:\...\twierdza-linux.pdf"           # dry-run
python imports/book_extract_images.py --id 9332 --pdf "C:\...\twierdza-linux.pdf" --apply
```

**Arguments:**
- `--id N` (required) — document id of the already-imported book
- `--pdf PATH` (required) — path to the original PDF file
- `--chapter-regex REGEX` — override the default `// ROZDZIAŁ NNN //` marker pattern
- `--apply` — write to storage/database (default: dry-run only, prints per-chapter image counts)

### `dynamodb_sync.py`

Incremental sync of documents from AWS DynamoDB and S3 webpage content to the local Docker PostgreSQL. No VPN, EC2, or RDS needed — uses standard AWS API access over the internet.

**Resource discovery via SSM Parameter Store.** DynamoDB table name and S3 bucket name are resolved from SSM using the project/environment convention (`/{project}/{env}/dynamodb/documents/name`, `/{project}/{env}/s3/website-content/name`). CLI overrides (`--table`, `--bucket`) skip the SSM lookup.

**Data access: DynamoDB + S3 → ORM (SQLAlchemy)**. Reads from DynamoDB (DateIndex GSI) and S3, writes via `DocumentService.import_document()`. Run history is recorded in `import_logs` via `ImportLogTracker`.

**How it works:**
1. Resolves DynamoDB table name and S3 bucket from SSM Parameter Store (or CLI overrides)
2. Resolves an exact incremental watermark with second precision. By default it uses the UTC start time of the latest successful run; using the start rather than finish prevents losing items created while that run was querying DynamoDB.
3. Queries UTC `DateIndex` partitions day-by-day, handles pagination, then retains records with `created_at >= watermark`. The partition key `created_date` is always a UTC calendar date, independent of workstation time.
4. For each item, checks if URL already exists in local PostgreSQL (duplicate detection via `Document.get_by_url()`)
5. For `webpage` type items with `uuid`: fetches `{uuid}.txt` and `{uuid}.html` from S3 into memory
6. Inserts new documents via `DocumentService.import_document(skip_if_exists=True)`
7. After insert, saves S3 content to cache as `{CACHE_DIR}/markdown/{doc.id}/{doc.id}.html` (same convention as `document_prepare.py`, so downstream tools can reuse cached files without re-downloading from S3)
8. For webpages: converts HTML to markdown (`_step_1_all.md`) and runs LLM article extraction (CloudFerro primary, ARK Labs fallback) unless `--skip-llm`. On successful extraction, persists `text_extracted` (raw LLM output, pre-clean) and `text_md` (after `article_cleaner.clean_article_text()`) on the document, and replaces the document's `document_images` rows (`library/document_images.py`) — `--skip-llm` and failed extraction leave both fields untouched
9. Sets `processing_status` to `DOCUMENT_INTO_DATABASE` (with S3 content) or `URL_ADDED` (without)

**DynamoDB → PostgreSQL field mapping:**
- `url` → `url`, `type` → `document_type`, `title` → `title`, `language` → `language`
- `source` → `source` (default "own"), `note` → `note`, `paywall` → `paywall`
- `chapter_list` → `chapter_list`, `s3_uuid` → `uuid` (backward-compat: reads both `uuid` and `s3_uuid` from DynamoDB), `created_at` → `ingested_at` (historical DynamoDB items keep the old field name)
- S3 `{uuid}.txt` → `text`, S3 `{uuid}.html` → `text_raw`

**Running:**
```bash
cd backend
./imports/dynamodb_sync.py                                  # exact timestamp from latest successful run, UTC
./imports/dynamodb_sync.py --since 2026-02-20T14:30:00Z     # explicit UTC timestamp
./imports/dynamodb_sync.py --since 2026-02-20T15:30:00 --timezone Europe/Warsaw
./imports/dynamodb_sync.py --since 2026-02-20               # midnight in --timezone
./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
./imports/dynamodb_sync.py --since 2026-02-20 --limit 10
./imports/dynamodb_sync.py --since 2026-02-20 --skip-s3
./imports/dynamodb_sync.py --since 2026-02-20 --env dev --project lenie
```

**Arguments:**
- `--since ISO-8601` (optional) — inclusive date/time watermark. A date means midnight; a naive timestamp is interpreted in `--timezone`; a timestamp with offset or `Z` keeps its own offset. If omitted, the start timestamp of the latest successful run is used with second precision.
- `--timezone IANA_ZONE` — working timezone for parsing naive `--since` values and displaying the automatic watermark (default: `UTC`; example: `Europe/Warsaw`). DynamoDB partitions remain UTC regardless of this option.
- `--dry-run` — preview only, no DB writes or S3 downloads
- `--limit N` — max documents to sync (for testing)
- `--skip-s3` — metadata only, skip S3 file downloads
- `--skip-llm` — skip LLM article extraction (still converts HTML to markdown)
- `--project CODE` — project code for SSM path (default: `lenie`)
- `--env ENV` — environment for SSM path (default: `dev`)
- `--table TABLE` — DynamoDB table name override (skips SSM lookup)
- `--bucket BUCKET` — S3 bucket name override (skips SSM lookup)
- `--data-dir PATH` — cache dir for S3 files (default: `os.path.join(CACHE_DIR, 'markdown')`)
- `-y`, `--yes` — skip confirmation prompt (for automation)

Before executing any operations, the script displays source (AWS profile, region) and target (PostgreSQL host/db/port/user) information, then asks for confirmation (`Continue? [Y/n]`, Enter accepts). Use `-y` to skip the prompt.

**UTC and incremental safety:** DynamoDB uses `created_date` as a UTC partition key and `created_at` as the precise creation timestamp. PostgreSQL import-log timestamps are also interpreted as UTC. The next automatic run starts inclusively from the previous successful run's `started_at`, not `finished_at`. This intentionally re-reads a small overlap, preventing an item written during the prior query from falling behind its watermark. URL deduplication makes this overlap idempotent. `--timezone` affects parsing and display only; comparisons and DynamoDB partition selection always use UTC.

**SSM parameters used:**
- `/{project}/{env}/dynamodb/documents/name` — DynamoDB table name
- `/{project}/{env}/s3/website-content/name` — S3 bucket for webpage content

**Prerequisites:**
- PostgreSQL database must be accessible (local Docker on port 5433) — not required for `--dry-run` with explicit `--since`
- `.env` file with `POSTGRESQL_*` variables
- AWS credentials (via env vars or AWS profile) with SSM read, DynamoDB read, and S3 read access

### Legacy feed monitor (removed)

Feed monitoring was moved to `library/feed_parser.py`, `library/feed_monitor_service.py`, the REST API and `worker.py`. The former CLI, YAML seed and file-based review flow were removed. The historical notes below are migration context only; do not use those commands.

The former CLI feed monitor was removed. Feed sources and candidates now live in PostgreSQL and are handled by `library/feed_parser.py`, `library/feed_monitor_service.py`, the REST API and `worker.py`.

**Data access: ORM (SQLAlchemy)** via `DocumentService.import_document()`. Run history is recorded in `import_logs` via `ImportLogTracker`. DB connection is optional for `--check`/`--review` (only used to mark entries as NEW / IN DB).

**Feed types:**
- `youtube_channel` — YouTube channel Atom feed (built from `channel_id`)
- `wordpress` / `rss` — RSS 2.0 / Atom feeds
- `json_api` — JSON API (e.g. unknow.news `archiwum.json`), with per-feed `field_mapping`

**Modes:**
- `--list` — show configured feeds with type, language, project, tags, flags
- `--check` — list new items from all (or one) feeds; `--db` marks NEW / IN DB; `--ignored` shows only entries filtered out by skip patterns
- `--import` — import new items. Feeds with `auto_import: true` are imported without interaction; other feeds show a numbered list for interactive selection (`1,3,5`, `1-5`, `all`, `none`)
- The old interactive review actions were replaced by the REST API and Web UI. Use `.claude/commands/lenie-feed-review.md` for the current workflow.

**Date cutoff priority** (per feed): explicit `--since` → last import date from DB (`auto_import` feeds only) → `last_checked` from `feeds_state.yaml` → default 14 days back. `--since` accepts `YYYY-MM-DD` or natural language (`"last 2 weeks"`, `"3 days ago"`) parsed via dateparser.

Feed configuration is stored in PostgreSQL `feed_sources`, including source URL, collection, tags, auto-import watermark and skip patterns.

**State:** check timestamps, errors and review decisions are stored in PostgreSQL.

**Running:**
```bash
cd backend
GET /feed_sources
POST /feed_sources/{id}/check
GET /feed_items?status=new
POST /feed_items/{id}/import
```

The Web UI exposes the same operations under **Feedy**, **Kuracja feedów** and **Joby**.

**Prerequisites:**
- `.env` with `POSTGRESQL_*` variables (for `--import`, and for `--check`/`--review` with `--db`)
- Network access to the configured feed URLs

### `article_browser.py` (removed 2026-07-24)

Formerly an interactive ORM-based browser/review tool for articles, and the data source the `/lenie-obsidian-note` skill shelled out to. Progressively hollowed out on 2026-07-24 as its responsibilities moved elsewhere, then deleted once nothing unique was left:
- `--meta`/`--dump`/`--dump-md`/`--runs`/`--chunks`/`--chunk-text` (JSON dump modes for `/lenie-obsidian-note`) → replaced by the backend REST API (`GET /website_get`, `/analysis_runs`, `/analysis_run/<id>/chunks`, `/document/<id>/control_questions`), used by both the Claude Code (`.claude/commands/lenie-obsidian-note.md`) and Codex (`.agents/skills/lenie-obsidian-note/references/workflow.md`) skill variants.
- `[v]iew`/`[b]oundaries`/`[e]ncje`/`[m]ark review`/`[s]ave note`/`[w]rite to db` (`--review` actions) → duplicated the React web UI's `/webpage/:id` (edit form) and `/chunks/:id` (chunk review) pages (`EntitiesPanel`, `ArticleSourceComparison`, the chunk-based `document_analysis_service` pipeline).
- `[c]ompare` → duplicated `/lenie-obsidian-note`'s Step 3 ("Find related notes via index").
- The rest (`--list`, `--show`, `--notes`, and `--review`'s `[n]ext`/`[p]rev`/`[r]efresh`/`[d]one`/`[o]bsidian`/`[k]raje`/`[q]uit`) had no replacement when removed — full history and the deleted implementation are in git (`git log -- backend/imports/article_browser.py`).
- Obsidian vault path is currently hardcoded (`OBSIDIAN_VAULT` constant) — see backlog for moving it to config

### `youtube_add.py`

Ad-hoc CLI tool for processing a single YouTube video: adds it to the database, fetches metadata (title, language), downloads captions or transcription, and optionally generates an AI summary and/or runs the full Bielik LLM chunk analysis (`--analyze`).

**Data access: ORM (SQLAlchemy)** via `process_youtube_url()` from `library.youtube_processing`; with `--analyze` also `DocumentAnalysisService` from `library.document_analysis_service` + file exports from `library.analysis_exports`.

**How it works:**
1. Optionally authenticates Webshare proxy (checks bandwidth, disables if exhausted)
2. Calls `process_youtube_url()` with the provided URL and options
3. Prints a summary (ID, title, URL, language, state, text length, elapsed time)
4. With `--analyze`: runs `DocumentAnalysisService.create_run()` on the new document and exports MD/JSON/debug/HTML files to `.claude/exports/`. If analysis fails, the document stays in the database and the script prints the `youtube_batch_analyze.py` command to retry.

**Running:**
```bash
cd backend
python imports/youtube_add.py <URL>
python imports/youtube_add.py <URL> --language pl --note "..." --source own
python imports/youtube_add.py <URL> --summary --force
python imports/youtube_add.py <URL> --chapters-file chapters.txt -v
python imports/youtube_add.py <URL> --analyze                              # full pipeline in one command
python imports/youtube_add.py <URL> --analyze --speaker1 "..." --speaker2 "..."
```

**Arguments:**
- `url` — YouTube video URL (required)
- `--language CODE` — language code (e.g. `pl`, `en`); auto-detected if omitted
- `--note TEXT` — note to attach to the document
- `--source ID` — source identifier (default: `own`)
- `--chapters TEXT` — chapter list as inline text
- `--chapters-file PATH` — path to file with chapter list
- `--summary` — generate AI summary after processing
- `--force` — reprocess even if embeddings already exist
- `--no-proxy` — disable Webshare proxy
- `--analyze` — run Bielik LLM chunk analysis after processing (see [`youtube_batch_analyze.py`](#youtube_batch_analyzepy))
- `--model NAME` — LLM model for `--analyze` (default: `Bielik-11B-v3.0-Instruct`)
- `--speaker1 NAME` / `--speaker2 NAME` — `--analyze`: explicit speaker names (skips LLM speaker extraction)
- `--no-synthesis` — `--analyze`: skip the final synthesis step
- `-v`, `--verbose` — enable debug logging

**Prerequisites:**
- `.env` file with `POSTGRESQL_*` variables and LLM API keys
- Optional: `WEBSHARE_API_KEY` for proxy support
- For `--analyze`: `CLOUDFERRO_SHERLOCK_KEY` (Bielik)

### `youtube_backfill_author.py`

One-off backfill for the `byline` field (YouTube channel name) on videos added before `youtube_processing.py` started setting it automatically (`process_youtube_url()` sets the document byline from `youtube_file.author` on every new video). Queries `documents` for `document_type='youtube' AND byline IS NULL`, re-fetches metadata per video via `pytubefix`, and commits per document.

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/youtube_backfill_author.py --dry-run              # preview, no DB writes
python imports/youtube_backfill_author.py                        # full backfill
python imports/youtube_backfill_author.py --limit 20 --delay 2
python imports/youtube_backfill_author.py --no-proxy             # skip Webshare (was not needed in practice — no rate-limiting observed on a 10-video sample)
```

**Arguments:**
- `--dry-run` — preview only, no DB writes
- `--limit N` — max number of videos to process
- `--delay SECONDS` — sleep between requests (default: 1.5)
- `--no-proxy` — disable Webshare proxy
- `-v`, `--verbose` — enable debug logging

**Prerequisites:**
- `.env` with `POSTGRESQL_*` variables
- Optional: `WEBSHARE_API_KEY` for proxy support (see `youtube_add.py`)

### `extract_references.py`

Extracts book footnotes ("¹⁸ https://... (dostęp: ...)", "29 Eurostat.") out of a document's `text_md` into the `document_references` table (`library/references.py` — see there for the detection heuristics) and updates `text_md` to the cleaned text. Replace semantics — safe to re-run. **After `--apply`, re-run NER** for the document so entities are rebuilt from the clean text (footnote URLs used to become junk person entities).

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/extract_references.py --id 9204           # dry-run (default)
python imports/extract_references.py --id 9204 --apply
python imports/extract_references.py --id 9204 --show 30 # more dry-run samples
```

### `extract_time_periods.py`

Classifies the historical period a document's content is about ("współczesność", "zimna wojna", "starożytny Egipt") into the `document_time_periods` table (`library/time_periods.py`) — one LLM call per reader chapter for books, one for the whole document otherwise. Up to 3 periods per chapter (main period first), each with an approximate year range (BCE = negative) for future search filtering by period. Replace semantics — safe to re-run. Read back via `GET /document/<id>/time_periods`.

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/extract_time_periods.py --id 9144 --dry-run     # preview, no DB writes
python imports/extract_time_periods.py --id 9144               # classify + store
python imports/extract_time_periods.py --id 9204 --chapter 37  # re-run one book chapter
```

### `extract_tones.py`

Classifies the emotional tone and language register of a document into the `document_tones` table (`library/tones.py`) — one LLM call per reader chapter for books, one for the whole document otherwise. Two separate axes per chapter: emotion (closed list: neutralny/radosny/smutny/gniewny/alarmistyczny/podniosły/refleksyjny + sentiment + intensity) and language register (formalny/potoczny/dziecinny/wulgarny/obraźliwy/ironiczny) — a joyful text written in childish language is emotion `radosny` + register `dziecinny`. Labels are validated against the closed lists (diacritic-tolerant). Replace semantics — safe to re-run. Read back via `GET /document/<id>/tones`; the reader shows the current chapter's tone in the "🎭 Ton rozdziału" sidebar panel.

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/extract_tones.py --id 9144 --dry-run     # preview, no DB writes
python imports/extract_tones.py --id 9144               # classify + store
python imports/extract_tones.py --id 9204 --chapter 9   # re-run one book chapter
```

### `fix_duplicate_analysis_runs.py`

One-off cleanup for abandoned duplicate analysis runs — the state left behind before `document_analysis_service.create_run()` started superseding unfinished sibling runs automatically. Finds every `(document_id, scope)` group with more than one run, marks each non-newest run that never reached `reviewed` as `status='superseded'` and flips its still-open chunks (`pending`/`needs_reanalysis`/`split_requested`) to `skipped`, so they drop out of the "missing Obsidian notes" filter on `/list`. Runs whose chunks already carry Obsidian notes are reported but never touched; nothing is deleted (history stays browsable in `/chunks/:id`).

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/fix_duplicate_analysis_runs.py            # dry-run (default)
python imports/fix_duplicate_analysis_runs.py --apply    # write changes
python imports/fix_duplicate_analysis_runs.py --id 9245  # single document
```

### `fix_place_tags.py`

One-off cleanup: merges duplicate `miejsce-*` tags created before `place_verification.py` started slugging tags from the geocoder's canonical spelling — inflected NER variants used to each get their own tag (`miejsce-kijowa` + `miejsce-kijow`). Recomputes each document's `miejsce-*` tags via `canonical_place_name()` on `geocode_cache.display_name` (no live geocoder calls) and rewrites `documents.tags`, dropping duplicates. Tags with no matching resolved place entity are left untouched. Run on the NAS DB 2026-07-11 (1 document updated).

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/fix_place_tags.py            # dry-run (default)
python imports/fix_place_tags.py --apply    # write changes
python imports/fix_place_tags.py --id 9216  # single document
```

### `organization_descriptions_backfill.py`

One-off backfill for `Organization.description` (global organization registry, `library/db/models.py`) — shown as a tooltip and ℹ️ marker on organization chips in the reader (`EntitiesPanel.tsx`/`read.tsx`, `GET /website_entities`'s `organization_description` field). For each organization missing a description, asks the tagging LLM (`TAGGING_MODEL` config, default Bielik) for one short Polish sentence; skips (never guesses) an organization the model answers "NIEZNANA" for, so an ambiguous/obscure name doesn't get a wrong tooltip shown to every future reader. New organizations resolved after this backfill (or edited by a human) can also get their `description` set directly via `PATCH /organizations/<id>` from the reader's "Edytuj" mode.

**Data access: ORM (SQLAlchemy)** via `get_session()`, only when `--apply` is passed. LLM calls happen in both dry-run and `--apply` (there's no other way to preview the description).

**Running:**
```bash
cd backend
python imports/organization_descriptions_backfill.py            # dry-run (default)
python imports/organization_descriptions_backfill.py --apply
python imports/organization_descriptions_backfill.py --apply --limit 20
python imports/organization_descriptions_backfill.py --apply --id 534
```

**Arguments:**
- `--apply` — write to the database (default: dry-run only, prints what each organization would get)
- `--id N` — process a single organization by id
- `--limit N` — max number of organizations to process

### `backfill_obsidian_content_groups.py`

One-off backfill for the content-group (Tematy) auto-classification hook added to `obsidian_reimport_service.py` — that hook only fires for notes created/updated after it shipped, so already-imported `obsidian_note` documents (e.g. #9922 "jq", tagged `linux` but with no "Linux" content group membership) need a retroactive pass. Enqueues a `content_group_suggest` job per document via `content_group_suggestion_service.request_suggestions()` — **does not call the LLM itself**; classification (and, above `CONTENT_GROUP_AUTO_APPLY_MIN_CONFIDENCE`, auto-assignment into `content_groups`) happens asynchronously via the worker already running on the NAS. By default only documents with zero existing group memberships are enqueued (`--force` to include already-classified ones too).

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/backfill_obsidian_content_groups.py                    # dry-run (default)
python imports/backfill_obsidian_content_groups.py --apply
python imports/backfill_obsidian_content_groups.py --apply --id 9922  # single document
python imports/backfill_obsidian_content_groups.py --apply --limit 20
```

**Arguments:**
- `--apply` — enqueue jobs (default: dry-run, lists candidates only)
- `--id N` — process a single document by id
- `--limit N` — max number of documents to process
- `--force` — also re-enqueue documents that already have a content group membership

### `youtube_batch_analyze.py`

Bielik LLM chunk analysis of an **existing** document (by `--doc_id`): chunk splitting, speaker extraction/labeling, two-pass rewrite + summarize, topic grouping, synthesis, DB persistence. Moved from `test_code/` — the pipeline lives in `library/document_analysis_service.py` + `library/chunk_llm_analysis.py` (shared with Flask `chunk_review_routes.py`); file exports in `library/analysis_exports.py`. For a brand-new video, use `youtube_add.py <URL> --analyze` instead.

**Data access: ORM (SQLAlchemy)** via `DocumentAnalysisService.create_run()`; writes `document_analysis_runs` / `document_chunks` / `document_topic_sections` and exports MD/JSON/debug/HTML (with YouTube timestamp links) to `.claude/exports/`.

**Running:**
```bash
cd backend
python imports/youtube_batch_analyze.py --doc_id 9158
python imports/youtube_batch_analyze.py --doc_id 9158 --dry_run          # chunk breakdown + cost estimate, no API calls
python imports/youtube_batch_analyze.py --doc_id 9158 --no_synthesis
python imports/youtube_batch_analyze.py --doc_id 9158 --speaker1 "..." --speaker2 "..."
```

**Arguments:**
- `--doc_id N` — document ID in the database (required)
- `--model NAME` — LLM model (default: `Bielik-11B-v3.0-Instruct`; also `arklabs/...` variant)
- `--chunk_size N` — characters per chunk (default: 5000 ≈ 1500 tokens)
- `--speaker1 NAME` / `--speaker2 NAME` — explicit speaker names (skips LLM speaker extraction)
- `--no_synthesis` — skip the final synthesis step
- `--dry_run` — preview chunk breakdown and cost estimate without calling the API

**Prerequisites:**
- `.env` with `POSTGRESQL_*` variables and `CLOUDFERRO_SHERLOCK_KEY`
- Cost: ~0.05 EUR per 90K-char transcript at 0.56 EUR/M tokens

### `freedom_house_import.py`

Standalone query tool for Freedom House "Freedom in the World" country ratings, fetched from the Our World in Data API. **Does not touch the Lenie database** — data is cached as CSV in `{CACHE_DIR}/freedom_house.csv` (default `backend/tmp/`). Supports Polish and English country names (built-in mapping) and generates ready-to-paste markdown blocks for Obsidian country notes.

**Running:**
```bash
cd backend
python imports/freedom_house_import.py --download                 # fetch/update the CSV cache (run first)
python imports/freedom_house_import.py --country "Korea Północna" # latest data, PL or EN name
python imports/freedom_house_import.py --country Poland --history # all years
python imports/freedom_house_import.py --list --status "Not Free"
python imports/freedom_house_import.py --markdown "Iran"          # markdown block for Obsidian
```

### `control_questions.py`

Standalone helper that filters "control questions" (geopolitical analysis prompts) from a markdown file in the Obsidian vault by thematic tags. **Does not touch the Lenie database.** Used when writing country/region notes to pull only the relevant question sections.

**Running:**
```bash
python imports/control_questions.py --list-tags
python imports/control_questions.py --tags wojsko,gospodarka,sojusze
python imports/control_questions.py --tags geopolityka --file path/to/questions.md
```

The default questions file path is currently hardcoded (Obsidian vault) — see backlog for moving it to config.

### `import_control_questions.py`

One-way sync of the Obsidian control-question bank (`_pytania_kontrolne/*.md`) into the `control_questions` DB
table. Necessary because `_pytania_kontrolne/*.md` falls outside the two pilot subfolders (`02-wiedza/Informatyka`,
`02-wiedza/Geopolityka i polityka`) that `library/obsidian_reimport_service.py` (Epic 42) gives the backend (NAS)
runtime read access to — `library/control_question_selection.py`'s router reads this table, not the filesystem.
Reuses `parse_sections()`/`TAG_TO_HEADERS` from `control_questions.py` (one heading = one question; body text is
context/examples for a human author, not sub-questions). Replace semantics per `source_file` — safe to re-run
after editing questions in Obsidian. **Does not touch the Lenie database** in dry-run (default) mode.

**Data access: ORM (SQLAlchemy)** via `get_session()`, only when `--apply` is passed.

**Running:**
```bash
cd backend
python imports/import_control_questions.py               # dry-run preview, all .md files in the default vault dir
python imports/import_control_questions.py --apply
python imports/import_control_questions.py --dir "C:\...\_pytania_kontrolne" --apply
```

### `select_control_questions.py`

Cheap-LLM (Bielik) router: for one document, selects which control questions (from `control_questions`, filtered
to the document's tags) are actually answered by its content, and stores the answers in
`document_control_answers` (`library/control_question_selection.py`, replace semantics, per reader chapter for
books). Zero LLM calls when the document has no tag matching any active question. Also runs automatically as
part of `library/document_enrichment.py`'s per-document enrichment stage — this CLI is for manual/local runs
(dry-run preview, single-chapter reruns). The `/lenie-obsidian-note` skill's on-demand trigger goes through
`POST /document/<id>/select_control_questions` instead (same `refresh_document_control_answers()` under the
hood) so it doesn't need direct ORM/DB access from the caller's machine.

**Data access: ORM (SQLAlchemy)** via `get_session()`.

**Running:**
```bash
cd backend
python imports/select_control_questions.py --id 9204 --dry-run     # preview, no DB writes
python imports/select_control_questions.py --id 9204                # classify + store
python imports/select_control_questions.py --id 9204 --chapter 37   # re-run one book chapter
```

### `migrate_data_to_cache.py`

One-time migration script: copies UUID-named `.html`/`.txt` files from `imports/data/` (legacy S3 download location) into the `{CACHE_DIR}/markdown/{doc_id}/{doc_id}.ext` convention used by `document_prepare.py`. Looks up `doc_id` by `uuid` in PostgreSQL. Files are **copied**, not moved — use `--delete-source` to remove originals after a successful copy. Supports `--dry-run`, `--source-dir`, `--target-dir`.

## Architecture Notes

- All scripts bypass the REST API intentionally — they are meant for local or scheduled operations, not the web interface.
- DB-writing scripts use ORM models (`Document` from `library.db.models`) with `get_session()` from `library.db.engine`. Session lifecycle: `session = get_session()` → `try` → `session.commit()` → `finally` → `session.close()`.
- Document creation goes through `DocumentService.import_document(skip_if_exists=True)` (`library/document_service.py`), which handles duplicate detection via `Document.get_by_url()`.
- Bulk import runs from the remaining CLI tools are recorded in the `import_logs` table via `ImportLogTracker` (`library/import_log_tracker.py`). `dynamodb_sync.py` uses the latest successful run's UTC `started_at` as its exact automatic watermark. Legacy `since_date`/`until_date` remain day-level reporting fields; the exact UTC watermark and selected timezone are stored in `parameters`.
- `control_questions.py` and `freedom_house_import.py` are standalone tools that never touch the database.
