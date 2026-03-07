-- Add transcript_needed column to web_documents
-- Default false — transcription is paid, only process when explicitly requested
\c "lenie-ai";

ALTER TABLE public.web_documents
    ADD COLUMN IF NOT EXISTS transcript_needed boolean DEFAULT false;
