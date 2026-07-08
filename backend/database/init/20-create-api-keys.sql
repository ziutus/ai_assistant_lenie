-- Migration: api_keys — service accounts + per-user API keys (Etap 8)
-- Replaces the single shared STALKER_API_KEY: kind=service keys grant full
-- access without a reader identity; kind=user keys carry the reader identity
-- (no x-user-id header needed). Only the SHA-256 hash of the key is stored;
-- the plaintext is shown once at creation time. key_prefix keeps the first
-- characters of the plaintext so keys can be recognized without revealing them.

\c "lenie-ai";

CREATE TABLE IF NOT EXISTS public.api_keys (
    id           SERIAL PRIMARY KEY,
    kind         VARCHAR(10) NOT NULL CHECK (kind IN ('user', 'service')),
    user_id      INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    name         VARCHAR(100) NOT NULL UNIQUE,
    key_hash     CHAR(64) NOT NULL UNIQUE,
    key_prefix   VARCHAR(16) NOT NULL,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP,
    CONSTRAINT ck_api_keys_user_id_kind CHECK ((kind = 'user') = (user_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON public.api_keys(user_id);

SELECT 'api_keys table created' AS status;
