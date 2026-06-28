## Epic 37: Lenie Write Tools — Article Deletion & Obsidian Note Linking

Developer can delete articles from the Lenie database via MCP, and the `obsidian_write_note` tool (Epic 38) can automatically associate Obsidian note paths with the source article and mark it as reviewed — completing the article lifecycle management.

**Stories:** 37-1, 37-2

Implementation notes:
- Story 37-1 (lenie_delete_article) is independent and can be done first
- Story 37-2 (article-note linking logic) is a prerequisite for Epic 38's `obsidian_write_note` implementation — the linking helpers must exist before Story 38.3 uses them
- Both stories require write access to `web_documents` table

### Story 37.1: lenie_delete_article Tool

As a **user on mobile**,
I want to delete an article from Lenie when it's not interesting or relevant,
so that the unreviewed article list stays clean and reflects only content worth keeping.

**Acceptance Criteria:**

**Given** an article with ID `article_id` exists in the database
**When** `lenie_delete_article(article_id=<id>)` is invoked
**Then** the article is permanently deleted from `web_documents`
**And** any associated vector embeddings in `websites_embeddings` are also deleted (CASCADE)
**And** the tool returns `{"deleted": true, "id": <id>, "title": "<title>"}`

**Given** an article does not exist
**When** `lenie_delete_article` is invoked with its ID
**Then** it returns error `{"error": "article_not_found", "message": "Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty."}`

**Given** the delete operation is atomic
**When** the database transaction is committed
**Then** either both `web_documents` and `websites_embeddings` rows are deleted, or neither (no partial delete)

**Given** PostgreSQL is unavailable
**When** `lenie_delete_article` is invoked
**Then** it returns error `{"error": "database_unavailable", "message": "Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają."}`

**Given** the user says "delete this article" without asking for confirmation
**When** Claude invokes `lenie_delete_article`
**Then** deletion proceeds immediately — no confirmation dialog required (single-user personal project per PRD)

**Technical notes:**
- Tool parameter: `article_id: int`
- Use SQLAlchemy `session.delete(article)` — CASCADE handles `websites_embeddings`
- Return the title before deletion so Claude can confirm to the user which article was removed
- The delete is irreversible — this is by design (PRD: "Delete operations on Lenie articles do not require confirmation")

### Story 37.2: Article-Obsidian Linking Helpers (obsidian_note_paths + reviewed_at)

As a **developer**,
I want reusable helper functions that update an article's `obsidian_note_paths` and `reviewed_at` fields,
so that `obsidian_write_note` (Epic 38) can automatically link notes to source articles and mark them as reviewed without duplicating the DB logic.

**Acceptance Criteria:**

**Given** `src/lenie_mcp/tools/lenie.py` exists
**When** `append_obsidian_note_path(session, article_id, note_path)` is called
**Then** `note_path` is appended to `web_documents.obsidian_note_paths` JSONB array for `article_id`
**And** if `note_path` already exists in the array, it is NOT duplicated (idempotent)
**And** if `article_id` does not exist, the function raises `ArticleNotFoundError`

**Given** `mark_article_reviewed(session, article_id)` is called
**When** the article exists and `reviewed_at IS NULL`
**Then** `reviewed_at` is set to `NOW()` for that article

**Given** `mark_article_reviewed` is called on an article that is already reviewed (`reviewed_at` is not NULL)
**When** the function runs
**Then** `reviewed_at` is NOT overwritten — the original review timestamp is preserved

**Given** `obsidian_write_note` is called with `article_id=<id>` and `mark_as_reviewed=True`
**When** the write succeeds
**Then** `append_obsidian_note_path(session, id, note_path)` is called
**And** `mark_article_reviewed(session, id)` is called in the same transaction

**Given** a single article has notes linked from multiple Obsidian files
**When** `append_obsidian_note_path` is called multiple times with different paths
**Then** all paths accumulate in the JSONB array (no overwrite)
**Example:** `["02-wiedza/Kraje/Turcja/Polityka.md", "02-wiedza/Geopolityka/EU-sankcje.md"]`

**Technical notes:**
- JSONB append SQL: `UPDATE web_documents SET obsidian_note_paths = obsidian_note_paths || jsonb_build_array(:path) WHERE id = :id AND NOT (obsidian_note_paths @> jsonb_build_array(:path))`
- These are internal helpers (not MCP tools) — called from `obsidian_write_note` in Epic 38
- Defined in `src/lenie_mcp/tools/lenie.py` as regular functions, not FastMCP tools
- Uses the same SQLAlchemy session passed in from the calling tool
