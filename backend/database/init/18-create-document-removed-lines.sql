-- Migration: store lines/blocks removed during manual chunk-review cleanup
-- Training data for improving article_cleaner.py / site_rules.json: what the
-- automatic cleaner missed and a human had to remove.
-- source: manual (line removed in chunk-review UI) | szum_chunk (whole
--         SZUM/REKLAMA chunk dropped by apply_cleanup)
-- run_id/chunk_id are SET NULL on delete so rows survive run cleanup and stay
-- usable for aggregate queries (portal derived via join on web_documents.url).

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.document_removed_lines (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    run_id      INTEGER REFERENCES public.document_analysis_runs(id) ON DELETE SET NULL,
    chunk_id    INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    source      VARCHAR(20) NOT NULL,
    line_text   TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_removed_lines_document_id ON public.document_removed_lines(document_id);
CREATE INDEX IF NOT EXISTS idx_removed_lines_source      ON public.document_removed_lines(source);

SELECT 'Table document_removed_lines created' AS status;
