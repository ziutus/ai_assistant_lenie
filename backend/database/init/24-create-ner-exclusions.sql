-- Migration: NER exclusion dictionary (false-positive suppressions)
-- Suppresses recurring NER mistakes at entity-refresh time (entity_service.py):
--   * "Taliban" / "Taliban Pakistan" detected as persName (organizations)
--   * STT artifacts like "Starling" / "starlinek" (the Starlink device)
-- entity_text: matched case-insensitively against the aggregated entity base
--              form (lemma) of a mention
-- entity_type: persName | geogName | placeName | '*' (all types)
-- scope:       'global' (every document) or 'author' (only documents whose
--              documents.author matches the author column — e.g. one
--              podcast channel whose STT keeps producing the same artifact)

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.ner_exclusions (
    id          SERIAL PRIMARY KEY,
    entity_text TEXT NOT NULL,
    entity_type VARCHAR(20) NOT NULL DEFAULT '*',
    scope       VARCHAR(10) NOT NULL DEFAULT 'global',
    author      TEXT,
    note        TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ner_exclusions_scope_check CHECK (scope IN ('global', 'author')),
    CONSTRAINT ner_exclusions_author_required CHECK (scope != 'author' OR author IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ner_exclusions_unique
    ON public.ner_exclusions (LOWER(entity_text), entity_type, scope, COALESCE(LOWER(author), ''));

SELECT 'Table ner_exclusions created' AS status;
