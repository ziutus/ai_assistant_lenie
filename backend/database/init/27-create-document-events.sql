-- Timeline events discussed in documents. Derived data refreshed with
-- replace semantics by library/timeline_events.py.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.document_events (
    id               SERIAL PRIMARY KEY,
    document_id      INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    chapter_position INTEGER,
    event_date       DATE,
    event_date_end   DATE,
    date_precision   VARCHAR(10) NOT NULL CHECK (
        date_precision IN ('day', 'month', 'year', 'decade', 'century', 'era', 'unknown')
    ),
    date_text        TEXT NOT NULL,
    sort_year        INTEGER,
    description      TEXT NOT NULL,
    anchor_quote     TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_events_document_sort_year
    ON public.document_events(document_id, sort_year);

SELECT 'Table document_events created' AS status;
