-- Manual topic categories for individual reader chapters backed by analysis chunks.
CREATE TABLE IF NOT EXISTS public.document_chunk_group_memberships (
    chunk_id INTEGER NOT NULL REFERENCES public.document_chunks(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_document_chunk_group_memberships_group_id
    ON public.document_chunk_group_memberships(group_id);
