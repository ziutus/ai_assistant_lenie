-- Skrypt tworzenia tabel dla projektu Stalker Web Documents
-- Baza danych: lenie-ai (PostgreSQL)

-- Przełączenie na nową bazę danych i instalacja rozszerzeń
\c "lenie-ai";

-- Instalacja rozszerzenia pgvector
CREATE EXTENSION IF NOT EXISTS vector;



-- Tworzenie tabeli głównej dla dokumentów
CREATE TABLE IF NOT EXISTS public.web_documents (
                                                    id SERIAL PRIMARY KEY,
                                                    url TEXT NOT NULL,
                                                    title TEXT,
                                                    text TEXT,
                                                    text_md TEXT,
                                                    text_english TEXT,
                                                    document_type VARCHAR(50) NOT NULL,
                                                    document_state VARCHAR(50) NOT NULL DEFAULT 'URL_ADDED',
                                                    document_state_error TEXT,
                                                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                    language VARCHAR(10),
                                                    tags TEXT,
                                                    summary TEXT,
                                                    summary_english TEXT,
                                                    source TEXT,
                                                    author TEXT,
                                                    note TEXT,
                                                    project VARCHAR(100),
                                                    s3_uuid VARCHAR(100),
                                                    chapter_list TEXT,
                                                    date_from DATE,
                                                    paywall BOOLEAN DEFAULT false,
                                                    ai_summary_needed BOOLEAN DEFAULT false,
                                                    ai_correction_needed BOOLEAN DEFAULT false
);

-- Tworzenie tabeli dla embeddings
CREATE TABLE IF NOT EXISTS public.websites_embeddings (
                                                          id SERIAL PRIMARY KEY,
                                                          website_id INTEGER NOT NULL,
                                                          langauge VARCHAR(10), -- zachowuję oryginalną nazwę z błędem dla kompatybilności
                                                          text TEXT,
                                                          text_original TEXT,
                                                          embedding vector(1536), -- dla modeli OpenAI
                                                          model VARCHAR(100) NOT NULL,
                                                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                          FOREIGN KEY (website_id) REFERENCES public.web_documents(id) ON DELETE CASCADE
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

CREATE INDEX IF NOT EXISTS idx_websites_embeddings_website_id ON public.websites_embeddings(website_id);
CREATE INDEX IF NOT EXISTS idx_websites_embeddings_model ON public.websites_embeddings(model);

-- Indeks dla wyszukiwania podobieństwa wektorowego
CREATE INDEX IF NOT EXISTS idx_websites_embeddings_vector ON public.websites_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Potwierdzenie utworzenia tabel
SELECT 'Tables created successfully in lenie-ai database' as status;