# Backend Imports — CLAUDE.md

Standalone CLI scripts that add or manage documents in the Lenie database, bypassing the REST API. Covers both single-item ad-hoc tools and bulk import pipelines.

## Directory Structure

```
imports/
├── dynamodb_sync.py          # Sync documents from DynamoDB + S3 to local PostgreSQL
├── unknown_news_import.py    # Import curated links from unknow.news
├── youtube_add.py            # Ad-hoc: process a single YouTube video
├── email_import.py           # Ad-hoc: import a Gmail email (via gws CLI)
├── article_browser.py        # Interactive browser / review tool for DB articles
├── feed_monitor.py           # Monitor RSS/Atom feeds and import new entries
└── freedom_house_import.py   # Import Freedom House country ratings
```

## Scripts

### `dynamodb_sync.py`

Incremental sync of documents from AWS DynamoDB and S3 webpage content to the local Docker PostgreSQL. No VPN, EC2, or RDS needed — uses standard AWS API access over the internet.

**Resource discovery via SSM Parameter Store.** DynamoDB table name and S3 bucket name are resolved from SSM using the project/environment convention (`/{project}/{env}/dynamodb/documents/name`, `/{project}/{env}/s3/website-content/name`). CLI overrides (`--table`, `--bucket`) skip the SSM lookup.

**Data access: DynamoDB + S3 → ORM (SQLAlchemy)**. Reads from DynamoDB (DateIndex GSI) and S3, writes via `WebDocument` ORM model with `session.add()` + `session.commit()`. All fields including `created_at` and `chapter_list` are set via ORM attribute assignment.

**How it works:**
1. Resolves DynamoDB table name and S3 bucket from SSM Parameter Store (or CLI overrides)
2. Queries DynamoDB `DateIndex` GSI day-by-day from `--since` date to today (handles pagination)
3. For each item, checks if URL already exists in local PostgreSQL (duplicate detection via `WebDocument.get_by_url()`)
4. For `webpage` type items with `uuid`: fetches `{uuid}.txt` and `{uuid}.html` from S3 into memory
5. Inserts new documents via ORM: `WebDocument(url=url)` → set attributes → `session.add(doc)` + `session.commit()`
6. After insert, saves S3 content to cache as `{CACHE_DIR}/{doc.id}/{doc.id}.html` (same convention as `document_prepare.py`, so downstream tools can reuse cached files without re-downloading from S3)
7. Sets `document_state` to `DOCUMENT_INTO_DATABASE` (with S3 content) or `URL_ADDED` (without)

**DynamoDB → PostgreSQL field mapping:**
- `url` → `url`, `type` → `document_type`, `title` → `title`, `language` → `language`
- `source` → `source` (default "own"), `note` → `note`, `paywall` → `paywall`
- `chapter_list` → `chapter_list`, `s3_uuid` → `uuid` (backward-compat: reads both `uuid` and `s3_uuid` from DynamoDB), `created_at` → `created_at`
- S3 `{uuid}.txt` → `text`, S3 `{uuid}.html` → `text_raw`

**Running:**
```bash
cd backend
./imports/dynamodb_sync.py                                  # auto-detect --since from last successful run
./imports/dynamodb_sync.py --since 2026-02-20               # explicit date
./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
./imports/dynamodb_sync.py --since 2026-02-20 --limit 10
./imports/dynamodb_sync.py --since 2026-02-20 --skip-s3
./imports/dynamodb_sync.py --since 2026-02-20 --env dev --project lenie
```

**Arguments:**
- `--since YYYY-MM-DD` (optional) — sync from this date. If omitted, auto-detected from last successful run in `import_logs`
- `--dry-run` — preview only, no DB writes or S3 downloads
- `--limit N` — max documents to sync (for testing)
- `--skip-s3` — metadata only, skip S3 file downloads
- `--project CODE` — project code for SSM path (default: `lenie`)
- `--env ENV` — environment for SSM path (default: `dev`)
- `--table TABLE` — DynamoDB table name override (skips SSM lookup)
- `--bucket BUCKET` — S3 bucket name override (skips SSM lookup)
- `--data-dir PATH` — cache dir for S3 files (default: `os.path.join(CACHE_DIR, 'markdown')`)
- `-y`, `--yes` — skip confirmation prompt (for automation)

Before executing any operations, the script displays source (AWS profile, region) and target (PostgreSQL host/db/port/user) information, then asks for confirmation (`Continue? [y/N]`). Use `-y` to skip the prompt.

**SSM parameters used:**
- `/{project}/{env}/dynamodb/documents/name` — DynamoDB table name
- `/{project}/{env}/s3/website-content/name` — S3 bucket for webpage content

**Prerequisites:**
- PostgreSQL database must be accessible (local Docker on port 5433)
- `.env` file with `POSTGRESQL_*` variables
- AWS credentials (via env vars or AWS profile) with SSM read, DynamoDB read, and S3 read access

### `unknown_news_import.py`

Imports curated technology/science links from [unknow.news](https://unknow.news/) — a Polish newsletter aggregating interesting articles.

**Data access: ORM (SQLAlchemy)** (not via REST API). Uses `WebDocument` ORM model and `WebsitesDBPostgreSQL(session=session)` for database access. Requires direct PostgreSQL connectivity and the same `POSTGRESQL_*` environment variables as the backend.

**How it works:**
1. Downloads `archiwum.json` from `https://unknow.news/archiwum.json` (full archive of curated links)
2. Saves it locally to `tmp/archiwum.json` as a cache
3. Determines the date cutoff: uses `--since` if provided, otherwise queries the database for the most recent entry (`get_last_unknown_news()`). If DB returns None (empty), imports all entries.
4. Iterates through the JSON entries, skipping:
   - Entries older than the last imported date (already processed)
   - Paid/affiliate links (`uw7.org/un` URLs)
   - Sponsored entries (title matching "sponsorowane")
5. For each new URL:
   - In `--dry-run` mode: prints what would be added without DB writes
   - Checks if it already exists in the database (by URL lookup via `WebDocument.get_by_url()`)
   - If it exists: corrects missing `date_from` field if needed
   - If it's new: creates a document with type `link` (or `youtube` for YouTube URLs), language `pl`, source `https://unknow.news/`
6. Stops after `--limit` documents are added (if specified)

**Imported document fields:**
- `url` — link URL
- `title` — article title
- `summary` — short description (`info` field from JSON)
- `language` — always `pl` (Polish)
- `document_type` — `StalkerDocumentType.link`
- `document_state` — `StalkerDocumentStatus.READY_FOR_EMBEDDING` (link) or `StalkerDocumentStatus.URL_ADDED` (youtube)
- `source` — `https://unknow.news/`
- `date_from` — publication date from the feed

**Running:**
```bash
cd backend
./imports/unknown_news_import.py
./imports/unknown_news_import.py --since 2026-02-01
./imports/unknown_news_import.py --since 2026-02-01 --dry-run
./imports/unknown_news_import.py --since 2026-02-01 --dry-run --limit 5
```

**Arguments:**
- `--since YYYY-MM-DD` — import entries from this date onward (overrides auto-detection from DB)
- `--dry-run` — preview only, no DB writes
- `--limit N` — max documents to add (0 = unlimited, default)

**Prerequisites:**
- PostgreSQL database must be accessible (unless using `--since` with `--dry-run`)
- `.env` file with `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`
- `tmp/` directory must exist (for caching the downloaded JSON)
- Network access to `https://unknow.news/`

### `youtube_add.py`

Ad-hoc CLI tool for processing a single YouTube video: adds it to the database, fetches metadata (title, language), downloads captions or transcription, and optionally generates an AI summary.

**Data access: ORM (SQLAlchemy)** via `process_youtube_url()` from `library.youtube_processing`.

**How it works:**
1. Optionally authenticates Webshare proxy (checks bandwidth, disables if exhausted)
2. Calls `process_youtube_url()` with the provided URL and options
3. Prints a summary (ID, title, URL, language, state, text length, elapsed time)

**Running:**
```bash
cd backend
python imports/youtube_add.py <URL>
python imports/youtube_add.py <URL> --language pl --note "..." --source own
python imports/youtube_add.py <URL> --summary --force
python imports/youtube_add.py <URL> --chapters-file chapters.txt -v
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
- `-v`, `--verbose` — enable debug logging

**Prerequisites:**
- `.env` file with `POSTGRESQL_*` variables and LLM API keys
- Optional: `WEBSHARE_API_KEY` for proxy support

### `email_import.py`

Ad-hoc CLI tool for importing a Gmail email into Lenie. Uses the `gws` CLI (Google Workspace CLI) to fetch the email, extracts links from the body, and stores the document in the database.

**Data access: ORM (SQLAlchemy)** — direct DB writes via `WebDocument` model.

**Prerequisite:** `gws` CLI must be installed and authenticated:
```bash
npm install -g @googleworkspace/cli
gws auth setup
```

**Running:**
```bash
cd backend
python imports/email_import.py --search "subject:AI Flash #78"
python imports/email_import.py --id 19ce7076beeaf054
python imports/email_import.py --id 19ce7076beeaf054 --source "newsletter:AI Flash" --note "AI news digest"
python imports/email_import.py --search "from:campus@campusai.pl" --list
python imports/email_import.py --id 19ce7076beeaf054 --dry-run
```

**Arguments:**
- `--id ID` — Gmail message ID to import
- `--search QUERY` — Gmail search query to find messages
- `--list` — list matching messages without importing
- `--source TEXT` — source identifier for the imported document
- `--note TEXT` — note to attach to the document
- `--dry-run` — preview only, no DB writes

## Architecture Notes

- All scripts bypass the REST API intentionally — they are meant for local or scheduled operations, not the web interface.
- Scripts use ORM models (`WebDocument` from `library.db.models`) with `get_session()` from `library.db.engine`. Session lifecycle: `session = get_session()` → `try` → `session.commit()` → `finally` → `session.close()`.
- Duplicate detection uses `WebDocument.get_by_url(session, url)` — returns existing document or `None`.
- `unknown_news_import.py` creates link documents with `READY_FOR_EMBEDDING` status and YouTube documents with `URL_ADDED` status.
