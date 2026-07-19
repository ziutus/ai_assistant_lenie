-- Migration: discovery_sources lookup table + FK on web_documents.discovery_source_id
-- discovery source = how the user DISCOVERED the content ("own", "unknow.news",
-- "friend") — a recommendation channel, NOT the content creator (that is
-- web_documents.byline). Stage 11d of the search rebuild normalized the old
-- name-based FK (sources.name, ON UPDATE CASCADE) into a plain integer FK;
-- renaming a source now only edits its lookup row. The HTTP wire format keeps
-- the NAME (`source` field) — resolution happens in the backend
-- (WebDocument.set_discovery_source, auto-creates unknown names).
-- The discovery_source_id column itself is created in 03-create-table.sql.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.discovery_sources (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR UNIQUE NOT NULL,
    description TEXT,
    url         TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO public.discovery_sources (name) VALUES ('own') ON CONFLICT (name) DO NOTHING;

ALTER TABLE public.web_documents
    ADD CONSTRAINT web_documents_discovery_source_id_fkey
    FOREIGN KEY (discovery_source_id) REFERENCES public.discovery_sources(id);

SELECT 'Table discovery_sources created' AS status;
