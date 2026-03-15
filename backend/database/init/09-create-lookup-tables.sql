-- Create lookup tables and seed data for Project Lenie
-- Tables: document_status_types, document_status_error_types, document_types, embedding_models

\c "lenie-ai";

-- document_status_types (16 rows)
-- Source: backend/library/models/stalker_document_status.py
CREATE TABLE IF NOT EXISTS public.document_status_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

INSERT INTO public.document_status_types (name) VALUES
    ('ERROR'),
    ('URL_ADDED'),
    ('NEED_TRANSCRIPTION'),
    ('TRANSCRIPTION_IN_PROGRESS'),
    ('TRANSCRIPTION_DONE'),
    ('TRANSCRIPTION_DONE_AND_SPLIT_BY_CHAPTERS'),
    ('NEED_MANUAL_REVIEW'),
    ('READY_FOR_TRANSLATION'),
    ('READY_FOR_EMBEDDING'),
    ('EMBEDDING_EXIST'),
    ('DOCUMENT_INTO_DATABASE'),
    ('NEED_CLEAN_TEXT'),
    ('NEED_CLEAN_MD'),
    ('TEXT_TO_MD_DONE'),
    ('MD_SIMPLIFIED'),
    ('TEMPORARY_ERROR')
ON CONFLICT (name) DO NOTHING;

-- document_status_error_types (17 rows)
-- Source: backend/library/models/stalker_document_status_error.py
CREATE TABLE IF NOT EXISTS public.document_status_error_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

INSERT INTO public.document_status_error_types (name) VALUES
    ('NONE'),
    ('ERROR_DOWNLOAD'),
    ('LINK_SUMMARY_MISSING'),
    ('TITLE_MISSING'),
    ('TITLE_TRANSLATION_ERROR'),
    ('TEXT_MISSING'),
    ('TEXT_TRANSLATION_ERROR'),
    ('SUMMARY_TRANSLATION_ERROR'),
    ('NO_URL_ERROR'),
    ('EMBEDDING_ERROR'),
    ('MISSING_TRANSLATION'),
    ('TRANSLATION_ERROR'),
    ('REGEX_ERROR'),
    ('TEXT_TO_MD_ERROR'),
    ('NO_CAPTIONS_AVAILABLE'),
    ('CAPTIONS_LANGUAGE_MISMATCH'),
    ('CAPTIONS_FETCH_ERROR')
ON CONFLICT (name) DO NOTHING;

-- document_types (6 rows)
-- Source: backend/library/models/stalker_document_type.py
CREATE TABLE IF NOT EXISTS public.document_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

INSERT INTO public.document_types (name) VALUES
    ('movie'),
    ('youtube'),
    ('link'),
    ('webpage'),
    ('text_message'),
    ('text'),
    ('email')
ON CONFLICT (name) DO NOTHING;

-- embedding_models (7 rows)
-- Source: backend/database/init/04-create-table.sql HNSW indexes + sequential scan models
CREATE TABLE IF NOT EXISTS public.embedding_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL
);

INSERT INTO public.embedding_models (name) VALUES
    ('text-embedding-ada-002'),
    ('amazon.titan-embed-text-v1'),
    ('amazon.titan-embed-text-v2:0'),
    ('dunzhang/stella_en_1.5B_v5'),
    ('BAAI/bge-m3'),
    ('BAAI/bge-multilingual-gemma2'),
    ('intfloat/e5-mistral-7b-instruct')
ON CONFLICT (name) DO NOTHING;

-- Verification
SELECT 'document_status_types' AS table_name, count(*) AS row_count FROM public.document_status_types
UNION ALL
SELECT 'document_status_error_types', count(*) FROM public.document_status_error_types
UNION ALL
SELECT 'document_types', count(*) FROM public.document_types
UNION ALL
SELECT 'embedding_models', count(*) FROM public.embedding_models;
