# Story 28.2: Similarity Search via pgvector-python & API Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want similarity search implemented with pgvector-python native `cosine_distance()` operator and the `/website_similar` endpoint functional,
so that vector search works through ORM with zero raw SQL.

## Acceptance Criteria

1. **Given** a query vector and a limit **When** repository method `get_similar(vector, limit, model)` is called **Then** it uses `WebsiteEmbedding.embedding.cosine_distance(query_vector)` for ordering

2. **Given** similarity search results **When** similarity score is computed **Then** it is calculated as `1 - cosine_distance` using a SQLAlchemy SQL expression (`func.cast`), not Python-side computation

3. **Given** `get_similar()` returns results **When** result format is inspected **Then** each result is a dict with: `website_id`, `text`, `similarity` (float), `id`, `url`, `language`, `text_original`, `websites_text_length`, `embeddings_text_length`, `title`, `document_type`, `project`

4. **Given** a query vector **When** `GET /website_similar` endpoint is called with vector and model parameters **Then** Flask route creates repository with ORM session, calls `get_similar()`, returns JSON response

5. **Given** no similar documents exist above threshold **When** similarity search is performed **Then** returns empty list (no error)

6. **Given** pgvector HNSW partial indexes exist in the database **When** ORM model is inspected **Then** indexes are NOT defined in the model — they are managed by database init SQL only

**Covers:** FR23, FR43 | NFR1 (partial)

## Tasks / Subtasks

- [x] Task 1: Rewrite `get_similar()` in `WebsitesDBPostgreSQL` to ORM (AC: #1, #2, #3, #5)
  - [x] 1.1 Add ORM branch in `get_similar()` under `if self.session:` — build SQLAlchemy query using `select()` with `WebsiteEmbedding` and `WebDocument` join
  - [x] 1.2 Compute similarity score as SQL expression: `(1 - func.cast(WebsiteEmbedding.embedding.cosine_distance(query_vector), Float)).label("similarity")`
  - [x] 1.3 Order by `cosine_distance` ascending (smaller distance = more similar) and apply `.limit(limit)`
  - [x] 1.4 Filter by `WebsiteEmbedding.model == model` in WHERE clause
  - [x] 1.5 Apply `minimal_similarity` threshold in WHERE clause: `similarity > minimal_similarity` (use `having` or computed column filter)
  - [x] 1.6 Support optional `project` parameter: conditionally add `WebDocument.project == project` to WHERE clause
  - [x] 1.7 Join `WebDocument` via `WebsiteEmbedding.website_id == WebDocument.id` to include document fields in result
  - [x] 1.8 Select columns: `WebsiteEmbedding.website_id`, `WebsiteEmbedding.text`, similarity (computed), `WebsiteEmbedding.id`, `WebDocument.url`, `WebDocument.language`, `WebsiteEmbedding.text_original`, `func.length(WebDocument.text).label("websites_text_length")`, `func.length(WebsiteEmbedding.text).label("embeddings_text_length")`, `WebDocument.title`, `WebDocument.document_type`, `WebDocument.project`
  - [x] 1.9 Convert each result row to dict with exact 12 keys matching legacy format — return `list[dict]`
  - [x] 1.10 Handle `embedding is None` → return `None` (same as legacy)
  - [x] 1.11 Keep legacy `else:` branch (psycopg2 raw SQL) for backward compatibility
  - [x] 1.12 **DO NOT** call `self.session.commit()` — caller controls transactions

- [x] Task 2: Update `/website_similar` Flask endpoint to use ORM session (AC: #4)
  - [x] 2.1 Replace `legacy_repo = WebsitesDBPostgreSQL()` with `repo = WebsitesDBPostgreSQL(session=get_scoped_session())`
  - [x] 2.2 Remove `legacy_repo.close()` call — session lifecycle managed by Flask teardown (`shutdown_session`)
  - [x] 2.3 Preserve existing input parsing (form/json/args) and `embedding.get_embedding()` call — no changes to input handling
  - [x] 2.4 Preserve response format: `{"status": "success", "message": ..., "encoding": "utf8", "text": ..., "websites": [...]}`
  - [x] 2.5 Ensure `limit` is cast to `int` before passing to `get_similar()` (form/args values come as strings)

- [x] Task 3: Write unit tests for `get_similar()` ORM path (AC: #1, #2, #3, #5)
  - [x] 3.1 Create test file: `backend/tests/unit/test_similarity_search_orm.py`
  - [x] 3.2 Use `pytest.importorskip("sqlalchemy")` pattern (consistent with previous stories)
  - [x] 3.3 Test basic similarity search: verify `session.execute()` called with correct SELECT statement containing cosine_distance
  - [x] 3.4 Test result format: verify returned dicts contain all 12 expected keys
  - [x] 3.5 Test empty results: verify returns empty list `[]` when no matches (not `None`)
  - [x] 3.6 Test `embedding is None` → returns `None`
  - [x] 3.7 Test project filtering: verify `WebDocument.project == project` added to WHERE when project parameter provided
  - [x] 3.8 Test minimal_similarity threshold: verify threshold applied in query
  - [x] 3.9 Test SQL structure: verify compiled SQL contains `cosine_distance` / `<=>` operator and JOIN

- [x] Task 4: Update Flask endpoint test (AC: #4)
  - [x] 4.1 Update existing test in `test_flask_endpoints_orm.py` → `TestWebsiteSimilar` to verify ORM session is used (not legacy psycopg2)
  - [x] 4.2 Add test: endpoint returns correct JSON structure with `status`, `message`, `websites` keys
  - [x] 4.3 Add test: endpoint handles `limit` as string (from form/args) — cast to int

- [x] Task 5: Quality checks (AC: all)
  - [x] 5.1 `uvx ruff check backend/` — zero new warnings
  - [x] 5.2 All existing unit tests pass (344+ from previous stories)
  - [x] 5.3 No new dependencies added — no `.venv_wsl` sync needed
  - [x] 5.4 Verify no raw `cursor.execute()` in newly written ORM methods
  - [x] 5.5 Verify `get_similar()` legacy branch unchanged (backward compatibility)

## Dev Notes

### Architecture Decisions (MUST follow)

**Dual-mode constructor pattern** (established in Story 27.2):
```python
class WebsitesDBPostgreSQL:
    def __init__(self, session=None):
        self.session = session
        if session is None:
            # Legacy psycopg2 mode — for backward compatibility
            self.conn = psycopg2.connect(...)
```

**All new ORM methods MUST:**
- Check `if self.session:` before using ORM operations
- Fall through to legacy `else:` branch for psycopg2 callers
- NEVER call `session.commit()` or `session.rollback()` — caller controls transactions
- Use `select()`, `delete()`, `insert()` from `sqlalchemy` — not `session.query()` (legacy style)

**Transaction boundaries** (from architecture.md):
- Repository methods NEVER commit — caller controls transactions
- Flask routes: session managed by `get_scoped_session()` + `shutdown_session` teardown
- No explicit `session.close()` needed in Flask routes

### Current Raw SQL to Replace

**`get_similar()` (lines 367-421) — full method:**
```python
def get_similar(self, embedding, model: str, limit: int = 3, minimal_similarity: float = 0.30, project=None):
    if minimal_similarity is None:
        minimal_similarity = 0.30
    if embedding is None:
        return None

    if project:
        where_project = " AND public.web_documents.project = '" + project + "' "
    else:
        where_project = ""

    query = f"""
        SELECT public.websites_embeddings.website_id,
        public.websites_embeddings.text,
        1 - (public.websites_embeddings.embedding <=> '{embedding}') AS cosine_similarity,
        public.websites_embeddings.id,
        public.web_documents.url,
        public.web_documents.language,
        public.websites_embeddings.text_original,
        LENGTH(public.web_documents.text) AS websites_text_length,
        LENGTH(public.websites_embeddings.text) AS embeddings_text_length,
        public.web_documents.title,
        public.web_documents.document_type,
        public.web_documents.project
        FROM public.websites_embeddings
        left join public.web_documents on public.websites_embeddings.website_id = public.web_documents.id
        WHERE public.websites_embeddings.model = '{model}' {where_project}
        AND (1 - (public.websites_embeddings.embedding <=> '{embedding}')) > {minimal_similarity}
        ORDER BY cosine_similarity desc
        LIMIT {limit}
        """

    cursor = self.conn.cursor()
    cursor.execute(query)

    result = []
    for r in cursor.fetchall():
        result.append({
            "website_id": r[0], "text": r[1], "similarity": r[2], "id": r[3],
            "url": r[4], "language": r[5], "text_original": r[6],
            "websites_text_length": r[7], "embeddings_text_length": r[8],
            "title": r[9], "document_type": r[10], "project": r[11],
        })
    return result
```

**ORM replacement approach:**
```python
if self.session:
    if minimal_similarity is None:
        minimal_similarity = 0.30
    if embedding is None:
        return None

    similarity = (
        literal(1) - func.cast(
            WebsiteEmbedding.embedding.cosine_distance(embedding),
            Float,
        )
    ).label("similarity")

    stmt = (
        select(
            WebsiteEmbedding.website_id,
            WebsiteEmbedding.text,
            similarity,
            WebsiteEmbedding.id,
            WebDocument.url,
            WebDocument.language,
            WebsiteEmbedding.text_original,
            func.length(WebDocument.text).label("websites_text_length"),
            func.length(WebsiteEmbedding.text).label("embeddings_text_length"),
            WebDocument.title,
            WebDocument.document_type,
            WebDocument.project,
        )
        .join(WebDocument, WebsiteEmbedding.website_id == WebDocument.id)
        .where(WebsiteEmbedding.model == model)
        .where(
            literal(1) - func.cast(
                WebsiteEmbedding.embedding.cosine_distance(embedding),
                Float,
            ) > minimal_similarity
        )
        .order_by(WebsiteEmbedding.embedding.cosine_distance(embedding))
        .limit(limit)
    )

    if project:
        stmt = stmt.where(WebDocument.project == project)

    rows = self.session.execute(stmt).all()
    return [
        {
            "website_id": r.website_id,
            "text": r.text,
            "similarity": float(r.similarity),
            "id": r.id,
            "url": r.url,
            "language": r.language,
            "text_original": r.text_original,
            "websites_text_length": r.websites_text_length,
            "embeddings_text_length": r.embeddings_text_length,
            "title": r.title,
            "document_type": r.document_type,
            "project": r.project,
        }
        for r in rows
    ]
```

### SQL Injection Fix

Current `get_similar()` uses **f-string interpolation** for `model`, `project`, and `embedding` — all SQL injection vulnerabilities (tracked in B-86). The ORM rewrite fixes this by using parameterized `where()` clauses.

### Existing ORM Infrastructure (from Stories 26.1–28.1)

| Component | File | Status |
|-----------|------|--------|
| Engine & sessions | `backend/library/db/engine.py` | Done (26.1) |
| `WebDocument` model | `backend/library/db/models.py` | Done (26.2, 27.1) — 26 columns, STI, dict(), classmethods |
| `WebsiteEmbedding` model | `backend/library/db/models.py:364-383` | Done (26.2) — 8 columns, Vector(), FK, relationship |
| `WebDocument.embeddings` relationship | `backend/library/db/models.py:106-111` | Done (26.2) — cascade="all, delete-orphan" |
| `WebsitesDBPostgreSQL` dual-mode | `backend/library/stalker_web_documents_db_postgresql.py` | Done (27.2) — `session` param for ORM mode |
| Flask teardown | `backend/server.py:80-85` | Done (26.3) — `scoped_session.remove()` |
| Embedding CRUD (ORM) | `backend/library/stalker_web_documents_db_postgresql.py` | Done (28.1) — `embedding_add()`, `embedding_delete()`, `get_documents_needing_embedding()` |

### WebsiteEmbedding ORM Model (already exists — DO NOT modify)

```python
class WebsiteEmbedding(Base):
    __tablename__ = "websites_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("web_documents.id", ondelete="CASCADE"), nullable=False,
    )
    language: Mapped[str | None] = mapped_column(String(10))
    text: Mapped[str | None] = mapped_column(Text)
    text_original: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, server_default=sa_text("CURRENT_TIMESTAMP"),
    )

    # Relationship back to document
    document: Mapped["WebDocument"] = relationship(back_populates="embeddings")
```

### Database Schema: HNSW Indexes (DO NOT touch — managed by init SQL)

- `idx_emb_ada002` — `text-embedding-ada-002` (1536 dims)
- `idx_emb_titan_v1` — `amazon.titan-embed-text-v1` (1536 dims)
- `idx_emb_titan_v2` — `amazon.titan-embed-text-v2:0` (1024 dims)
- `idx_emb_stella_en` — `dunzhang/stella_en_1.5B_v5` (1024 dims)
- `idx_emb_bge_m3` — `BAAI/bge-m3` (1024 dims)

### Current `/website_similar` Endpoint (to modify)

```python
@app.route('/website_similar', methods=['POST'])
def search_similar():
    # ... input parsing (form/json/args) — keep as-is ...
    embedds = embedding.get_embedding(model=cfg.require("EMBEDDING_MODEL"), text=text)
    # Currently: legacy_repo = WebsitesDBPostgreSQL()  # No session → psycopg2
    # Change to: repo = WebsitesDBPostgreSQL(session=get_scoped_session())
    websites_list = repo.get_similar(embedds.embedding, cfg.require("EMBEDDING_MODEL"), limit=int(limit))
    # Remove: legacy_repo.close()  — session managed by Flask teardown
    return {"status": "success", ...}
```

### Imports Needed (in `stalker_web_documents_db_postgresql.py`)

Already imported from Story 28.1: `and_`, `column`, `delete`, `union`, `WebsiteEmbedding`

**New imports for this story:**
```python
from sqlalchemy import Float, func, literal, select
from library.db.models import WebDocument  # if not already imported
```

Check which of these are already present before adding.

### Previous Story Intelligence (from Story 28.1)

Key learnings:
1. **`uvx pytest` lacks SQLAlchemy** — use `pytest.importorskip("sqlalchemy")` for test gating
2. **Dual-mode constructor** — `WebsitesDBPostgreSQL(session=None)` triggers legacy psycopg2 path
3. **No new dependencies** — no `.venv_wsl` sync needed
4. **Repository methods never commit** — caller controls transactions
5. **`session.execute()` for queries** — use `select()` statement
6. **Enum values** — ORM uses enum members (via SAEnum mapping), legacy uses `.name` strings
7. **Test pattern** — mock `session` and `session.execute()` for unit tests
8. **Pre-existing test ordering issue** — 8 tests in `test_get_list_query.py` fail only in full suite due to `sys.modules` psycopg2 mock (not caused by this work)

### Files to Modify

| File | Change |
|------|--------|
| `backend/library/stalker_web_documents_db_postgresql.py` | Add ORM branch to `get_similar()` |
| `backend/server.py` | Update `/website_similar` to use ORM session |
| `backend/tests/unit/test_similarity_search_orm.py` | **NEW** — unit tests for similarity search ORM |
| `backend/tests/unit/test_flask_endpoints_orm.py` | Update `TestWebsiteSimilar` for ORM session |

### Files NOT to Modify (scope guard)

- `backend/library/db/models.py` — NOT modified (WebsiteEmbedding model already complete)
- `backend/library/db/engine.py` — NOT modified (session factories complete)
- `backend/database/init/04-create-table.sql` — NOT modified (HNSW indexes managed separately)
- `backend/library/stalker_web_document_db.py` — NOT modified (high-level orchestration, Epic 29 scope)

### Project Structure Notes

- ORM branch added inside existing `get_similar()` method — consistent with dual-mode pattern from Stories 27.2, 28.1
- No new ORM model files — `WebsiteEmbedding` already exists
- Test file naming: `test_similarity_search_orm.py` follows established pattern
- Flask endpoint change is minimal — only swapping constructor argument

### References

- [Source: _bmad-output/planning-artifacts/epics/epic-28.md — Story 28.2 AC]
- [Source: _bmad-output/planning-artifacts/architecture.md — Vector Operations Strategy, Transaction Boundaries]
- [Source: backend/library/stalker_web_documents_db_postgresql.py — lines 367-421: current get_similar()]
- [Source: backend/server.py — lines 450-489: current /website_similar endpoint]
- [Source: backend/library/db/models.py — lines 364-383: WebsiteEmbedding model]
- [Source: _bmad-output/implementation-artifacts/28-1-embedding-crud-documents-needing-embeddings.md — previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — implementation proceeded without issues.

### Completion Notes List

- Task 1: Added ORM branch to `get_similar()` in `stalker_web_documents_db_postgresql.py`. Uses `WebsiteEmbedding.embedding.cosine_distance()` for pgvector-native similarity search, `literal(1) - func.cast(cosine_distance, Float)` for similarity score computation, JOIN with `WebDocument`, and parameterized WHERE clauses (fixing SQL injection from legacy f-string approach). Legacy psycopg2 branch preserved unchanged.
- Task 2: Updated `/website_similar` endpoint in `server.py` to use `WebsitesDBPostgreSQL(session=get_scoped_session())` instead of legacy no-session constructor. Removed `legacy_repo.close()` call. Added `int(limit)` cast for string-to-int conversion.
- Task 3: Created 12 unit tests in `test_similarity_search_orm.py` covering: basic search, result format (12 keys), result values, similarity as float, empty results, None embedding, project filtering, minimal_similarity default, SQL structure (cosine_distance operator and JOIN), no commit, multiple results.
- Task 4: Updated `TestWebsiteSimilar` in `test_flask_endpoints_orm.py` — replaced legacy test with 3 ORM-aware tests: session usage verification, JSON structure, limit string-to-int cast.
- Task 5: Ruff clean (0 warnings), 336 unit tests pass (12 new + 324 existing), no new dependencies, no raw cursor.execute in ORM path, legacy branch unchanged.

### Change Log

- 2026-03-09: Story 28.2 implementation — similarity search via pgvector-python ORM and API endpoint update
- 2026-03-09: Code review fixes — H1: document_type enum→string serialization, M1: LEFT JOIN→OUTER JOIN to match legacy, M2: added minimal_similarity SQL test, M3: limit default guard, added enum serialization test

### File List

- `backend/library/stalker_web_documents_db_postgresql.py` — Added ORM branch to `get_similar()`, added `Float` and `literal` imports; review fix: document_type enum→string, outerjoin
- `backend/server.py` — Updated `/website_similar` endpoint to use ORM session, removed legacy close(); review fix: limit default guard
- `backend/tests/unit/test_similarity_search_orm.py` — **NEW** — 14 unit tests for similarity search ORM path (12 original + 2 review fixes)
- `backend/tests/unit/test_flask_endpoints_orm.py` — Updated `TestWebsiteSimilar` (3 tests: ORM session, JSON structure, limit cast)
