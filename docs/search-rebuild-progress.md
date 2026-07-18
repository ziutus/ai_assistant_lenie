# Dziennik postępu — przebudowa wyszukiwania

Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md)
Nowe wpisy dopisywać NA GÓRZE.

---

## 2026-07-18 — Etap 1 (typy domenowe wyszukiwania) — UKOŃCZONY

**Zakres wykonany:**

- Nowy pakiet `backend/library/search/` (`types.py`): zamrożone dataclass walidowane w `__post_init__` —
  niepoprawnego obiektu nie da się skonstruować (`SearchQueryValidationError` z nazwą pola).
  - `ParsedSearchQuery` — pełny model z sekcji 5 planu (nowe nazwy domenowe: `published_on_*`,
    `ingested_at_*`, `subject_period_*_year`, `publisher_*`, `discovery_source_name`, `collection_name`);
    `interpretation_summary` wymagane; `clarification_question` tylko przy `clarification_required=True`;
    `to_filters()` produkuje `SearchFilters`.
  - `SearchFilters` — jedyne źródło reguł walidacji pól filtrów (współdzielone przez `ParsedSearchQuery`);
    `published_on_*` wymaga czystego `date` (odrzuca `datetime`), lata p.n.e. jako ujemne
    w zakresie [-10000, 3000], `document_types` walidowane wobec `StalkerDocumentType`,
    języki `^[a-z]{2,3}$`, domena wydawcy regex + lowercase, odwrócone zakresy = błąd konstrukcji.
  - `SearchRequest` — dwa warianty z sekcji 4 planu (naturalne zdanie XOR jawne query/filtry),
    pusty request odrzucany (fixture edge-06), `limit` 1–100, `offset` ≥ 0, odrzucanie `bool` jako int.
  - `SearchFeedback` + enumy: `SearchSort`, `InterpretationStatus`, `FeedbackVerdict`, `ModelConfidence`.
  - `normalize_year_range`/`normalize_date_range`/`normalize_datetime_range` — swap odwróconego zakresu
    + polski warning (semantyka fixture edge-04/edge-05); do użycia przez parser w etapie 4/5
    PRZED konstrukcją obiektu.
- Bez zmian w LLM, bazie, `SearchService` i frontendzie (zgodnie z zakresem etapu).
- Dokumentacja: wpisy w `backend/library/CLAUDE.md` i `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_search_types.py`: 113 passed (każde pole: wartość poprawna, zły typ, granice;
  odwrócone zakresy; warianty requestu; frozen).
- Pełna suita `tests/unit/`: **1544 passed**; `uvx ruff check backend/`: czysty.

**Otwarte ryzyka:**

- Limity długości (`MAX_QUERY_LENGTH=1000`, `MAX_NAME_LENGTH=300`, `MAX_COMMENT_LENGTH=2000`) przyjęte
  arbitralnie — zsynchronizować z kontrolą długości `raw_query` w etapie 2 (tabela audytu).
- `SearchRequest` bez `natural_query` wymaga query LUB niepustych filtrów — wariant „lista wszystkiego"
  świadomie niedostępny z poziomu requestu (dostępny w `ParsedSearchQuery`); do rewizji przy etapie 8,
  jeśli endpoint ma wspierać przeglądanie bez kryteriów.
- Ryzyka z etapu 0 bez zmian (structured output Sherlocka, pokrycie `document_persons.role='author'`).

**Następny krok:** Etap 2 — audyt wyszukiwania i użycie LLM (migracje Alembic:
`search_interpretation_logs` + `llm_usage_logs`, ORM + repozytorium, retencja `expires_at` 90 dni
wg ADR-017, seed cennika CloudFerro, koszty wyłącznie `NUMERIC`/`Decimal`). Etap `M` — podzielić
na dwie sesje; migracje testować na bazie NAS.

## 2026-07-18 — Etap 0 (decyzje i baseline) — UKOŃCZONY

**Zakres wykonany:**

- Decyzje właściciela projektu (zapisane w [ADR-017](adr/adr-017-search-rebuild-scope-decisions.md)):
  1. Słownik nazw z sekcji 3 planu — zatwierdzony bez zmian.
  2. Kolekcja = relacja **1:N** (`collection_id`); pole `project` w bazie NAS jest w 100% puste (9220 dokumentów).
  3. Retencja `search_interpretation_logs` = **90 dni** (`expires_at = created_at + 90 dni`).
- Fixture ewaluacyjny: `backend/tests/fixtures/search_query_cases.json` — 43 polskie zapytania
  (temat, okres treści z p.n.e., data publikacji, data dodania, autor, portal, discovery source,
  typ dokumentu, język, kombinacje, prompt injection, fallback, clarification, odwrócone zakresy).
- Test przypinający schemat fixture: `backend/tests/unit/test_search_query_cases_fixture.py`.
- Baseline `/website_similar` na NAS (limit=10, 2 przebiegi × 3 zapytania): **5,9–7,0 s**,
  zdominowane przez generowanie embeddingu w CloudFerro. Klucz payloadu to `search`.
  Szczegóły w ADR-017.

**Testy uruchomione:**

- `tests/unit/test_search_service.py` + `tests/unit/test_similarity_search_orm.py`: 30 passed (baseline, main @ 2e8c112).
- `tests/unit/test_search_query_cases_fixture.py`: 9 passed.

**Otwarte ryzyka:**

- Sekcja 10 planu bez zmian (structured output w Sherlocku niezweryfikowany — do sprawdzenia w etapie 3;
  pokrycie `document_persons.role='author'` niezmierzone — istotne dla etapu 7).
- Książki nie mają dedykowanego typu dokumentu (w fixture przyjęto `text`) — do potwierdzenia
  przy implementacji parsera.

**Następny krok:** Etap 1 — typy domenowe wyszukiwania (`ParsedSearchQuery`, enumy, walidacja
dat/lat/limitów/odwróconych zakresów; nowe nazwy domenowe; bez zmian w LLM, bazie i frontendzie).
Warunek zakończenia: niepoprawnego obiektu nie da się przekazać do `SearchService`.
