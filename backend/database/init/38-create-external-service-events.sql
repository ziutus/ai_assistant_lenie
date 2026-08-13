CREATE TABLE IF NOT EXISTS public.external_service_events (
    id BIGINT PRIMARY KEY, service VARCHAR(50) NOT NULL, operation VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL, status_code INTEGER, error_code VARCHAR(100), latency_ms INTEGER,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_external_service_events_service_occurred ON public.external_service_events (service, occurred_at);
