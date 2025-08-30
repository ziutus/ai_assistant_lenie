-- Skrypt tworzenia tabel dla projektu Stalker Web Documents
-- Baza danych: lenie-ai (PostgreSQL)

-- Przełączenie na nową bazę danych i instalacja rozszerzeń
\c "lenie-ai";

-- Tworzenie tabeli głównej dla dokumentów
create table web_documents
(
    id                   serial        primary key,
    url                  text                                               not null,
    title                text,
    text                 text,
    text_md              text,
    text_english         text,
    document_type        varchar(50)                                        not null,
    document_state       varchar(50) default 'URL_ADDED'::character varying not null,
    document_state_error text,
    created_at           timestamp   default CURRENT_TIMESTAMP,
    language             varchar(10),
    tags                 text,
    summary              text,
    summary_english      text,
    source               text,
    author               text,
    note                 text,
    project              varchar(100),
    s3_uuid              varchar(100),
    chapter_list         text,
    date_from            date,
    paywall              boolean     default false,
    ai_summary_needed    boolean     default false,
    ai_correction_needed boolean     default false,
    title_english        text,
    original_id          text,
    document_length      integer,
    text_raw             text,
    transcript_job_id    text
);

-- Indeksy dla optymalizacji wydajności
CREATE INDEX IF NOT EXISTS idx_web_documents_document_type ON public.web_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_web_documents_document_state ON public.web_documents(document_state);
CREATE INDEX IF NOT EXISTS idx_web_documents_created_at ON public.web_documents(created_at);
CREATE INDEX IF NOT EXISTS idx_web_documents_url ON public.web_documents(url);
CREATE INDEX IF NOT EXISTS idx_web_documents_project ON public.web_documents(project);
CREATE INDEX IF NOT EXISTS idx_web_documents_source ON public.web_documents(source);
CREATE INDEX IF NOT EXISTS idx_web_documents_date_from ON public.web_documents(date_from);
CREATE INDEX IF NOT EXISTS idx_web_documents_paywall ON public.web_documents(paywall);
CREATE INDEX IF NOT EXISTS idx_web_documents_ai_flags ON public.web_documents(ai_summary_needed, ai_correction_needed);

-- Potwierdzenie utworzenia tabel
SELECT 'Table created successfully in lenie-ai database' as status;