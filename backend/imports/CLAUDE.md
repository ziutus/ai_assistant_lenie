# Backend Imports — CLAUDE.md

Standalone import scripts for bulk-loading documents from external sources into the Lenie database.

## Directory Structure

```
imports/
└── unknown_news_import.py   # Import curated links from unknow.news
```

## Scripts

### `unknown_news_import.py`

Imports curated technology/science links from [unknow.news](https://unknow.news/) — a Polish newsletter aggregating interesting articles.

**Data access: Direct database connection** (not via REST API). Uses `StalkerWebDocumentDB` and `WebsitesDBPostgreSQL` with `psycopg2` — the same DB layer as the Flask backend. This means the script requires direct PostgreSQL connectivity and the same `POSTGRESQL_*` environment variables as the backend.

**How it works:**
1. Downloads `archiwum.json` from `https://unknow.news/archiwum.json` (full archive of curated links)
2. Saves it locally to `tmp/archiwum.json` as a cache
3. Queries the database for the most recent entry from this source (`get_last_unknown_news()`)
4. Iterates through the JSON entries, skipping:
   - Entries older than the last imported date (already processed)
   - Paid/affiliate links (`uw7.org/un` URLs)
   - Sponsored entries (title matching "sponsorowane")
5. For each new URL:
   - Checks if it already exists in the database (by URL lookup via `StalkerWebDocumentDB`)
   - If it exists: corrects missing `date_from` field if needed
   - If it's new: creates a document with status `READY_FOR_TRANSLATION`, type `link`, language `pl`, source `https://unknow.news/`

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
python -m imports.unknown_news_import
# or:
python imports/unknown_news_import.py
```

**Prerequisites:**
- PostgreSQL database must be accessible
- `.env` file with `POSTGRESQL_HOST`, `POSTGRESQL_DATABASE`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_PORT`
- `tmp/` directory must exist (for caching the downloaded JSON)
- Network access to `https://unknow.news/`

## Architecture Notes

- These scripts bypass the REST API intentionally — they are meant for batch import operations run locally or as scheduled jobs, not through the web interface.
- Documents are created with `READY_FOR_TRANSLATION` status, meaning they enter the processing pipeline at the translation step (since the source content is in Polish and may need English translation for embedding).
- The `StalkerWebDocumentDB` constructor performs a URL lookup on instantiation, so creating the object also serves as a duplicate check.
