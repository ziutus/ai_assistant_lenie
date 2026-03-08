## Epic 29: Data Pipeline Migration & Cleanup

Import scripts and batch pipeline work with ORM models and sessions. YouTube pipeline stores transcripts via ORM. Old wrapper code fully removed, all quality gates pass.

### Story 29.1: Import Scripts Migration (dynamodb_sync & unknown_news_import)

As a **developer**,
I want import scripts to use ORM models and sessions instead of the old wrapper,
So that data imports work through the same ORM layer as the rest of the application.

**Acceptance Criteria:**

**Given** `dynamodb_sync.py` is updated
**When** it processes a DynamoDB item
**Then** it creates `WebDocument(url=item['url'])` via ORM, sets attributes, and `session.commit()`

**Given** `dynamodb_sync.py` needs to set `created_at` and `chapter_list`
**When** these fields are updated
**Then** they are set via normal ORM attribute assignment (`doc.created_at = value`) — no direct SQL UPDATE

**Given** `unknown_news_import.py` is updated
**When** it processes a JSON feed entry
**Then** it creates `WebDocument` via ORM with fields: `title`, `summary`, `language`, `source`, `date_from`, `document_type`, `document_state`

**Given** `unknown_news_import.py` processes a URL that already exists
**When** `WebDocument.get_by_url(session, url)` returns a match
**Then** the duplicate is skipped (not inserted)

**Given** either import script
**When** session lifecycle is inspected
**Then** it follows the pattern: `session = get_session()` -> `try` -> `session.commit()` -> `finally` -> `session.close()`

**Given** import scripts use no raw SQL
**When** code is inspected
**Then** zero `cursor.execute()` calls remain in import scripts

**Covers:** FR31, FR32, FR33, FR34

### Story 29.2: Batch Pipeline & YouTube Processing Migration

As a **developer**,
I want `web_documents_do_the_needful_new.py` and YouTube processing to use ORM models,
So that the batch pipeline and transcript storage work through the same ORM layer.

**Acceptance Criteria:**

**Given** `web_documents_do_the_needful_new.py` is updated
**When** it processes an SQS message
**Then** it creates/retrieves `WebDocument` via ORM and `session.commit()`

**Given** batch pipeline needs to generate embeddings
**When** embeddings are created
**Then** they are stored via ORM relationship (`WebsiteEmbedding` added to document's embeddings collection)

**Given** batch pipeline processes a document through its lifecycle
**When** document state changes (e.g., `URL_ADDED` -> `DOCUMENT_INTO_DATABASE` -> `EMBEDDING_EXIST`)
**Then** state is updated via ORM attribute assignment (`doc.document_state = StalkerDocumentStatus.EMBEDDING_EXIST`) and `session.commit()`

**Given** YouTube processing pipeline receives transcript
**When** transcript text and metadata are stored
**Then** they are set via ORM attributes on `WebDocument` (not direct SQL)

**Given** batch pipeline session lifecycle
**When** inspected
**Then** uses script-scoped `get_session()` with commit per document

**Given** batch pipeline uses no raw SQL
**When** code is inspected
**Then** zero `cursor.execute()` calls remain

**Covers:** FR35, FR36, FR37, FR38

### Story 29.3: Old Code Removal & Final Verification

As a **developer**,
I want all old wrapper code removed and all quality gates verified,
So that the migration is complete with zero legacy code and a clean codebase.

**Acceptance Criteria:**

**Given** all consumers are migrated to ORM
**When** `stalker_web_document.py` is inspected
**Then** it contains only: `from library.db.models import WebDocument as StalkerWebDocument` (re-export)

**Given** all consumers are migrated
**When** `stalker_web_document_db.py` is inspected
**Then** it contains only: `from library.db.models import WebDocument as StalkerWebDocumentDB` (re-export)

**Given** old wrapper code
**When** codebase is searched for `cursor.execute()`
**Then** zero occurrences found in production code (NFR1 complete)

**Given** updated codebase
**When** `ruff check backend/` is run
**Then** zero warnings reported (line-length=120)

**Given** existing unit tests
**When** `cd backend && PYTHONPATH=. uvx pytest tests/unit/ -v` is run
**Then** all tests pass without modification

**Given** the complete migration
**When** codebase is searched for dead code from old architecture
**Then** no remnants of `StalkerWebDocumentDB` class definition, `db_conn` singleton, or `__clean_values()` method remain

**Covers:** NFR1 (complete), NFR2, NFR3, NFR9
