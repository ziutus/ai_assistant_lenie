## Epic 27: Document CRUD & API Serving

Developer can create, update, delete, and query documents through the ORM repository, and all Flask API endpoints (`/website_list`, `/website_get`, `/website_save`, `/website_delete`) return identical data formats as before. Old wrapper classes replaced with re-exports.

### Story 27.1: Document Persistence — CRUD via ORM

As a **developer**,
I want to create, read, update, and delete documents via ORM session operations and classmethods,
So that I no longer need manual SQL for basic document operations.

**Acceptance Criteria:**

**Given** a session and document data
**When** `WebDocument(url="https://...")` is created and `session.add(doc)` + `session.commit()` is called
**Then** the document is persisted in `web_documents` table

**Given** an existing document in the database
**When** `doc.title = "New title"` is set and `session.commit()` is called
**Then** SQLAlchemy dirty tracking generates UPDATE for the changed column only

**Given** a document with related embeddings
**When** `session.delete(doc)` + `session.commit()` is called
**Then** the document AND all related embeddings are deleted (cascade)

**Given** a URL string
**When** `WebDocument.get_by_url(session, url)` is called
**Then** returns the matching document or `None` (for duplicate detection)

**Given** a document ID
**When** `WebDocument.get_by_id(session, id)` is called
**Then** returns the matching document or `None`

**Given** a `WebDocument` instance
**When** `doc.dict()` is called
**Then** output matches exact format: dates as `"YYYY-MM-DD HH:MM:SS"`, enums as `.name`, all existing keys preserved including transient navigation fields when populated

**Covers:** FR14, FR15, FR16, FR17, FR18, FR19 | NFR5

### Story 27.2: Repository Queries — List, Count, State-Based Lookups

As a **developer**,
I want all repository query methods rewritten with SQLAlchemy `select()` queries,
So that document listing, counting, and state-based lookups work without raw SQL.

**Acceptance Criteria:**

**Given** `WebsitesDBPostgreSQL` receives session via constructor (`WebsitesDBPostgreSQL(session)`)
**When** any query method is called
**Then** it uses `session.execute(select(...))` — no raw `cursor.execute()`

**Given** repository method `get_list(document_type='link', limit=20)`
**When** called
**Then** returns list of subset dicts (id, url, title, document_type, created_at, document_state, document_state_error, note, project, s3_uuid) with dynamic filters applied

**Given** repository method `get_count(document_type='link')`
**When** called
**Then** returns integer count using `func.count()`

**Given** repository method `get_count_by_type()`
**When** called
**Then** returns dict with counts per document type

**Given** repository method `get_ready_for_download()`
**When** called
**Then** returns documents in URL_ADDED state with webpage/link type

**Given** repository method `get_youtube_just_added()`
**When** called
**Then** returns YouTube documents in URL_ADDED state

**Given** repository method `get_transcription_done()`
**When** called
**Then** returns documents with completed transcriptions

**Given** repository method `get_next_to_correct(id, document_type)`
**When** called
**Then** returns the next document for navigation

**Given** repository method `get_last_unknown_news()`
**When** called
**Then** returns the last imported date for unknow.news source

**Given** repository method `load_neighbors(doc)`
**When** called
**Then** populates `doc.next_id`, `doc.next_type`, `doc.previous_id`, `doc.previous_type` transient attributes

**Given** any repository method
**When** inspected
**Then** it NEVER calls `session.commit()` or `session.rollback()` — caller controls transactions

**Covers:** FR24, FR25, FR26, FR27, FR28, FR29, FR30

### Story 27.3: Flask API Endpoints — CRUD Routes via Repository

As a **developer**,
I want Flask route handlers updated to use the ORM repository with scoped session,
So that the React frontend receives identical API responses after the migration.

**Acceptance Criteria:**

**Given** Flask app with scoped session
**When** `GET /website_list?document_type=link&limit=20` is called
**Then** route creates `WebsitesDBPostgreSQL(scoped_session())`, calls `get_list()`, returns JSON response identical to pre-migration format

**Given** a document with ID exists
**When** `GET /website_get?id=42` is called
**Then** route returns full document dict with navigation fields (`next_id`, `next_type`, `previous_id`, `previous_type`) populated via `load_neighbors()`

**Given** valid document data in request body
**When** `POST /website_save` is called
**Then** route creates or updates document via ORM model and `session.commit()`, returns success response

**Given** a document ID
**When** `DELETE /website_delete?id=42` is called
**Then** route deletes document via `session.delete()` with cascade (embeddings removed), returns success response

**Given** any Flask endpoint completes (success or error)
**When** request teardown occurs
**Then** `scoped_session.remove()` is called via `@app.teardown_appcontext`

**Given** frontend makes API calls before and after migration
**When** response JSON is compared
**Then** field names, value types, and date formats are identical

**Covers:** FR39, FR40, FR41, FR42 | NFR1 (partial)
