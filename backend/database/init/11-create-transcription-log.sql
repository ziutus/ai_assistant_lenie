-- Create transcription_log table for tracking transcription usage and costs
-- Story: AssemblyAI Usage Tracking — Story 1

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.transcription_log (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES public.web_documents(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL,
    speech_model VARCHAR(100),
    audio_duration_seconds INTEGER NOT NULL,
    cost_usd NUMERIC(10, 4) NOT NULL,
    transcript_job_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transcription_log_provider ON public.transcription_log(provider);
CREATE INDEX IF NOT EXISTS idx_transcription_log_created_at ON public.transcription_log(created_at);
