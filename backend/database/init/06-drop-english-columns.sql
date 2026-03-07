-- Migration: Remove deprecated English translation columns.
-- These columns are no longer used — all embedding models are multilingual.
-- NOTE: Docker init scripts only run on first container startup (empty data volume).
-- For existing deployments, run this migration manually against the database.
-- Deploy the updated application code BEFORE running this migration.

ALTER TABLE web_documents DROP COLUMN IF EXISTS text_english;
ALTER TABLE web_documents DROP COLUMN IF EXISTS title_english;
ALTER TABLE web_documents DROP COLUMN IF EXISTS summary_english;
