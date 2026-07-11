-- Migration: footnotes/references extracted out of a book's text_md
-- (library/references.py). OCR-ed books carry footnote lines inline where
-- they fell on the scanned page — they interrupt reading and pollute
-- NER/embeddings. Extraction moves them here; the reader renders them as a
-- per-chapter "Przypisy" section (GET /document/<id>/chapter/<pos>).
-- chapter_position: 1-based, matches detect_chapters(); NULL = unassigned.
-- marker: footnote number as printed ("18"); ref_text: full footnote text;
-- url: first URL found in the footnote (normalized to https://), if any.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.document_references (
    id               SERIAL PRIMARY KEY,
    document_id      INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    chapter_position INTEGER,
    marker           VARCHAR(10) NOT NULL,
    ref_text         TEXT NOT NULL,
    url              TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_references_document_id ON public.document_references(document_id);

SELECT 'Table document_references created' AS status;
