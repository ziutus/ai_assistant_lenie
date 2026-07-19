-- Migration: link embeddings to the chunk they were generated from
-- chunk_id: FK -> document_chunks.id, NULL for embeddings not generated from a chunk
-- (e.g. link title+summary, or whole-document embeddings from webdocument_md_decode.py)

\c "lenie-ai";

ALTER TABLE public.document_embeddings
    ADD COLUMN IF NOT EXISTS chunk_id INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_document_embeddings_chunk_id ON public.document_embeddings(chunk_id);

SELECT 'Column chunk_id added to document_embeddings' AS status;
