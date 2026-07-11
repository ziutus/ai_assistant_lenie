-- Migration: Overpass API lookup cache for linear infrastructure (pipelines)
-- Same philosophy as geocode_cache: one live Overpass call ever per distinct
-- query string, negative results cached too (resolved=false).
-- kind: 'pipeline' (future: power_line, ...); substance: gas | oil | ...
-- geojson: simplified GeoJSON MultiLineString rendered on the reader map
-- Populated by library/overpass_client.py during POST /website_entities.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.infra_geometries (
    id           SERIAL PRIMARY KEY,
    query        TEXT NOT NULL UNIQUE,
    resolved     BOOLEAN NOT NULL,
    kind         VARCHAR(30),
    substance    VARCHAR(30),
    name         TEXT,
    wikidata_qid VARCHAR(20),
    geojson      JSONB,
    provider     VARCHAR(20) NOT NULL DEFAULT 'overpass',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

SELECT 'Table infra_geometries created' AS status;
