-- Przełączenie na bazę danych lenie-ai i instalacja rozszerzenia pgvector
\c "lenie-ai";

-- Instalacja rozszerzenia pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Sprawdzenie instalacji
SELECT 'Extension pgvector installed successfully in lenie-ai database' as status;
