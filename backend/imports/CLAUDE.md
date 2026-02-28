# Backend Imports — CLAUDE.md

Standalone import scripts for bulk-loading documents from external sources into the Lenie database.

## Directory Structure

```
imports/
├── dynamodb_sync.py          # Sync documents from DynamoDB + S3 to local PostgreSQL
└── unknown_news_import.py    # Import curated links from unknow.news
```

## Scripts

### `dynamodb_sync.py`

Incremental sync of documents from AWS DynamoDB and S3 webpage content to the local Docker PostgreSQL. No VPN, EC2, or RDS needed — uses standard AWS API access over the internet.

**Resource discovery via SSM Parameter Store.** DynamoDB table name and S3 bucket name are resolved from SSM using the project/environment convention (`/{project}/{env}/dynamodb/documents/name`, `/{project}/{env}/s3/website-content/name`). CLI overrides (`--table`, `--bucket`) skip the SSM lookup.

**Data access: DynamoDB + S3 → Direct database connection**. Reads from DynamoDB (DateIndex GSI) and S3, writes via `StalkerWebDocumentDB.save()` with direct SQL for `created_at` and `chapter_list` preservation.

**How it works:**
1. Resolves DynamoDB table name and S3 bucket from SSM Parameter Store (or CLI overrides)
2. Queries DynamoDB `DateIndex` GSI day-by-day from `--since` date to today (handles pagination)
3. For each item, checks if URL already exists in local PostgreSQL (duplicate detection via `StalkerWebDocumentDB`)
4. For `webpage` type items with `s3_uuid`: downloads `{uuid}.txt` and `{uuid}.html` from S3, saves locally to `data/`
5. Inserts new documents via `StalkerWebDocumentDB.save()`, then preserves original `created_at` and `chapter_list` via direct SQL UPDATE
6. Sets `document_state` to `DOCUMENT_INTO_DATABASE` (with S3 content) or `URL_ADDED` (without)

**DynamoDB → PostgreSQL field mapping:**
- `url` → `url`, `type` → `document_type`, `title` → `title`, `language` → `language`
- `source` → `source` (default "own"), `note` → `note`, `paywall` → `paywall`
- `chapter_list` → `chapter_list`, `s3_uuid` → `s3_uuid`, `created_at` → `created_at`
- S3 `{uuid}.txt` → `text`, S3 `{uuid}.html` → `text_raw`

**Running:**
```bash
cd backend
./imports/dynamodb_sync.py --since 2026-02-20
./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
./imports/dynamodb_sync.py --since 2026-02-20 --limit 10
./imports/dynamodb_sync.py --since 2026-02-20 --skip-s3
./imports/dynamodb_sync.py --since 2026-02-20 --env dev --project lenie
```

**Arguments:**
- `--since YYYY-MM-DD` (required) — sync documents from this date onward
- `--dry-run` — preview only, no DB writes or S3 downloads
- `--limit N` — max documents to sync (for testing)
- `--skip-s3` — metadata only, skip S3 file downloads
- `--project CODE` — project code for SSM path (default: `lenie`)
- `--env ENV` — environment for SSM path (default: `dev`)
- `--table TABLE` — DynamoDB table name override (skips SSM lookup)
- `--bucket BUCKET` — S3 bucket name override (skips SSM lookup)
- `--data-dir PATH` — local dir for S3 files (default: `data/`)

**SSM parameters used:**
- `/{project}/{env}/dynamodb/documents/name` — DynamoDB table name
- `/{project}/{env}/s3/website-content/name` — S3 bucket for webpage content

**Prerequisites:**
- PostgreSQL database must be accessible (local Docker on port 5433)
- `.env` file with `POSTGRESQL_*` variables
- AWS credentials (via env vars or AWS profile) with SSM read, DynamoDB read, and S3 read access

### `unknown_news_import.py`

Imports curated technology/science links from [unknow.news](https://unknow.news/) — a Polish newsletter aggregating interesting articles.

**Data access: Direct database connection** (not via REST API). Uses `StalkerWebDocumentDB` and `WebsitesDBPostgreSQL` with `psycopg2` — the same DB layer as the Flask backend. This means the script requires direct PostgreSQL connectivity and the same `POSTGRESQL_*` environment variables as the backend.

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
   - Checks if it already exists in the database (by URL lookup via `StalkerWebDocumentDB`)
   - If it exists: corrects missing `date_from` field if needed
   - If it's new: creates a document with status `READY_FOR_TRANSLATION`, type `link`, language `pl`, source `https://unknow.news/`
6. Stops after `--limit` documents are added (if specified)

**Imported document fields:**
- `url` — link URL
- `title` — article title
- `summary` — short description (`info` field from JSON)
- `language` — always `pl` (Polish)
- `document_type` — `StalkerDocumentType.link`
- `document_state` — `StalkerDocumentStatus.READY_FOR_TRANSLATION`
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

## Architecture Notes

- These scripts bypass the REST API intentionally — they are meant for batch import operations run locally or as scheduled jobs, not through the web interface.
- Documents are created with `READY_FOR_TRANSLATION` status, meaning they enter the processing pipeline at the translation step (since the source content is in Polish and may need English translation for embedding).
- The `StalkerWebDocumentDB` constructor performs a URL lookup on instantiation, so creating the object also serves as a duplicate check.
