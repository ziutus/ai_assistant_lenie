-- Skrypt tworzenia tabel dla projektu Stalker Web Documents
-- Baza danych: lenie-ai (PostgreSQL)

-- Przełączenie na nową bazę danych i instalacja rozszerzeń
\c "lenie-ai";

-- Tworzenie tabeli głównej dla dokumentów
create table documents
(
    id                   serial primary key,
    summary              text,
    url                  text not null,
    language             varchar(10),
    tags                 text,
    text                 text,
    paywall              boolean     default false,
    title                text,
    created_at           timestamp   default CURRENT_TIMESTAMP,
    document_type        varchar(50) not null,
    discovery_source_id  integer,
    published_on            date,
    original_id          text,
    document_length      integer,
    chapter_list         text,
    video_description    text,
    processing_status       varchar(50) default 'URL_ADDED'::character varying not null,
    processing_error_code text,
    text_raw             text,
    transcript_job_id    text,
    ai_summary_needed    boolean     default false,
    byline               text,
    note                 text,
    uuid                 varchar(100) NOT NULL DEFAULT gen_random_uuid(),
    collection_id        integer,
    text_md              text,
    transcript_needed    boolean     default false
);

-- Indeksy dla optymalizacji wydajności
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON public.documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON public.documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON public.documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_url ON public.documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_collection_id ON public.documents(collection_id);
CREATE INDEX IF NOT EXISTS idx_documents_discovery_source_id ON public.documents(discovery_source_id);
CREATE INDEX IF NOT EXISTS idx_documents_published_on ON public.documents(published_on);
CREATE INDEX IF NOT EXISTS idx_documents_paywall ON public.documents(paywall);
CREATE INDEX IF NOT EXISTS idx_documents_ai_flag ON public.documents(ai_summary_needed);

-- Unique constraint for uuid (global document identifier, ADR-015)
ALTER TABLE public.documents ADD CONSTRAINT uq_documents_uuid UNIQUE (uuid);

-- Potwierdzenie utworzenia tabel
SELECT 'Table documents created successfully in lenie-ai database' as status;