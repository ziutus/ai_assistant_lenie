-- Add transcript_needed column to documents
-- Default false — transcription is paid, only process when explicitly requested
\c "lenie-ai";

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS transcript_needed boolean DEFAULT false;
