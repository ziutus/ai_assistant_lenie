-- Migration: add workflow columns to document_analysis_runs
-- mode:   analysis pipeline variant — 'transcript' (YouTube STT) | 'article' (clean markdown/text)
-- status: review workflow state — 'created' | 'in_review' | 'reviewed' | 'superseded'
-- scope:  human-readable analysed range (e.g. chapter title); NULL = whole document

\c "lenie-ai";

ALTER TABLE public.document_analysis_runs
    ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'transcript';

ALTER TABLE public.document_analysis_runs
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'created';

ALTER TABLE public.document_analysis_runs
    ADD COLUMN IF NOT EXISTS scope VARCHAR(200);

SELECT 'Columns mode, status, scope added to document_analysis_runs' AS status;
