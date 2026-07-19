-- Fix typo: rename column 'langauge' to 'language' in document_embeddings
\c "lenie-ai";

ALTER TABLE public.document_embeddings RENAME COLUMN langauge TO language;
