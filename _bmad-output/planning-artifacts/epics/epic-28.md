## Epic 28: Vector Embeddings & Similarity Search

Developer can manage vector embeddings via ORM relationship and perform similarity search using pgvector-python native `cosine_distance()` operator — zero raw SQL for vector operations.

### Story 28.1: Embedding CRUD & Documents Needing Embeddings

As a **developer**,
I want to add, delete, and query embeddings via ORM relationship and repository,
So that embedding management no longer requires hand-written INSERT/DELETE SQL.

**Acceptance Criteria:**

**Given** a `WebDocument` instance and an embedding vector
**When** a `WebsiteEmbedding` is created and added via ORM relationship (`doc.embeddings.append(embedding)`) and `session.commit()` is called
**Then** the embedding is persisted in `websites_embeddings` table with correct `web_document_id` FK

**Given** a document with embeddings for multiple models
**When** embeddings are deleted filtered by model name via repository
**Then** only embeddings for the specified model are removed, others remain

**Given** documents exist with and without embeddings
**When** repository method `get_documents_needing_embedding(model)` is called
**Then** returns documents that have no embedding for the specified model (outer join on `websites_embeddings`)

**Given** the query uses SQLAlchemy
**When** `get_documents_needing_embedding()` is inspected
**Then** it uses `select()` with `outerjoin()` — no raw `cursor.execute()`

**Covers:** FR20, FR21, FR22

### Story 28.2: Similarity Search via pgvector-python & API Endpoint

As a **developer**,
I want similarity search implemented with pgvector-python native `cosine_distance()` operator and the `/website_similar` endpoint functional,
So that vector search works through ORM with zero raw SQL.

**Acceptance Criteria:**

**Given** a query vector and a limit
**When** repository method `get_similar(vector, limit, model)` is called
**Then** it uses `WebsiteEmbedding.embedding.cosine_distance(query_vector)` for ordering

**Given** similarity search results
**When** similarity score is computed
**Then** it is calculated as `1 - cosine_distance` using a SQLAlchemy SQL expression (`func.cast`), not Python-side computation

**Given** `get_similar()` returns results
**When** result format is inspected
**Then** each result is a dict with: `website_id`, `text`, `similarity` (float), `id`, `url`, `language`, `text_original`, `websites_text_length`, `embeddings_text_length`, `title`, `document_type`, `project`

**Given** a query vector
**When** `GET /website_similar` endpoint is called with vector and model parameters
**Then** Flask route creates repository, calls `get_similar()`, returns JSON response

**Given** no similar documents exist above threshold
**When** similarity search is performed
**Then** returns empty list (no error)

**Given** pgvector HNSW partial indexes exist in the database
**When** ORM model is inspected
**Then** indexes are NOT defined in the model — they are managed by Alembic migrations only

**Covers:** FR23, FR43 | NFR1 (partial)
