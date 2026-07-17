CREATE TABLE IF NOT EXISTS public.document_analysis_jobs (
    id VARCHAR(32) PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.web_documents(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES public.document_analysis_runs(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    parameters JSONB NOT NULL,
    progress TEXT,
    error TEXT,
    chunk_count INTEGER,
    ad_count INTEGER,
    topic_section_count INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT ck_document_analysis_jobs_status
        CHECK (status IN ('queued', 'running', 'done', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_document_analysis_jobs_document_created
    ON public.document_analysis_jobs(document_id, created_at);
CREATE INDEX IF NOT EXISTS idx_document_analysis_jobs_status_created
    ON public.document_analysis_jobs(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_analysis_jobs_active_document
    ON public.document_analysis_jobs(document_id)
    WHERE status IN ('queued', 'running');
