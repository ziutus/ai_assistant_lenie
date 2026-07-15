ALTER TABLE public.user_document_notes
    ADD COLUMN IF NOT EXISTS tags VARCHAR(80)[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_user_document_notes_tags
    ON public.user_document_notes USING GIN (tags);
