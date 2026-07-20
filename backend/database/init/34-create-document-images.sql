-- Images extracted out of a document's article text (library/article_cleaner.py).
-- clean_article_text() replaces inline ![alt](url) markdown images with [imgN]
-- markers in text_md -- the URL used to be discarded. This table keeps the
-- image (and its adjacent caption/credit line, when present) so
-- article_quality.py can score photo sourcing without needing the image
-- markup to still live inline in the text. Replace-per-document semantics
-- (like document_entities): each re-clean of a document replaces its full
-- row set.

CREATE TABLE IF NOT EXISTS public.document_images (
    id               SERIAL PRIMARY KEY,
    document_id      INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_id         INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    position         SMALLINT,
    url              TEXT NOT NULL,
    alt_text         TEXT,
    caption_text     TEXT,
    caption_category VARCHAR(30),
    is_stock_photo   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_images_document_id ON public.document_images(document_id);
