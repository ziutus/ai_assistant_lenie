-- Migration: add video_description column to documents
-- Stores the full YouTube video description (used for auto-parsing chapter timestamps)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS video_description TEXT;

SELECT 'Column video_description added to documents' AS status;
