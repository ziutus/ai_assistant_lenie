-- Skrypt tworzenia tabel dla projektu Stalker Web Documents
-- Baza danych: lenie-ai (PostgreSQL)

-- Przełączenie na nową bazę danych i instalacja rozszerzeń
\c "lenie-ai";

-- Tworzenie tabeli głównej dla dokumentów
create table web_documents
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
    text_english         text,
    source               text,
    summary_english      text,
    title_english        text,
    date_from            date,
    original_id          text,
    document_length      integer,
    chapter_list         text,
    document_state       varchar(50) default 'URL_ADDED'::character varying not null,
    document_state_error text,
    text_raw             text,
    transcript_job_id    text,
    ai_summary_needed    boolean     default false,
    author               text,
    note                 text,
    s3_uuid              varchar(100),
    project              varchar(100),
    text_md              text
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
CREATE INDEX IF NOT EXISTS idx_web_documents_ai_flag ON public.web_documents(ai_summary_needed);

-- Potwierdzenie utworzenia tabel
SELECT 'Table web_documents created successfully in lenie-ai database' as status;