-- Adds a storage-backed image source alongside the existing external-URL one.
-- url = external image belonging to a web article (library/article_cleaner.py).
-- storage_key = object in our own object storage (library/storage.py), used for
-- images extracted from imported book PDFs (library/book_pdf_import.py). Exactly
-- one of the two is required per row.

ALTER TABLE public.document_images ADD COLUMN IF NOT EXISTS storage_key TEXT;
ALTER TABLE public.document_images ADD COLUMN IF NOT EXISTS page_number SMALLINT;
ALTER TABLE public.document_images ADD COLUMN IF NOT EXISTS chapter_position SMALLINT;
ALTER TABLE public.document_images ALTER COLUMN url DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'document_images_source_present'
    ) THEN
        ALTER TABLE public.document_images ADD CONSTRAINT document_images_source_present
            CHECK (url IS NOT NULL OR storage_key IS NOT NULL);
    END IF;
END $$;
