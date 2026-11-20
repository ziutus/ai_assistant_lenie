# Wyszukiwanie: kontrakt i słownik nazw

Opis bieżącego stanu wyszukiwania w języku naturalnym (Bielik → jawne, walidowane
kryteria → SQL + pgvector). Przebudowę zrealizowano w etapach 0-12 (zamknięta
2026-07-19; wcześniejszy plan etapów i dziennik postępu są w historii gita).
Decyzje zakresu: [ADR-017](adr/adr-017-search-rebuild-scope-decisions.md),
[ADR-020](adr/adr-020-search-indexing-deferred.md),
[ADR-021](adr/adr-021-search-terms-generated-by-bielik.md). Działanie hybrydy,
scoring i pomiary wydajności: [search-hybrid.md](search-hybrid.md). Baseline modelu:
[search-rebuild-bielik-baseline.md](search-rebuild-bielik-baseline.md).

## Zasady architektoniczne

1. LLM interpretuje tekst, ale nie generuje SQL i nie zna identyfikatorów bazy.
2. Wynik LLM zawsze przechodzi walidację i normalizację backendu.
3. Filtry SQL są nakładane przed `LIMIT` zarówno dla wyników leksykalnych, jak i wektorowych.
4. Awaria Bielika nie blokuje wyszukiwania: całe zdanie staje się zapytaniem fallbackowym.
5. Frontend zawsze pokazuje interpretację albo informację o fallbacku i pozwala ją poprawić.
6. Surowa odpowiedź modelu, wynik walidacji, błędy i korekty są zapisywane i audytowalne.
7. Każde wywołanie LLM zapisuje użycie i koszt przez wspólny mechanizm
   (`llm_usage_logs`, opis w [backend/library/CLAUDE.md](../backend/library/CLAUDE.md)),
   a nie w modułach domenowych.

## Endpointy

Implementacja: `backend/library/search_routes.py`.

- `POST /search/parse` — zdanie → interpretacja, bez wyszukiwania (testy, podgląd, ponowna interpretacja).
- `POST /search` — albo `{"natural_query": "..."}`, albo jawne kryteria bez wywołania LLM:
  `{"query", "filters": {...}, "limit", "offset", "sort"}`. Odpowiedź: `search_id`,
  interpretacja, wyniki, paginacja. To jedyny endpoint wyszukiwania (`/website_similar` usunięty).
- `POST /search/<search_id>/feedback` — `correct` / `partially_correct` / `incorrect`,
  komentarz i opcjonalny poprawiony obiekt zapytania.

Przykład: „niewolnictwo w afryce miedzy od konca II wojny swiatowej" →
`query: "niewolnictwo w Afryce"`, `subject_period_start_year: 1945`,
`interpretation_summary`, `warnings`.

## Interpretacja Bielika

Typ `ParsedSearchQuery` (`backend/library/search/types.py`, płaski, odzwierciedla JSON
zwracany przez model): `query`, `author_name`, `publisher_name`/`publisher_domain`,
`discovery_source_name`, `collection_name`, `published_on_from/to`,
`ingested_at_from/to`, `subject_period_start/end_year`, `temporal_expression`,
`document_types`, `languages`, `sort`, `interpretation_summary`, `warnings`,
`clarification_required`/`clarification_question`, `model_confidence`.
Pole z kodu jest źródłem prawdy; ta lista może się starzeć.

Nazwy autorów, portali, kolekcji i kanałów pozyskania backend rozwiązuje na
identyfikatory (`library/search/name_resolution.py`). Niejednoznaczne dopasowanie
daje prośbę o doprecyzowanie, nie losowy wybór.

## Rejestr interpretacji

Tabela `search_interpretation_logs`: surowe zapytanie, model, wersje parsera i promptu,
surowa odpowiedź, sparsowany JSON, `status` (`parsed`, `ambiguous`, `invalid_json`,
`validation_error`, `llm_error`, `fallback`), kod i bezpieczny opis błędu, czasy,
liczba wyników, feedback użytkownika i poprawiona interpretacja. Wiersze wygasają po
90 dniach (`expires_at`), bo surowe zapytania mogą zawierać dane prywatne. Do pól
widocznych dla frontendu nie trafiają klucze API, nagłówki ani stack trace. Szczegóły
tabeli: [backend/database/CLAUDE.md](../backend/database/CLAUDE.md).

## Słownik nazw domenowych

Fizyczne rename'y zostały wykonane (etap 11). Dawne nazwy → obecne:

| Dawniej | Obecnie | Uwagi |
|---|---|---|
| `web_documents` / `WebDocument` | `documents` / `Document` | wszystkie typy dokumentów |
| `websites_embeddings` | `document_embeddings` | |
| `website_id` | `document_id` | FK i klucze JSON wyników |
| `source` | `discovery_source_id` | kanał pozyskania, nie portal; format wire (`/url_add`, `/website_save`, `/website_get`) zachowuje klucz `source` (zgodność z wtyczką Chrome) |
| `sources` | `discovery_sources` | ścieżka API `/sources` bez zmian |
| `date_from` / `date_from_source` | `published_on` / `published_on_method` | |
| `author` / `author_source` | `byline` / `byline_method` | autorzy relacyjnie w `document_persons` |
| `project` | `collection_id` | tabela `collections`; kolumna `project` była w 100% pusta (ADR-017); dokument należy do najwyżej jednej kolekcji |
| `created_at` dokumentu | `ingested_at` | data dodania do Lenie |
| `document_state` / `document_state_error` | `processing_status` / `processing_error_code` | tabele słownikowe `processing_status_types`, `processing_error_types` |
| `period_from/to` | `subject_period_start/end_year` | okres, którego dotyczy treść |
| `website_similar` | `POST /search` | |
| `uuid` | **zostaje `uuid`** | świadome odstępstwo od `public_id` (2026-07-19): rename złamałby konwencję notatek Obsidian („Lenie AI uuid=...") |

Portal publikacji jest osobnym pojęciem od `discovery_source` i `information_sources`:
dokument ma `publisher_id`, a domeny wydawcy leżą w `publisher_domains`.
