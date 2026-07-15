CREATE TABLE IF NOT EXISTS public.information_sources (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    source_type VARCHAR(30),
    domain TEXT,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.information_source_aliases (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES public.information_sources(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    UNIQUE (source_id, alias)
);

CREATE TABLE IF NOT EXISTS public.document_information_sources (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES public.information_sources(id) ON DELETE CASCADE,
    role VARCHAR(30) NOT NULL,
    raw_mention TEXT NOT NULL,
    source_url TEXT,
    evidence_excerpt TEXT,
    confidence INTEGER,
    extraction_method VARCHAR(30) NOT NULL,
    review_status VARCHAR(30) NOT NULL DEFAULT 'auto_accepted',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, source_id, role)
);

CREATE INDEX IF NOT EXISTS idx_info_source_alias_lower ON public.information_source_aliases (LOWER(alias));
CREATE INDEX IF NOT EXISTS idx_doc_info_sources_document ON public.document_information_sources (document_id);
CREATE INDEX IF NOT EXISTS idx_doc_info_sources_source_role ON public.document_information_sources (source_id, role);
