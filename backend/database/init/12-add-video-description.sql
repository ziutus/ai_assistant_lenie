-- Migration: add video_description column to web_documents
-- Stores the full YouTube video description (used for auto-parsing chapter timestamps)
ALTER TABLE web_documents ADD COLUMN IF NOT EXISTS video_description TEXT;

SELECT 'Column video_description added to web_documents' AS status;
