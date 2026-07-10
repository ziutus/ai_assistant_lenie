-- Migration: geocoding cache + link from document_entities (NER stage 3,
-- docs/ner-integration-plan.md). One row per distinct query string sent to the
-- geocoder (LocationIQ free tier: 5000 req/day, 2 req/s) — negative results are
-- cached too, so a name is never geocoded twice.
-- resolved: geocoder returned a hit AND it passed the match-quality check
--           (rare Polish exonyms fuzzy-match to wrong places — e.g. "Cieśnina
--           Ormuz" -> a lake strait near Iława — so HTTP 200 alone is not proof)
-- raw: first hit as returned by the provider, for diagnostics/tuning

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.geocode_cache (
    id           SERIAL PRIMARY KEY,
    query        TEXT NOT NULL UNIQUE,
    resolved     BOOLEAN NOT NULL,
    display_name TEXT,
    lat          NUMERIC(9,6),
    lon          NUMERIC(9,6),
    osm_class    VARCHAR(50),
    osm_type     VARCHAR(50),
    importance   REAL,
    raw          JSONB,
    provider     VARCHAR(20) NOT NULL DEFAULT 'locationiq',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE public.document_entities
    ADD COLUMN IF NOT EXISTS geocode_id INTEGER REFERENCES public.geocode_cache(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_document_entities_geocode_id ON public.document_entities(geocode_id);

SELECT 'Table geocode_cache created, document_entities.geocode_id added' AS status;
