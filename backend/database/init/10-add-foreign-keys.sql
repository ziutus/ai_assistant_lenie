-- Add foreign key constraints to documents and document_embeddings
-- References lookup tables created in 09-create-lookup-tables.sql
-- Story: B-95

\c "lenie-ai";

-- documents: 3 FK constraints referencing lookup table `name` columns
ALTER TABLE public.documents
    ADD CONSTRAINT fk_document_type
    FOREIGN KEY (document_type) REFERENCES public.document_types(name);

ALTER TABLE public.documents
    ADD CONSTRAINT fk_processing_status
    FOREIGN KEY (processing_status) REFERENCES public.processing_status_types(name);

ALTER TABLE public.documents
    ADD CONSTRAINT fk_processing_error_code
    FOREIGN KEY (processing_error_code) REFERENCES public.processing_error_types(name);

-- document_embeddings: 1 FK constraint with cascade
ALTER TABLE public.document_embeddings
    ADD CONSTRAINT model_fk
    FOREIGN KEY (model) REFERENCES public.embedding_models(name) ON UPDATE CASCADE ON DELETE CASCADE;

-- Verification: list all FK constraints on both tables
SELECT constraint_name, table_name, constraint_type
FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY'
  AND table_name IN ('documents', 'document_embeddings')
ORDER BY table_name, constraint_name;
