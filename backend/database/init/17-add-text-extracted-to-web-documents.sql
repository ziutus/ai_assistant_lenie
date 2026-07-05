-- Migration: store raw LLM article extraction output (pre clean_article_text)
-- text_extracted: markdown returned by the LLM article boundary extraction, BEFORE
-- article_cleaner.clean_article_text(). Diagnostic column for cleaner regression
-- checks — intentionally NOT exposed via the API. text_md holds the cleaned version.

\c "lenie-ai";

ALTER TABLE public.web_documents
    ADD COLUMN IF NOT EXISTS text_extracted TEXT;

SELECT 'Column text_extracted added to web_documents' AS status;
