-- Feed monitor schema for fresh PostgreSQL databases. Alembic is the upgrade source of truth.
INSERT INTO public.processing_status_types (name) VALUES ('NEED_LLM_ANALYSIS') ON CONFLICT (name) DO NOTHING;
CREATE TABLE IF NOT EXISTS public.feed_sources (
    id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(30) NOT NULL CHECK (type IN ('rss','wordpress','youtube_channel','json_api')),
    url TEXT, channel_id VARCHAR(128), language VARCHAR(10) NOT NULL DEFAULT 'pl',
    collection_id INTEGER REFERENCES public.collections(id) ON DELETE SET NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb, auto_import BOOLEAN NOT NULL DEFAULT false,
    disabled BOOLEAN NOT NULL DEFAULT false, auto_import_after TIMESTAMPTZ,
    discovery_source_id INTEGER REFERENCES public.discovery_sources(id) ON DELETE SET NULL,
    default_state VARCHAR(50) NOT NULL DEFAULT 'URL_ADDED' REFERENCES public.processing_status_types(name),
    field_mapping JSONB NOT NULL DEFAULT '{}'::jsonb, skip_url_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    skip_title_patterns JSONB NOT NULL DEFAULT '[]'::jsonb, last_checked_at TIMESTAMPTZ,
    last_successful_import_at TIMESTAMPTZ, last_error_at TIMESTAMPTZ, last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((type = 'youtube_channel' AND channel_id IS NOT NULL AND url IS NULL) OR (type <> 'youtube_channel' AND url IS NOT NULL AND channel_id IS NULL))
);
CREATE TABLE IF NOT EXISTS public.feed_items (
    id SERIAL PRIMARY KEY, feed_source_id INTEGER NOT NULL REFERENCES public.feed_sources(id) ON DELETE RESTRICT,
    url TEXT NOT NULL, canonical_url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', summary TEXT,
    published_at TIMESTAMPTZ, raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(40) NOT NULL DEFAULT 'new' CHECK (status IN ('new','llm_analysis_requested','saved_for_later','imported','skipped','ignored','error')),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    saved_at TIMESTAMPTZ, saved_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL, reviewed_at TIMESTAMPTZ, reviewed_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL, document_id INTEGER REFERENCES public.documents(id) ON DELETE SET NULL, review_note TEXT, review_reason VARCHAR(40) CHECK (review_reason IS NULL OR review_reason IN ('not_interested','duplicate','already_known','too_long','other')), ignored_pattern TEXT, last_error TEXT,
    UNIQUE(feed_source_id, canonical_url)
);
CREATE INDEX IF NOT EXISTS idx_feed_items_source_status ON public.feed_items(feed_source_id,status);
CREATE INDEX IF NOT EXISTS idx_feed_items_status_first_seen ON public.feed_items(status,first_seen_at);
CREATE INDEX IF NOT EXISTS idx_feed_items_status_saved_at ON public.feed_items(status,saved_at);
CREATE TABLE IF NOT EXISTS public.jobs (
    id VARCHAR(32) PRIMARY KEY, type VARCHAR(40) NOT NULL CHECK (type IN ('feed_check','feed_check_all','feed_auto_import','feed_daily')),
    status VARCHAR(30) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','cancel_requested','cancelled')),
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb, progress JSONB, result JSONB, error TEXT, attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0), max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 0), available_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), started_at TIMESTAMPTZ, heartbeat_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, initiated_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL, idempotency_key VARCHAR(255) UNIQUE
);
CREATE TABLE IF NOT EXISTS public.feed_item_llm_analyses (
    id SERIAL PRIMARY KEY, feed_item_id INTEGER NOT NULL REFERENCES public.feed_items(id) ON DELETE CASCADE, status VARCHAR(20) NOT NULL DEFAULT 'requested', requested_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL, claimed_at TIMESTAMPTZ, claimed_by VARCHAR(255), prompt_payload JSONB, result JSONB, recommendation VARCHAR(30), error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_feed_item_active_llm ON public.feed_item_llm_analyses(feed_item_id) WHERE status IN ('requested','claimed');
CREATE TABLE IF NOT EXISTS public.document_llm_analyses (
    id SERIAL PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE, status VARCHAR(20) NOT NULL DEFAULT 'requested', requested_by_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL, claimed_by VARCHAR(255), input_payload JSONB, result JSONB, next_status VARCHAR(50), error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
);
