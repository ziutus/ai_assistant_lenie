-- Migration: add speakers JSONB column to document_analysis_runs
-- Stores extracted speaker info: [{"name": "...", "role": "...", "description": "..."}]

\c "lenie-ai";

ALTER TABLE public.document_analysis_runs
    ADD COLUMN IF NOT EXISTS speakers JSONB NOT NULL DEFAULT '[]';

SELECT 'Column speakers added to document_analysis_runs' AS status;
