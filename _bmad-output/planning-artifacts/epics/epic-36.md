## Epic 36: Lenie Read Tools — Article Discovery & Retrieval

Developer can use Claude on mobile to discover unreviewed articles, retrieve full article content, and search the knowledge base — all through the MCP server connecting to the existing Lenie PostgreSQL database.

**Stories:** 36-1, 36-2, 36-3

Implementation notes:
- All three stories are independent and can be implemented in any order
- All tools are read-only — no database writes in this epic
- Stories reuse `DocumentService` and `SearchService` from the backend library where available
- Error codes match the PRD error contract: `article_not_found`, `database_unavailable`

### Story 36.1: lenie_unreviewed_articles Tool

As a **user on mobile**,
I want to ask Claude to show me my unreviewed articles,
so that I can decide which one to read and process during a short mobile session.

**Acceptance Criteria:**

**Given** the MCP server is running and connected to PostgreSQL
**When** `lenie_unreviewed_articles` is invoked with no parameters
**Then** it returns a list of up to 6 articles (newest first) where `reviewed_at IS NULL` OR `obsidian_note_paths = '[]'`, each containing:
- `id` (integer — Lenie document ID)
- `title` (string)
- `source` (URL string)
- `size_kb` (integer — content size in kilobytes)
- `user_note` (string, nullable — the user's personal annotation)
- `added_at` (ISO 8601 date string)
- `total_unreviewed` (integer — total count of unreviewed articles across all pages)

**Given** the tool is invoked with `limit=3`
**When** the result is returned
**Then** the list contains at most 3 articles (not 6)

**Given** the tool is invoked with `source_filter="bbc.com"`
**When** the result is returned
**Then** only articles whose `source` URL contains `bbc.com` are returned

**Given** the tool is invoked with `type_filter="webpage"` (or `"youtube"`, `"link"`)
**When** the result is returned
**Then** only articles of the given `document_type` are returned

**Given** there are more than 6 unreviewed articles
**When** the tool is invoked with `offset=6`
**Then** articles 7–12 are returned (pagination support)

**Given** PostgreSQL is unavailable
**When** `lenie_unreviewed_articles` is invoked
**Then** it returns error `{"error": "database_unavailable", "message": "Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają."}`

**Given** there are no unreviewed articles
**When** the tool is invoked
**Then** it returns an empty list with `total_unreviewed: 0`

**Performance requirement:** Response within 2 seconds for default limit of 6 (NFR2).

**Technical notes:**
- Query: `WHERE (reviewed_at IS NULL OR obsidian_note_paths = '[]') ORDER BY created_at DESC LIMIT :limit OFFSET :offset`
- `total_unreviewed` uses a separate `COUNT(*)` query with the same filter (no OFFSET)
- Tool parameters: `limit: int = 6`, `offset: int = 0`, `source_filter: str | None = None`, `type_filter: str | None = None`
- Reuse `get_session()` from `lenie_mcp.db`

### Story 36.2: lenie_get_article Tool

As a **user on mobile**,
I want to ask Claude to retrieve the full content of a specific article from Lenie,
so that I can read it and decide how to incorporate it into my Obsidian notes.

**Acceptance Criteria:**

**Given** an article with ID `article_id` exists in the database
**When** `lenie_get_article(article_id=<id>)` is invoked
**Then** it returns the full article including:
- `id`, `title`, `source`, `size_kb`
- `content` (full markdown text — may be large)
- `language` (e.g. `"pl"`, `"en"`)
- `user_note` (nullable)
- `document_type` (e.g. `"webpage"`, `"youtube"`, `"link"`)
- `added_at` (ISO 8601)
- `reviewed_at` (ISO 8601 or `null`)
- `obsidian_note_paths` (array of strings, may be empty)

**Given** the article ID does not exist
**When** `lenie_get_article` is invoked
**Then** it returns error `{"error": "article_not_found", "message": "Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty."}`

**Given** PostgreSQL is unavailable
**When** `lenie_get_article` is invoked
**Then** it returns error `{"error": "database_unavailable", "message": "Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają."}`

**Given** an article with very large content (>100 KB) is requested
**When** the tool returns
**Then** full content is returned without truncation (MCP handles streaming)

**Performance requirement:** Response within 5 seconds (NFR1).

**Technical notes:**
- Tool parameter: `article_id: int` (integer PK from `web_documents.id`)
- `content` field maps to `doc.text` (the `text` column in `web_documents`) — not `text_content`
- `size_kb` is computed as `len(doc.text.encode()) // 1024` if not stored separately

### Story 36.3: lenie_search Tool

As a **user on mobile**,
I want to search my Lenie knowledge base by keyword or phrase,
so that I can find articles related to a topic I'm currently thinking about.

**Acceptance Criteria:**

**Given** a search query `"sanctions Turkey"`
**When** `lenie_search(query="sanctions Turkey")` is invoked
**Then** it returns up to 10 results (default limit) ordered by relevance, each containing:
- `id`, `title`, `source`, `size_kb`
- `snippet` (string — text excerpt showing where the match occurs, with surrounding context)
- `score` (float — relevance ordering, higher = more relevant)

**Given** `lenie_search(query="foo", limit=5)` is invoked
**When** the result is returned
**Then** at most 5 results are returned

**Given** no articles match the query
**When** `lenie_search` is invoked
**Then** it returns an empty list (not an error)

**Given** PostgreSQL is unavailable
**When** `lenie_search` is invoked
**Then** it returns error `{"error": "database_unavailable", "message": "Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają."}`

**Performance requirement:** Response within 5 seconds (NFR1).

**Technical notes:**
- Search implementation: PostgreSQL full-text search using `to_tsvector` + `to_tsquery` on `title` and `text_content` columns
- Snippet generation: `ts_headline()` PostgreSQL function for excerpt with match highlighting
- `score`: `ts_rank()` value from PostgreSQL
- Tool parameters: `query: str`, `limit: int = 10`
- This is keyword/phrase search — vector semantic search is a post-MVP feature (Phase 2)
- Fallback: if full-text search is not available, use `ILIKE '%query%'` on title + content
