-- Migration: create document analysis tables for YouTube chunk analysis workflow
-- Enables storing LLM analysis results per document, with chunk-level review workflow

\c "lenie-ai";

-- Jedno uruchomienie analizy LLM dla dokumentu
CREATE TABLE IF NOT EXISTS public.document_analysis_runs (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    model       VARCHAR(100) NOT NULL,
    chunk_size  INTEGER NOT NULL DEFAULT 5000,
    synthesis   TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_document_id ON public.document_analysis_runs(document_id);


-- Poszczególne chunki z wynikami LLM
-- status: pending | approved | needs_reanalysis | split_requested | split
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id                SERIAL PRIMARY KEY,
    run_id            INTEGER NOT NULL REFERENCES public.document_analysis_runs(id) ON DELETE CASCADE,
    document_id       INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    position          SMALLINT NOT NULL,
    type              VARCHAR(20) NOT NULL,        -- TEMAT | REKLAMA
    topic             VARCHAR(500),
    original_text     TEXT NOT NULL,
    corrected_text    TEXT,
    summary           TEXT,                        -- NULL dla REKLAMA
    seg_start         INTEGER,                     -- indeks w text_raw JSON (włącznie)
    seg_end           INTEGER,                     -- indeks w text_raw JSON (wyłączony)
    rewrite_ratio     SMALLINT,                    -- % długości corrected vs original
    status            VARCHAR(30) NOT NULL DEFAULT 'pending',
    split_at_seg      INTEGER,                     -- segment podziału (przed zatwierdzeniem)
    split_first_type  VARCHAR(20),                 -- typ pierwszej części po podziale
    split_second_type VARCHAR(20),                 -- typ drugiej części po podziale
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_run_id       ON public.document_chunks(run_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id  ON public.document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status       ON public.document_chunks(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_run_position ON public.document_chunks(run_id, position);


-- Sekcje tematyczne (pogrupowane chunki) — edytowalne przez usera
CREATE TABLE IF NOT EXISTS public.document_topic_sections (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES public.document_analysis_runs(id) ON DELETE CASCADE,
    document_id     INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    position        SMALLINT NOT NULL,
    type            VARCHAR(20) NOT NULL,          -- TEMAT | REKLAMA
    title           VARCHAR(500),
    summary         TEXT,
    chunk_positions INTEGER[] NOT NULL,            -- np. {1,2,3} — pozycje chunków z tego runu
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sections_run_id ON public.document_topic_sections(run_id);

SELECT 'Tables document_analysis_runs, document_chunks, document_topic_sections created' AS status;
