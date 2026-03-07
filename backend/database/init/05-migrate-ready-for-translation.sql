-- Migration: Replace deprecated READY_FOR_TRANSLATION state with READY_FOR_EMBEDDING
-- This is a one-time migration for existing records that still use the old state.
-- NOTE: Docker init scripts only run on first container startup (empty data volume).
-- For existing deployments, run this migration manually against the database.

UPDATE web_documents
SET document_state = 'READY_FOR_EMBEDDING'
WHERE document_state = 'READY_FOR_TRANSLATION';
