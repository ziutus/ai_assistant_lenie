# Dziennik postępu — przebudowa wyszukiwania

Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md)
Nowe wpisy dopisywać NA GÓRZE.

---

## 2026-07-18 — Etap 2, sesja B (repozytorium audytu + recorder usage) — ETAP 2 UKOŃCZONY

**Zakres wykonany:**

- `library/llm_usage/recorder.py` — `record_llm_usage()`: JEDYNA ścieżka zapisu do `llm_usage_logs`
  (dokładnie jeden rekord na wywołanie LLM). Snapshot aktywnego wiersza `llm_pricing`
  (stawki + waluta + `pricing_version` FK), koszt przez `estimate_cost()`; koszt raportowany
  przez providera (Decimal + wymagana waluta) ma pierwszeństwo przed estymacją; brak ceny →
  `cost_status='unknown'` (nigdy błąd, nigdy 0). Tokeny od providera sanityzowane (złe wartości →
  NULL + warning, bez wyjątku); float dla pieniędzy (`reported_cost`, `credits_used`) →
  `PricingError` (błąd programisty). Własna sesja; awaria DB połknięta (`usage_log_id=None`,
  głośny log) — accounting nie może wywalić operacji biznesowej.
- `library/search/audit_repository.py` — `record_interpretation()` (wszystkie statusy
  `InterpretationStatus`; status `fallback` wymusza `fallback_used=True`; niepoprawny status →
  ValueError eager, przed sesją), `record_feedback()` (zapis i nadpisanie werdyktu/komentarza/
  `corrected_query`; brak wiersza → False), `delete_expired_interpretations()` (retencja 90 dni;
  jako operacja utrzymaniowa PROPAGUJE błędy DB), `parsed_query_to_dict()` (ParsedSearchQuery →
  JSON-safe dict dla JSONB: daty→ISO, enumy→value, tuple→list). Kontrola długości w warstwie
  zapisu: `raw_query`→`MAX_QUERY_LENGTH` (1000), `raw_response`→20 000, `error_message`→500,
  z widocznym `TRUNCATION_SUFFIX`. Zapisy we własnej sesji — awaria zapisu audytu nie psuje
  wyszukiwania (zwraca None/False).
- `__init__.py` obu pakietów: leniwe re-eksporty (PEP 562) — `library.search`/`library.llm_usage`
  importują się nadal bez sqlalchemy w lekkim środowisku uvx.
- Dokumentacja: `backend/library/CLAUDE.md`, `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_llm_usage_recorder.py` (17) + `tests/unit/test_search_audit_repository.py` (25):
  42 passed (mockowane sesje, bez DB — konwencja repo).
- Pełna suita `tests/unit/`: **1624 passed**; `uvx ruff check backend/`: czysty.
- E2E na bazie NAS (192.168.200.7:5434): pełny cykl `record_interpretation` → `record_feedback` →
  `record_llm_usage` (1000+500 tokenów → 0.0008400000 EUR `estimated` z seedu
  `cloudferro-bielik-2026-07-18`) → `delete_expired_interpretations` (0) → DELETE interpretacji
  potwierdza `ON DELETE SET NULL` na usage → cleanup; tabele po teście puste (0/0).

**Otwarte ryzyka:**

- `delete_expired_interpretations()` nie jest nigdzie wywoływane cyklicznie — podpiąć w etapie 12
  (job/cron) albo wywoływać przy okazji zapytań.
- `feedback_at` ustawiane przez `func.now()` (zegar DB) — spójne z `created_at`, ale wartość
  w obiekcie ORM przed odświeżeniem to wyrażenie SQL, nie datetime.
- Alokacja kosztu abonamentowego (`allocated`) i sumowanie między walutami (EUR/PLN/USD) —
  bez zmian, świadomie odłożone do etapu 12 (raporty).
- Warunek zakończenia etapu 2 spełniony: błędy zapisywane bez wpływu na transakcję wyszukiwania,
  jedno wywołanie LLM = jeden rekord usage.

**Następny krok:** Etap 3 — poprawa abstrakcji LLM (`ai_ask()` z osobnym `system_prompt`,
rola systemowa w Sherlocku, temperatura 0 dla parsera, structured output jeśli wspierany,
po każdym callu zapis usage przez `record_llm_usage()`, `response.usage` bez atrybutów
`cost_usd`/`cost`/`credits_used` na `AiResponse`). Etap `S` — jedna sesja.

## 2026-07-18 — Etap 2, sesja A (migracje audytu + cennik + koszty Decimal) — POŁOWA ETAPU

**Zakres wykonany:**

- Migracja `d3e4f5a6b7c8` — `search_interpretation_logs`: raw_query, wersje modelu/parsera/promptu,
  surowa odpowiedź, `parsed_query` JSONB, `status` (CHECK zgodny z `InterpretationStatus`),
  bezpieczny kod/opis błędu, latencje, feedback (`feedback_verdict` CHECK, komentarz,
  `corrected_query`), `expires_at NOT NULL DEFAULT now() + 90 dni` (ADR-017) + indeksy
  (created_at, status+created_at, expires_at).
- Migracja `e4f5a6b7c8d9` — `llm_pricing` (wersjonowany cennik, wiersze niemutowalne, częściowy
  unikalny indeks „jeden otwarty cennik na provider/model", seed CloudFerro:
  `cloudferro-bielik-2026-07-18` 0,56 EUR/1M we/wy, `cloudferro-bge-2026-07-18` 0,50 PLN netto/1M)
  oraz `llm_usage_logs` (operation/provider/model, tokeny jako fakt pomiarowy, `credits_used`,
  zdenormalizowany snapshot stawek + FK `pricing_version`, `cost_amount NUMERIC(18,10)`,
  `cost_currency`, `cost_status` CHECK reported/estimated/allocated/unknown, opcjonalne FK
  do interpretacji `ON DELETE SET NULL`, indeksy agregacyjne).
- ORM: `SearchInterpretationLog`, `LlmPricing`, `LlmUsageLog` w `library/db/models.py`
  (pieniądze jako `Decimal`/`Numeric`, nie float).
- Nowy pakiet `library/llm_usage/` (`pricing.py`): `estimate_cost()` — koszt liczony wyłącznie
  na `Decimal` (float dla stawki = `PricingError`), osobno składnik wejścia i wyjścia,
  kwantyzacja do 10 miejsc (skala kolumny), tryby nie-tokenowe → `UNKNOWN_COST`
  (brak ceny nigdy nie jest błędem biznesowym ani kosztem 0).
- Dokumentacja: `backend/database/CLAUDE.md` (sekcja 3 nowych tabel), `backend/library/CLAUDE.md`,
  `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_llm_usage_pricing.py` (25) + `tests/unit/test_search_audit_models.py` (13): 38 passed.
- Pełna suita `tests/unit/`: **1582 passed**; `uvx ruff check backend/`: czysty.
- Migracje na bazie NAS (192.168.200.7:5434): `upgrade head` → weryfikacja psql (schemat + seed) →
  `downgrade c2d3e4f5a6b7` (tabele znikają) → `upgrade head`; head = `e4f5a6b7c8d9`.
- ORM round-trip na NAS (insert interpretacji + usage z kosztem 0.0008400000 EUR `estimated`,
  `expires_at` = created_at + 90 dni) zakończony rollbackiem — nic nie zostało w bazie.

**Otwarte ryzyka:**

- Retencja 90 dni to na razie tylko `expires_at` + indeks — brak joba czyszczącego (do etapu 12
  lub prostego DELETE w sesji B).
- Kontrola długości `raw_query`/odpowiedzi/komunikatu błędu odłożona do repozytorium (sesja B) —
  kolumny są TEXT, limity z `library/search/types.py` (`MAX_QUERY_LENGTH=1000`) zastosuje warstwa zapisu.
- Alokacja kosztu abonamentowego (`allocated`) świadomie niezaimplementowana — `estimate_cost()`
  zwraca `UNKNOWN_COST` dla trybów nie-tokenowych; alokacja to raport (etap 12).
- Waluty per rekord (EUR/PLN/USD) — agregaty nie mogą sumować między walutami bez przeliczenia.

**Następny krok:** Etap 2, sesja B — repozytorium audytu (zapis sukcesu/błędu/fallbacku poza
transakcją wyszukiwania, kontrola długości pól, zapis i aktualizacja feedbacku, gwarancja
dokładnie jednego rekordu usage na wywołanie LLM) + testy zapisu wszystkich statusów.

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
