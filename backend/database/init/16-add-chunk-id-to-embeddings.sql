-- Migration: link embeddings to the chunk they were generated from
-- chunk_id: FK -> document_chunks.id, NULL for embeddings not generated from a chunk
-- (e.g. link title+summary, or whole-document embeddings from webdocument_md_decode.py)

\c "lenie-ai";

ALTER TABLE public.websites_embeddings
    ADD COLUMN IF NOT EXISTS chunk_id INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_websites_embeddings_chunk_id ON public.websites_embeddings(chunk_id);

SELECT 'Column chunk_id added to websites_embeddings' AS status;
