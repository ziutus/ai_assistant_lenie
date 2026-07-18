# Dziennik postępu — przebudowa wyszukiwania

Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md)
Nowe wpisy dopisywać NA GÓRZE.

---

## 2026-07-18 — Etap 3b (sprzątanie usage w modułach domenowych) — UKOŃCZONY

**Zakres wykonany:**

- Nowy moduł `library/llm_usage/report.py` — `usage_report(usage)` kształtuje jedno wywołanie
  (`response.usage`, czyli `UsageRecord` z etapu 3) do słownika przyjaznego JSON-owi
  (`llm_calls`, `usage_log_ids`, `llm_tokens`, `llm_cost_amount` jako `str(Decimal)`,
  `llm_cost_currency`, `llm_cost_status`); `combine_usage_reports()` agreguje wiele takich
  słowników (tokeny sumowane gdy wszystkie znane; koszt sumowany TYLKO gdy wszystkie składniki
  mają znaną kwotę w tej samej walucie — inaczej `None`/`unknown`, nigdy cichego miksowania
  walut ani zera zamiast nieznanej ceny; mieszany status reported/estimated → `estimated`
  jako bezpieczniejszy). Bez importu sqlalchemy (duck typing na `usage`) — moduł działa też
  w lekkim środowisku uvx.
- `library/timeline_events.py` — usunięto `_response_usage()` (martwa sonda `cost_usd`/`cost`/
  `credits_used`, zawsze zwracała `None`) i `_combine_costs()`; `extract_fragment_events()`
  i `extract_document_events()` budują raporty przez `usage_report()`/`combine_usage_reports()`;
  wywołanie `ai_ask()` dostało `operation="timeline_event_extraction"`.
- `library/tones.py` — usunięty prywatny import `_response_usage` z `timeline_events`;
  `classify_fragment()` używa `usage_report()`; `ai_ask()` dostał
  `operation="tone_classification"`.
- `library/time_periods.py` — analogicznie; `ai_ask()` dostał
  `operation="time_period_classification"`.
- Skrypty CLI (`imports/extract_events.py`, `extract_tones.py`, `extract_time_periods.py`)
  bez zmian — dumpują cokolwiek jest w raporcie, nowe pola (`usage_log_ids`,
  `llm_cost_amount/currency/status`) po prostu się w nich pojawią zamiast starego `llm_cost`.
- Dokumentacja: `backend/library/CLAUDE.md` (opis `report.py`, aktualizacja wzmianki o etapie 3b
  przy `ai_ask()`), `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_llm_usage_report.py` (nowy, 11 testów): kształtowanie pojedynczego wywołania,
  agregacja tokenów/kosztu, mix walut nigdy nie sumowany, dowolny `unknown` zatruwa sumę,
  brakujący token zatruwa sumę tokenów, mieszany status → estimated, lista pusta, pojedynczy
  raport = passthrough.
- `tests/unit/test_timeline_events.py`, `test_tones.py`, `test_time_periods.py` zaktualizowane
  (mocki `ai_ask` w testach dostały `usage=fake_usage(...)` zamiast czytanego wcześniej
  `total_tokens=` bezpośrednio na obiekcie odpowiedzi) — 76 testów łącznie z nowym modułem.
- Pełna suita `tests/unit/`: **1650 passed**; `uvx ruff check backend/`: czysty.
- E2E na żywym Sherlocku + baza NAS: `tones.classify_fragment()` i `time_periods.classify_fragment()`
  na tym samym fragmencie o zakończeniu II wojny światowej — oba zwróciły niepuste
  `usage_log_ids`, `llm_cost_status="estimated"`, `llm_cost_currency="EUR"`; w bazie potwierdzono
  wiersze z `operation='tone_classification'`/`'time_period_classification'`; posprzątane po teście.

**Otwarte ryzyka:**

- `grep -rn "_response_usage\|_combine_costs"` w `backend/` daje tylko wzmiankę w docstringu
  `report.py` — zero żywego kodu odwołuje się do starych nazw (potwierdza warunek zakończenia
  etapu 3b z planu).
- `combine_usage_reports()` przy mieszanym statusie reported/estimated zwraca `estimated` —
  arbitralna decyzja projektowa (brak precyzyjniejszego statusu w enum `CostStatus` dla „część
  rekordów miała inny status"); nieistotne dziś, bo żaden provider w tych trzech modułach nie
  raportuje kosztu (`reported`), tylko lokalna estymacja Bielika.
- `imports/extract_events.py`/`extract_tones.py`/`extract_time_periods.py` nadal nie mają testów
  jednostkowych na kształt wypisywanego JSON-a (nie było ich też przed tą sesją) — zmiana pól
  raportu jest więc niezweryfikowana testem na poziomie CLI, tylko przez testy modułów
  bibliotecznych i E2E ręczne.

**Następny krok:** Etap 4 — samodzielny `SearchQueryParser` (nowy moduł niezależny od
testowego parsera komend Slacka, polski prompt systemowy z pełnym schematem, walidacja/
normalizacja odpowiedzi Bielika przez `ParsedSearchQuery` z etapu 1, fallback do surowej frazy,
zapis każdej próby do `search_interpretation_logs` przez `record_interpretation()` z etapu 2,
`ai_ask(..., operation="search_query_parse", ...)` z `system_prompt` i `response_format` json_schema
z etapu 3). Etap `M` — rozbić na dwie sesje.

## 2026-07-18 — Etap 3 (poprawa abstrakcji LLM) — UKOŃCZONY

**Zakres wykonany:**

- `library/api/cloudferro/sherlock/sherlock.py` — nowy parametr `response_format` przekazywany
  do klienta OpenAI SDK; `system_prompt` już istniał (bez zmian semantyki).
- `library/ai.py` — przepisany routing modeli na wewnętrzne closure `call()` na provider:
  - `system_prompt` jako osobny argument `ai_ask()`, wysyłany jako prawdziwa rola `system`
    (nigdy konkatenacja z tekstem użytkownika); wspierane providery: `cloudferro`, `arklabs`
    (dodano przekazanie do `arklabs_get_completion`, wcześniej ginęło); inny provider →
    `ValueError` przed jakimkolwiek wywołaniem sieciowym.
  - `response_format` jako osobny argument, przekazywany wyłącznie do `cloudferro` (Sherlock);
    inny provider → `ValueError`.
  - Ujednolicenie nazw pól tokenów: `prompt_tokens`/`completion_tokens` (OpenAI, Sherlock,
    ARK Labs) vs `input_tokens`/`output_tokens` (Bedrock) → jeden widok przed zapisem usage.
  - Po każdym wywołaniu (sukces i wyjątek) dokładnie jeden zapis przez
    `library.llm_usage.recorder.record_llm_usage()`; `latency_ms` mierzony przez `time.monotonic()`
    wokół wywołania providera. Zwrócony `UsageRecord` trafia do nowego atrybutu
    `AiResponse.usage` (tokeny, latency, `usage_log_id`, `CostEstimate` ze statusem).
    Awaria recordera (w tym `SystemExit` z `config_loader.require()` gdy brak configu DB —
    dodano jawne przechwycenie w `ai.py`, `recorder.py` i `audit_repository.py`, bo `SystemExit`
    NIE dziedziczy z `Exception`) jest logowana i połykana — nigdy nie wywala wywołania LLM.
  - Nowe parametry `operation` (domyślnie `"ai_ask"`) i `search_interpretation_log_id`
    przekazywane wprost do recordera (do użycia przez przyszły parser zapytań, etap 4).
- `library/models/ai_response.py` — dodany atrybut `usage` (docstring: koszt żyje WYŁĄCZNIE tu,
  zakaz dodawania `cost_usd`/`cost`/`credits_used` — sprzątanie sond w `timeline_events.py`
  to świadomie osobny etap 3b, nietknięty w tej sesji).
- `library/llm_usage/recorder.py` — `UsageRecord.latency_ms` (nowe pole), `except (SystemExit, Exception)`.
- `library/search/audit_repository.py` — `except (SystemExit, Exception)` w obu miejscach zapisu
  (ten sam powód co w recorderze).
- Sonda na żywym CloudFerro Sherlock (rozstrzyga ryzyko z sekcji 10 planu): `response_format`
  `{"type": "json_schema", ...}` jest respektowany (wymuszone klucze schematu w odpowiedzi),
  `{"type": "json_object"}` odrzucany HTTP 400 — structured output wymaga pełnego JSON Schema.
- Dokumentacja: `backend/library/CLAUDE.md` (pełny opis kontraktu `ai_ask()`), `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_ai.py` przepisany od zera (18 testów): propagacja parametrów, system_prompt
  jako osobna wiadomość (w tym odrzucenie dla OpenAI), response_format (w tym odrzucenie dla
  OpenAI), ujednolicenie tokenów Bedrock, dokładnie jeden zapis usage przy sukcesie i przy
  wyjątku, recorder failure/SystemExit nie psuje wywołania, nieznany model nie zapisuje usage,
  `AiResponse` bez atrybutów kosztu.
- `tests/unit/test_llm_usage_recorder.py` — dodany test `SystemExit` z `session_factory`
  (18 testów, było 17).
- Pełna suita `tests/unit/`: **1639 passed**; `uvx ruff check backend/`: czysty.
- Regresja modułów-konsumentów `ai_ask()` (`tones.py`, `time_periods.py`, `timeline_events.py`,
  `article_tagging.py`, `ai_intent_parser.py`): 121 passed, bez zmian w ich wywołaniach
  pozycyjnych — kompatybilne wstecznie.
- E2E na żywym Sherlocku + baza NAS (192.168.200.7:5434): `ai_ask()` z `system_prompt` +
  `response_format` json_schema → poprawny, wymuszony JSON; `response.usage.usage_log_id`
  ustawiony, koszt 0,0000476000 EUR `estimated` z seedu `cloudferro-bielik-2026-07-18`;
  w bazie dokładnie 1 rekord dla `operation='stage3_verify'`; posprzątane po teście.

**Otwarte ryzyka:**

- Etap 3b (sprzątanie `_response_usage()`/`_combine_costs()` w `timeline_events.py`, `tones.py`,
  `time_periods.py`) świadomie NIE wykonany w tej sesji — te moduły nadal sondują martwe
  atrybuty kosztu przez `getattr`, teraz jeszcze bardziej martwe (mają realne dane w
  `response.usage`, ale go nie czytają). Zgodnie z planem to następny krok.
- `arklabs_get_completion()` nie ma parametru `response_format` (tylko Sherlock go dostał —
  zgodne z zakresem etapu, ARK Labs nieprzetestowany na structured output).
- `operation`/`search_interpretation_log_id` w `ai_ask()` nie są jeszcze używane przez żadnego
  wywołującego (parser zapytań wyszukiwania to etap 4) — dziś każdy call domyślnie zapisuje
  `operation="ai_ask"`, co warto doprecyzować przy okazji etapu 3b (moduły domenowe powinny
  przekazywać własną nazwę operacji zamiast domyślnej).

**Następny krok:** Etap 3b — sprzątanie usage w modułach domenowych: `timeline_events.py`,
`tones.py`, `time_periods.py` mają czytać tokeny/koszt z `response.usage` zamiast z
`_response_usage()`/`_combine_costs()`; usunąć te funkcje i ich importy między modułami;
przy okazji nadać modułom sensowne wartości `operation=` w wywołaniach `ai_ask()`. Etap `S`.

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
