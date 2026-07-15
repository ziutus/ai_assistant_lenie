ALTER TABLE public.document_persons
    ADD COLUMN IF NOT EXISTS role VARCHAR(30) NOT NULL DEFAULT 'mentioned',
    ADD COLUMN IF NOT EXISTS source_excerpt TEXT,
    ADD COLUMN IF NOT EXISTS bio_review_status VARCHAR(30),
    ADD COLUMN IF NOT EXISTS bio_review_result JSONB,
    ADD COLUMN IF NOT EXISTS bio_reviewed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_document_persons_bio_review
    ON public.document_persons (bio_review_status);
