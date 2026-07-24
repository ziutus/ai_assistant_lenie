# Backend Imports — CLAUDE.md

Standalone CLI scripts that add or manage documents in the Lenie database, bypassing the REST API. Covers single-item ad-hoc tools, bulk import pipelines, and a few standalone helper tools that do not touch the database at all.

## Directory Structure

```
imports/
├── article_browser.py        # Interactive browser / review tool for DB articles + Obsidian integration
├── control_questions.py      # Filter control questions from an Obsidian markdown file by tags (no DB)
├── import_control_questions.py # Sync the Obsidian control-question bank into the control_questions DB table
├── select_control_questions.py # Cheap-LLM (Bielik) router: which control questions a document actually answers
├── dynamodb_sync.py          # Sync documents from DynamoDB + S3 to local PostgreSQL
├── feed_monitor.py           # Monitor RSS/Atom/JSON feeds and import new entries
├── feeds.yaml                # Feed definitions for feed_monitor.py (committed)
├── extract_references.py     # Extract book footnotes from text_md into document_references
├── extract_time_periods.py   # Classify the historical period a document is about (per chapter for books)
├── extract_tones.py          # Classify emotional tone + language register per chapter
├── feeds_state.yaml          # Per-feed last_checked state (gitignored, created at runtime)
├── fix_duplicate_analysis_runs.py # One-off: supersede abandoned duplicate analysis runs (same document+scope, never reviewed)
├── fix_place_tags.py         # One-off: merge duplicate miejsce-* tags (inflected NER variants) via geocode_cache
├── freedom_house_import.py   # Query Freedom House country ratings via OWID API (no DB)
├── migrate_data_to_cache.py  # One-time migration: data/ files → CACHE_DIR convention
├── youtube_add.py            # Ad-hoc: process a single YouTube video (optionally + LLM analysis)
├── youtube_backfill_author.py # One-off: fetch channel name for existing videos missing 'byline'
└── youtube_batch_analyze.py  # Bielik LLM chunk analysis of an existing document (by ID)
```

## Scripts

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

### `feed_monitor.py`

Monitors RSS/Atom/JSON feeds defined in [`feeds.yaml`](feeds.yaml) and imports selected entries into the database. Replaces the old `unknown_news_import.py` script (removed; unknow.news is configured as a `json_api` feed with `auto_import: true`).

**Data access: ORM (SQLAlchemy)** via `DocumentService.import_document()`. Run history is recorded in `import_logs` via `ImportLogTracker`. DB connection is optional for `--check`/`--review` (only used to mark entries as NEW / IN DB).

**Feed types:**
- `youtube_channel` — YouTube channel Atom feed (built from `channel_id`)
- `wordpress` / `rss` — RSS 2.0 / Atom feeds
- `json_api` — JSON API (e.g. unknow.news `archiwum.json`), with per-feed `field_mapping`

**Modes:**
- `--list` — show configured feeds with type, language, project, tags, flags
- `--check` — list new items from all (or one) feeds; `--db` marks NEW / IN DB; `--ignored` shows only entries filtered out by skip patterns
- `--import` — import new items. Feeds with `auto_import: true` are imported without interaction; other feeds show a numbered list for interactive selection (`1,3,5`, `1-5`, `all`, `none`)
- `--review` — interactive per-entry loop with actions: [n]ext, [a]dd to DB, [d]iscuss (append to `tmp/feed_review_discuss.md` for a later Claude Code session — see the `/feed-review` skill), [i]gnore (add a `skip_title_patterns` regex to `feeds.yaml`), [e]xplain (open `claude -p` on the URL), [q]uit

**Date cutoff priority** (per feed): explicit `--since` → last import date from DB (`auto_import` feeds only) → `last_checked` from `feeds_state.yaml` → default 14 days back. `--since` accepts `YYYY-MM-DD` or natural language (`"last 2 weeks"`, `"3 days ago"`) parsed via dateparser.

**`feeds.yaml` per-feed keys:** `name`, `type`, `url` or `channel_id`, `language`, `project`, `tags`, `auto_import`, `source_id` (value stored in the document `source` field), `default_state` (initial `processing_status`, default `URL_ADDED`), `field_mapping` (json_api only), `skip_url_patterns` (prefix match), `skip_title_patterns` (regex, case-insensitive), `cache_path`, `disabled` (skipped unless explicitly selected via `--source`).

**State:** `feeds_state.yaml` (gitignored) stores `last_checked` per feed, updated after each `--check`/`--import`/`--review` run.

**Running:**
```bash
cd backend
python imports/feed_monitor.py --list
python imports/feed_monitor.py --check --db
python imports/feed_monitor.py --check --source "malak.cloud" --since 2026-03-01
python imports/feed_monitor.py --import                              # interactive selection
python imports/feed_monitor.py --import --source "unknow.news"       # auto-import feed
python imports/feed_monitor.py --import --dry-run --limit 5
python imports/feed_monitor.py --review --source 12 --since "last 2 weeks"
```

`--source` accepts a feed name or its number from `--list` output.

**Prerequisites:**
- `.env` with `POSTGRESQL_*` variables (for `--import`, and for `--check`/`--review` with `--db`)
- Network access to the configured feed URLs

### `article_browser.py`

Interactive browser and review tool for articles already in the database. Displays cleaned article text, manages review state, tags, embeddings, and integrates with Claude Code to create/update Obsidian notes. The `/obsidian-note` slash command (both the Claude Code and Codex skill variants) reads document/chunk data via the backend REST API instead (`GET /website_get`, `/analysis_runs`, `/analysis_run/<id>/chunks`, `/document/<id>/control_questions`) — see [`.claude/commands/obsidian-note.md`](../../.claude/commands/obsidian-note.md) and [`.agents/skills/obsidian-note/references/workflow.md`](../../.agents/skills/obsidian-note/references/workflow.md). The JSON dump modes this tool used to expose for that purpose (`--meta`, `--dump`, `--dump-md`, `--runs`, `--chunks`, `--chunk-text`) were removed 2026-07-24 once both skills migrated off them.

**Data access: ORM (SQLAlchemy)** + cache files in `{CACHE_DIR}/markdown/{doc_id}/` + S3 fallback (downloads HTML and converts to markdown when cache is missing).

**Modes** (mutually exclusive):
- `--list` — list articles; `--format table` (default), `ids` (one ID per line, for scripting), `short` (ID + title)
- `--review` — interactive per-article loop (see actions below); `--view` auto-displays text
- `--show --id N` — display metadata + article text, non-interactive; `--check-urls` validates links/images via HEAD requests
- `--notes` — list saved per-article notes from `tmp/article_notes/`

**Filters** (for `--list` / `--review`): `--since`, `--portal` (URL substring), `--state`, `--limit`, `--not-reviewed` (`reviewed_at IS NULL`), `--no-obsidian` (no Obsidian notes yet), `--not-cleaned` (fast flow: states still processable by regexp+LLM, excludes `NEED_MANUAL_REVIEW`), `--manual-review` (slow flow: shortcut for `--state NEED_MANUAL_REVIEW`). All filtering happens SQL-side.

**Text resolution order** (`get_article_text`): youtube/movie → transcript from `doc.text`; `doc.text` if state is `MD_SIMPLIFIED`/`EMBEDDING_EXIST`; cache files (`_step_2_1_article.md` preferred over `_llm_extracted_article.md`); otherwise download HTML from S3, convert to markdown (`_step_1_all.md`) and run LLM extraction. Cleaned via `library/article_cleaner.py`.

**Review actions:** [n]ext, [p]rev, [v]iew, [b]oundaries (show what was cut before/after the cleaned text, expands by ~400 chars per press), [r]efresh (clear LLM cache and re-extract), [w]rite to db (save cleaned text, LLM thematic tags via `library/article_tagging.py`, country tags, NER entities via `library/entity_service.py`, embedding → `EMBEDDING_EXIST`), [s]ave note (personal note to `tmp/article_notes/{id}_note.md`), [d]one (set `reviewed_at`), [m]ark review (toggle `NEED_MANUAL_REVIEW` state), [o]bsidian (Claude Code creates/updates an Obsidian note, then records the note path in `obsidian_note_paths`), [c]ompare (Claude Code compares article with existing notes, read-only), [k]raje (extract country tags — gazetteer prescreen + LLM confirmation, `library/article_tagging.py:extract_countries_hybrid`), [e]ncje (detect persons/places via the NER service, store them in `document_entities`, then verify places — geocoder + LLM → `miejsce-*` tags, ✓ next to verified names — and resolve persons — alias/Wikidata+LLM/fuzzy → `document_persons` links with confidence), [q]uit.

**Running:**
```bash
cd backend
python imports/article_browser.py --list --state NEED_MANUAL_REVIEW --format short
python imports/article_browser.py --review --not-cleaned
python imports/article_browser.py --review --view --manual-review
python imports/article_browser.py --show --id 8799 --check-urls
```

**Prerequisites:**
- `.env` with `POSTGRESQL_*` variables, LLM API keys (extraction/tagging), S3 access for cache misses
- `claude` CLI on PATH for the [o]bsidian / [c]ompare actions
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
table. Necessary because the backend (NAS) has no runtime access to the Obsidian vault, which lives only on the
user's local machine — `library/control_question_selection.py`'s router reads this table, not the filesystem.
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
(dry-run preview, single-chapter reruns). The `/obsidian-note` skill's on-demand trigger goes through
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
- Bulk import runs (`dynamodb_sync.py`, `feed_monitor.py`) are recorded in the `import_logs` table via `ImportLogTracker` (`library/import_log_tracker.py`). `dynamodb_sync.py` uses the latest successful run's UTC `started_at` as its exact automatic watermark. Legacy `since_date`/`until_date` remain day-level reporting fields; the exact UTC watermark and selected timezone are stored in `parameters`.
- `control_questions.py` and `freedom_house_import.py` are standalone tools that never touch the database.
