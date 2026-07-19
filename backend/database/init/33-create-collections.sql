-- Thematic collections a document can belong to (ADR-017: 1:N via
-- documents.collection_id; stage 11c of the search rebuild replaced the
-- never-used documents.project string column with this lookup table).
-- The collection_id column itself is created in 03-create-table.sql (runs
-- earlier); the FK constraint is added here, after the table exists.

CREATE TABLE IF NOT EXISTS public.collections (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_collection_id_fkey'
    ) THEN
        ALTER TABLE public.documents
            ADD CONSTRAINT documents_collection_id_fkey
            FOREIGN KEY (collection_id) REFERENCES public.collections(id) ON DELETE SET NULL;
    END IF;
END $$;
