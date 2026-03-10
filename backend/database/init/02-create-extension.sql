-- Przełączenie na bazę danych lenie-ai i instalacja rozszerzeń
\c "lenie-ai";

-- Instalacja rozszerzenia pgvector (vector similarity search)
CREATE EXTENSION IF NOT EXISTS vector;

-- Instalacja rozszerzenia unaccent (diacritic-insensitive search: Łódź → lodz, Michał → michal)
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Instalacja rozszerzenia pg_trgm (fuzzy matching via trigram similarity)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Sprawdzenie instalacji
SELECT 'Extensions pgvector, unaccent, pg_trgm installed successfully in lenie-ai database' as status;
