-- Skrypt tworzenia tabel dla projektu Stalker Web Documents
-- Baza danych: lenie-ai (PostgreSQL)

-- Przełączenie na nową bazę danych i instalacja rozszerzeń
\c "lenie-ai";


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


CREATE INDEX IF NOT EXISTS idx_websites_embeddings_website_id ON public.websites_embeddings(website_id);
CREATE INDEX IF NOT EXISTS idx_websites_embeddings_model ON public.websites_embeddings(model);

-- Indeks dla wyszukiwania podobieństwa wektorowego
CREATE INDEX IF NOT EXISTS idx_websites_embeddings_vector ON public.websites_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Potwierdzenie utworzenia tabel
SELECT 'Table websites_embeddings created successfully in lenie-ai database' as status;