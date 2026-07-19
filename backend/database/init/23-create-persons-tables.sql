-- Migration: person entity model (NER stage 4, docs/person-ner-plan.md /
-- docs/ner-integration-plan.md). Persons need a relational model instead of
-- tags: two different people can share a name (osoba-jan-kowalski would merge
-- them) and one person appears under many spelling variants (inflection,
-- initials) that must aggregate.
--
-- persons:          one row per real person; wikidata_qid NULL when the person
--                   has no Wikidata entry (local/less-known figures)
-- person_aliases:   spelling variants seen in articles, growing over time
-- document_persons: document<->person M:N + extraction metadata
--   confidence: wikidata_matched (Wikidata human entity + LLM context match)
--             | alias_matched    (existing alias/canonical name matched)
--             | manual_review    (new/uncertain person - review queue)
--             | manual_confirmed (human approved a manual_review row)

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.persons (
    id             SERIAL PRIMARY KEY,
    uuid           VARCHAR(100) NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    canonical_name TEXT NOT NULL,
    wikidata_qid   VARCHAR(20) UNIQUE,
    description    TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_persons_canonical_name_trgm
    ON public.persons USING gin (canonical_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS public.person_aliases (
    id        SERIAL PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES public.persons(id) ON DELETE CASCADE,
    alias     TEXT NOT NULL,
    UNIQUE (person_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_person_aliases_alias_trgm
    ON public.person_aliases USING gin (alias gin_trgm_ops);

CREATE TABLE IF NOT EXISTS public.document_persons (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES public.persons(id) ON DELETE CASCADE,
    raw_mention TEXT NOT NULL,
    confidence  VARCHAR(20) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_document_persons_document_id ON public.document_persons(document_id);
CREATE INDEX IF NOT EXISTS idx_document_persons_person_id   ON public.document_persons(person_id);

SELECT 'Tables persons, person_aliases, document_persons created' AS status;
