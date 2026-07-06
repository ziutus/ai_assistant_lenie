-- Migration: reader users, per-user reading progress and per-fragment notes (Etap 7)
-- users: lightweight identity (household trust model) — x-api-key stays the app-level
--        auth, x-user-id header only says WHO is reading.
-- user_reading_progress: current chapter + read chapters per (user, document);
--        chapter positions are 1-based and match GET /document/<id>/chapters.
-- user_document_notes: note anchored by exact quote + surrounding context
--        (W3C TextQuoteSelector style) at the DOCUMENT level, so it survives
--        run deletion; run_id/chunk_id are convenience links (SET NULL).
-- stance: agree | disagree | neutral | NULL — "czy się zgadzam" reaction.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.users (
    id           SERIAL PRIMARY KEY,
    username     VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.user_reading_progress (
    id                    SERIAL PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_id           INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    current_chapter       INTEGER NOT NULL,
    current_chapter_title VARCHAR(500),
    read_chapters         INTEGER[] NOT NULL DEFAULT '{}',
    updated_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_reading_progress_user_document UNIQUE (user_id, document_id)
);

CREATE TABLE IF NOT EXISTS public.user_document_notes (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    document_id      INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    chapter_position INTEGER,
    anchor_quote     TEXT NOT NULL,
    anchor_prefix    VARCHAR(100),
    anchor_suffix    VARCHAR(100),
    run_id           INTEGER REFERENCES public.document_analysis_runs(id) ON DELETE SET NULL,
    chunk_id         INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    note_text        TEXT NOT NULL,
    stance           VARCHAR(10),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_notes_document_id ON public.user_document_notes(document_id);
CREATE INDEX IF NOT EXISTS idx_user_notes_user_id     ON public.user_document_notes(user_id);

SELECT 'Reader user tables created' AS status;
