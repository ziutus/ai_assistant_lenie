-- Migration: sources lookup table + FK on web_documents.source
-- source = how the user DISCOVERED the content ("own", "unknow.news", "friend") —
-- a recommendation channel, NOT the content creator (that is web_documents.author).
-- FK references name (ADR-010); ON UPDATE CASCADE so renaming a source in the
-- lookup table rewrites all documents atomically (same pattern as model_fk in
-- 10-add-foreign-keys.sql).

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.sources (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR UNIQUE NOT NULL,
    description TEXT,
    url         TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO public.sources (name) VALUES ('own') ON CONFLICT (name) DO NOTHING;

ALTER TABLE public.web_documents
    ADD CONSTRAINT fk_source FOREIGN KEY (source)
    REFERENCES public.sources(name) ON UPDATE CASCADE;

SELECT 'Table sources created' AS status;
