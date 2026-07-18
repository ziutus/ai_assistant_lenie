# Dziennik postępu — przebudowa wyszukiwania

Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md)
Nowe wpisy dopisywać NA GÓRZE.

---

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
