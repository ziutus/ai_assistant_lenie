-- Migration: raw NER entities per document (MVP of docs/ner-integration-plan.md)
-- entity_type: persName | geogName | placeName (labels from spaCy pl_core_news_lg
--              via ner_service/, see backend/library/ner_client.py)
-- entity_text: base form of the mention (lemma when available) — inflected
--              variants of the same name are aggregated into one row
-- mention_count: number of mentions aggregated into this row
-- variants: distinct surface forms as seen in the text ("Kijów", "Kijowa") —
--           used by the chapter-scoped entity filter (entity_service.
--           filter_entities_to_text) to match regardless of Polish inflection
-- Deliberately no disambiguation columns — persons get dedicated tables in a
-- later stage (docs/person-ner-plan.md), places get verification + tags
-- (docs/geo-place-ner-plan.md). Rows are derived data: refresh = replace.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.document_entities (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    entity_type   VARCHAR(20) NOT NULL,
    entity_text   TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    variants      TEXT[] NOT NULL DEFAULT '{}',
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, entity_type, entity_text)
);

CREATE INDEX IF NOT EXISTS idx_document_entities_document_id ON public.document_entities(document_id);
CREATE INDEX IF NOT EXISTS idx_document_entities_type        ON public.document_entities(entity_type);

SELECT 'Table document_entities created' AS status;
