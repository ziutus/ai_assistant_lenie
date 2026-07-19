CREATE TABLE IF NOT EXISTS public.cited_publications (
    id SERIAL PRIMARY KEY,
    title TEXT,
    journal TEXT,
    publication_year INTEGER,
    doi TEXT,
    pmid VARCHAR(20),
    pmcid VARCHAR(30),
    canonical_url TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cited_publications_doi ON public.cited_publications (LOWER(doi)) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cited_publications_pmid ON public.cited_publications (pmid) WHERE pmid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cited_publications_pmcid ON public.cited_publications (UPPER(pmcid)) WHERE pmcid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cited_publications_url ON public.cited_publications (canonical_url);

CREATE TABLE IF NOT EXISTS public.document_cited_publications (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    publication_id INTEGER NOT NULL REFERENCES public.cited_publications(id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    raw_citation TEXT NOT NULL,
    evidence_excerpt TEXT,
    extraction_method VARCHAR(30) NOT NULL,
    review_status VARCHAR(30) NOT NULL DEFAULT 'auto_accepted',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, publication_id)
);
CREATE INDEX IF NOT EXISTS idx_document_cited_publications_document ON public.document_cited_publications(document_id);
CREATE INDEX IF NOT EXISTS idx_document_cited_publications_publication ON public.document_cited_publications(publication_id);
