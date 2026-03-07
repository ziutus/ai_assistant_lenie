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
                                                          embedding vector, -- bez ustalonego wymiaru — obsługa wielu modeli o różnych wymiarach
                                                          model VARCHAR(100) NOT NULL,
                                                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                          FOREIGN KEY (website_id) REFERENCES public.web_documents(id) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_websites_embeddings_website_id ON public.websites_embeddings(website_id);
CREATE INDEX IF NOT EXISTS idx_websites_embeddings_model ON public.websites_embeddings(model);

-- Indeksy HNSW per model (partial indexes) — każdy model embeddingu ma swój indeks
-- HNSW w pgvector 0.8.1 obsługuje max 2000 wymiarów dla vector_cosine_ops
-- Modele z >2000 wymiarów (bge-multilingual-gemma2: 3584, e5-mistral: 4096) używają sequential scan
-- Dodaj nowy indeks przy dodawaniu obsługi nowego modelu (jeśli wymiar <= 2000)
CREATE INDEX IF NOT EXISTS idx_emb_ada002 ON public.websites_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops) WHERE model = 'text-embedding-ada-002';
CREATE INDEX IF NOT EXISTS idx_emb_titan_v1 ON public.websites_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops) WHERE model = 'amazon.titan-embed-text-v1';
CREATE INDEX IF NOT EXISTS idx_emb_titan_v2 ON public.websites_embeddings USING hnsw ((embedding::vector(1024)) vector_cosine_ops) WHERE model = 'amazon.titan-embed-text-v2:0';
CREATE INDEX IF NOT EXISTS idx_emb_stella_en ON public.websites_embeddings USING hnsw ((embedding::vector(1024)) vector_cosine_ops) WHERE model = 'dunzhang/stella_en_1.5B_v5';
CREATE INDEX IF NOT EXISTS idx_emb_bge_m3 ON public.websites_embeddings USING hnsw ((embedding::vector(1024)) vector_cosine_ops) WHERE model = 'BAAI/bge-m3';
-- No HNSW index for: BAAI/bge-multilingual-gemma2 (3584 dims), intfloat/e5-mistral-7b-instruct (4096 dims)

-- Potwierdzenie utworzenia tabel
SELECT 'Table websites_embeddings created successfully in lenie-ai database' as status;