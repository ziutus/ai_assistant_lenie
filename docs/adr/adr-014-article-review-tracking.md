# ADR-014: Article Review Tracking — Columns Now, Join Table for Multi-User

**Date:** 2026-03-28
**Status:** Accepted
**Decision Makers:** Ziutus
**Backlog Item:** [B-101](../\_bmad-output/planning-artifacts/epics/backlog.md) — Track Obsidian Note Status for Articles

## Context

The `article_browser.py` script provides an interactive CLI for browsing documents in the Lenie database and creating knowledge notes in an Obsidian vault. Currently, there is no way to track:

1. **Which articles have been reviewed** — the user must remember or re-read articles to know if they were already processed.
2. **Which articles have Obsidian notes** — the `[o]` (obsidian) action creates notes but doesn't record this fact in the database.

This makes the review workflow inefficient: `--review` shows all articles regardless of prior review status, and there's no `--not-reviewed` or `--no-obsidian` filter.

### Options Considered

**Option A: New document processing status (e.g. `REVIEWED`, `OBSIDIAN_DONE`)**

The existing `document_state` column tracks the **technical processing pipeline**:

```
URL_ADDED → DOCUMENT_INTO_DATABASE → ... → MD_SIMPLIFIED → EMBEDDING_EXIST
```

Each state answers: "what has the **system** done with this document?" Adding a user-action state (reviewed, Obsidian note created) breaks this model because:

- **Two independent dimensions collapsed into one.** A document can have `EMBEDDING_EXIST` and be unreviewed, or be reviewed before embeddings are generated. A linear status cannot express both.
- **Review is reversible and repeatable.** The user may review an article multiple times, add multiple Obsidian notes over time. Pipeline states are monotonically advancing.
- **Multi-user breaks it entirely.** When User A reviews a document, User B hasn't. A single status column cannot represent per-user state.
- **Pipeline automation depends on `document_state`.** Batch scripts (`web_documents_do_the_needful_new.py`) use state to decide what to process next. Mixing user actions into the pipeline would require every automation script to understand and skip user-action states.

**Option B: Columns on `web_documents` (chosen for Phase 1)**

Add `reviewed_at` (TIMESTAMP) and `obsidian_note_paths` (JSONB array) directly on `web_documents`. Simple, zero new tables, covers the single-user use case. JSONB array because a single article often produces multiple Obsidian notes — e.g. a geopolitics article may yield separate notes per country and per topic (drone warfare, sanctions, diplomacy).

**Option C: Join table `user_document_reviews` (planned for Phase 9 multi-user)**

Separate table with `(user_id, document_id)` composite key. Required when multiple users each have their own review state and Obsidian vault.

## Decision

**Phase 1 (now, single-user):** Add two columns to `web_documents` via Alembic migration:

```sql
ALTER TABLE web_documents ADD COLUMN reviewed_at TIMESTAMP;
ALTER TABLE web_documents ADD COLUMN obsidian_note_paths JSONB NOT NULL DEFAULT '[]';
```

- `reviewed_at` — set when the user marks an article as reviewed (via `article_browser.py`). NULL = not reviewed.
- `obsidian_note_paths` — JSONB array of relative paths within the Obsidian vault. Empty array `[]` = no Obsidian notes. Example value:

```json
[
  "02-wiedza/Geopolityka/Sankcje-UE-2026.md",
  "02-wiedza/Wojsko/Wojna-dronowa-Ukraina.md",
  "02-wiedza/Osoby/Zelenski-wizyta-Berlin.md"
]
```

This enables:
- `--not-reviewed` filter: `WHERE reviewed_at IS NULL`
- `--no-obsidian` filter: `WHERE obsidian_note_paths = '[]'`
- Adding a note: `UPDATE web_documents SET obsidian_note_paths = obsidian_note_paths || '["path/to/note.md"]'::jsonb WHERE id = :id`
- Count notes per article: `jsonb_array_length(obsidian_note_paths)`

**Phase 9 (future, multi-user):** Migrate to a join table when user authentication (B-33) and per-user data isolation (B-34, B-35) are implemented.

## Multi-User Migration Plan

### Prerequisites

The following backlog items must be completed first:
- [B-33: AWS Cognito authentication](../\_bmad-output/implementation-artifacts/sprint-status.yaml)
- [B-34: Add `user_id` to database schema](../\_bmad-output/implementation-artifacts/sprint-status.yaml)
- [B-35: Enforce data isolation per user](../\_bmad-output/implementation-artifacts/sprint-status.yaml)

### New Table Schema

```sql
-- Review tracking: one row per user per document (1:1 review state)
CREATE TABLE user_document_reviews (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
    reviewed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    note TEXT,
    CONSTRAINT uq_user_document UNIQUE (user_id, document_id)
);

-- Obsidian notes: many rows per user per document (1:N notes)
CREATE TABLE user_obsidian_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES web_documents(id) ON DELETE CASCADE,
    obsidian_note_path TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_udr_user_id ON user_document_reviews(user_id);
CREATE INDEX idx_udr_document_id ON user_document_reviews(document_id);
CREATE INDEX idx_uon_user_document ON user_obsidian_notes(user_id, document_id);
```

Two tables instead of one because review state (1:1 per user per document) and Obsidian notes (1:N per user per document) have different cardinality. Putting them together would either require removing the UNIQUE constraint on reviews or duplicating review data across note rows.

### Data Migration (Alembic)

Single Alembic migration that:

1. Creates both tables (`user_document_reviews`, `user_obsidian_notes`).
2. Migrates review data — assigns all current reviews to user_id=1 (the original single user):

```sql
INSERT INTO user_document_reviews (user_id, document_id, reviewed_at)
SELECT 1, id, reviewed_at
FROM web_documents
WHERE reviewed_at IS NOT NULL;
```

3. Migrates Obsidian note paths — unnests the JSONB array into individual rows:

```sql
INSERT INTO user_obsidian_notes (user_id, document_id, obsidian_note_path)
SELECT 1, id, path.value #>> '{}'
FROM web_documents,
     jsonb_array_elements(obsidian_note_paths) AS path(value)
WHERE obsidian_note_paths != '[]';
```

4. Drops the columns from `web_documents`:

```sql
ALTER TABLE web_documents DROP COLUMN reviewed_at;
ALTER TABLE web_documents DROP COLUMN obsidian_note_paths;
```

### Query Changes

| Operation | Phase 1 (columns) | Phase 9 (tables) |
|-----------|-------------------|---------------------|
| Unreviewed articles | `WHERE reviewed_at IS NULL` | `LEFT JOIN user_document_reviews r ON r.document_id = d.id AND r.user_id = :uid WHERE r.id IS NULL` |
| Without Obsidian notes | `WHERE obsidian_note_paths = '[]'` | `LEFT JOIN user_obsidian_notes n ON n.document_id = d.id AND n.user_id = :uid WHERE n.id IS NULL` |
| Mark as reviewed | `UPDATE web_documents SET reviewed_at = NOW() WHERE id = :id` | `INSERT INTO user_document_reviews (user_id, document_id) VALUES (:uid, :did) ON CONFLICT (user_id, document_id) DO UPDATE SET reviewed_at = NOW()` |
| Add Obsidian note | `UPDATE web_documents SET obsidian_note_paths = obsidian_note_paths \|\| '["path"]'::jsonb WHERE id = :id` | `INSERT INTO user_obsidian_notes (user_id, document_id, obsidian_note_path) VALUES (:uid, :did, :path)` |
| List notes for article | `SELECT jsonb_array_elements_text(obsidian_note_paths) FROM web_documents WHERE id = :id` | `SELECT obsidian_note_path FROM user_obsidian_notes WHERE user_id = :uid AND document_id = :did` |

### Code Changes

- `article_browser.py` — replace direct column access with repository method calls.
- ORM model — in Phase 1, add `reviewed_at` (Mapped[datetime | None]) and `obsidian_note_paths` (Mapped[list], type JSONB, default=[]) to `WebDocument`. In Phase 9, add `UserDocumentReview` and `UserObsidianNote` models with relationships.
- Repository — add `get_unreviewed_documents(user_id)`, `mark_reviewed(user_id, document_id)`, `add_obsidian_note(user_id, document_id, path)`, and `get_obsidian_notes(user_id, document_id)` methods. Phase 1 implementation ignores `user_id`; Phase 9 uses it.

## Rationale

1. **Separation of concerns.** Document processing state (`document_state`) and user review state (`reviewed_at`) are orthogonal. Mixing them would complicate every script that reads `document_state`.
2. **YAGNI for now.** A join table for a single-user system adds complexity without benefit. Columns are simpler to query, simpler to maintain.
3. **Clean migration path.** The Phase 1 → Phase 9 migration is mechanical: one Alembic migration, zero data loss, no behavioral changes for existing code.
4. **No premature abstraction.** The repository interface can be designed to accept `user_id` from the start (defaulting to a constant), making the Phase 9 switch a backend-only change.

## Consequences

- **Positive:** `article_browser.py` gains `--not-reviewed` and `--no-obsidian` filters immediately.
- **Positive:** Zero new tables, minimal schema change for Phase 1.
- **Positive:** Clear, tested migration path to multi-user with no data loss.
- **Negative:** Phase 9 migration requires dropping and recreating the tracking mechanism — but this is a one-time, automated Alembic operation.
- **Negative:** Between Phase 1 and Phase 9, the `reviewed_at` column cannot distinguish between users — acceptable because multi-user auth doesn't exist yet.

## Related Artifacts

- [B-101: Track Obsidian Note Status for Articles](../\_bmad-output/planning-artifacts/epics/backlog.md)
- [B-33: Implement user authentication with AWS Cognito](../\_bmad-output/implementation-artifacts/sprint-status.yaml)
- [B-34: Add user ownership to database schema](../\_bmad-output/implementation-artifacts/sprint-status.yaml)
- [ADR-004a: Migrate to SQLAlchemy ORM](adr-004a-sqlalchemy-orm-migration.md) — ORM model changes follow this pattern
- [ADR-010: Database Lookup Tables with Foreign Keys](adr-010-database-lookup-tables.md) — Alembic migration pattern
- `backend/imports/article_browser.py` — primary consumer
- `backend/library/db/models.py` — ORM model to extend
