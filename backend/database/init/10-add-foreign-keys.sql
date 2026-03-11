-- Add foreign key constraints to web_documents and websites_embeddings
-- References lookup tables created in 09-create-lookup-tables.sql
-- Story: B-95

\c "lenie-ai";

-- web_documents: 3 FK constraints referencing lookup table `name` columns
ALTER TABLE public.web_documents
    ADD CONSTRAINT fk_document_type
    FOREIGN KEY (document_type) REFERENCES public.document_types(name);

ALTER TABLE public.web_documents
    ADD CONSTRAINT fk_document_state
    FOREIGN KEY (document_state) REFERENCES public.document_status_types(name);

ALTER TABLE public.web_documents
    ADD CONSTRAINT fk_document_state_error
    FOREIGN KEY (document_state_error) REFERENCES public.document_status_error_types(name);

-- websites_embeddings: 1 FK constraint with cascade
ALTER TABLE public.websites_embeddings
    ADD CONSTRAINT model_fk
    FOREIGN KEY (model) REFERENCES public.embedding_models(name) ON UPDATE CASCADE ON DELETE CASCADE;

-- Verification: list all FK constraints on both tables
SELECT constraint_name, table_name, constraint_type
FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY'
  AND table_name IN ('web_documents', 'websites_embeddings')
ORDER BY table_name, constraint_name;
