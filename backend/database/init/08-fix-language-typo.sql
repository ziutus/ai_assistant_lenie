-- Fix typo: rename column 'langauge' to 'language' in websites_embeddings
\c "lenie-ai";

ALTER TABLE public.websites_embeddings RENAME COLUMN langauge TO language;
