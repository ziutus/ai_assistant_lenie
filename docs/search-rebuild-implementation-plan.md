# Plan przebudowy wyszukiwania Lenie

Status: propozycja do review  
Zakres: PostgreSQL, backend Flask/SQLAlchemy, Bielik 11B, frontend React  
Poza zakresem: Slack bot i utrzymywanie zgodności jego testowego API

## 1. Cel

Użytkownik powinien móc wpisać luźne polskie zdanie, np.:

> niewolnictwo w afryce miedzy od konca II wojny swiatowej

Bielik ma zamienić je na jawny, walidowany zamiar wyszukania:

```json
{
  "query": "niewolnictwo w Afryce",
  "filters": {
    "subject_period_start_year": 1945,
    "subject_period_end_year": null
  },
  "interpretation_summary": "Niewolnictwo w Afryce od zakończenia II wojny światowej",
  "warnings": ["Nie podano końca okresu."],
  "clarification_required": false
}
```

Backend wykonuje deterministyczne zapytania SQL i pgvector. Frontend pokazuje, jakie kryteria ustawił Bielik, pozwala je poprawić, a błędy i korekty zapisuje w PostgreSQL.

## 2. Zasady architektoniczne

1. LLM interpretuje tekst, ale nie generuje SQL i nie zna identyfikatorów bazy.
2. Wynik LLM zawsze przechodzi walidację i normalizację backendu.
3. Filtry SQL są nakładane przed `LIMIT` zarówno dla wyników leksykalnych, jak i wektorowych.
4. Awaria Bielika nie blokuje wyszukiwania: całe zdanie staje się zapytaniem fallbackowym.
5. Frontend zawsze pokazuje interpretację lub informację o fallbacku.
6. Surowa odpowiedź modelu, wynik walidacji, błędy i korekty są wersjonowane i audytowalne.
7. Nowe nazwy domenowe są stosowane w API i nowym kodzie od początku. Fizyczne rename'y tabel i kolumn mogą nastąpić później, po ustabilizowaniu zachowania.
8. Każdy etap kończy się testami i commitem możliwym do niezależnego review.
9. Każde wywołanie LLM zapisuje użycie i koszt przez wspólny mechanizm niezależny od modelu i dostawcy.

## 3. Docelowe nazewnictwo

| Obecnie | Nazwa docelowa | Uwagi |
|---|---|---|
| `web_documents` | `documents` | wszystkie typy dokumentów — **zrobione fizycznie (Etap 11f, migracja `f7a8b9c0d1e2`)**: tabela + sekwencja + 10 indeksów + 7 constraintów |
| `WebDocument` | `Document` | model domenowy — **zrobione (Etap 11f)**: klasa ORM i interfejs TS w `shared/types` |
| `websites_embeddings` | `document_embeddings` | embedding dokumentu/chunka — **zrobione fizycznie (Etap 11e, migracja `e6f7a8b9c0d1`)** |
| `website_id` | `document_id` | FK i pole odpowiedzi — **zrobione fizycznie (Etap 11e)**: kolumna, ORM, klucze JSON wyników wyszukiwania, `shared/types`, frontendy |
| `source` | `discovery_source_id` | kanał pozyskania, nie portal — **zrobione fizycznie (Etap 11d, migracja `d5e6f7a8b9c0`)**; format wire (`/url_add`, `/website_save`, `/website_get`) świadomie zachowuje NAZWĘ pod kluczem `source` (zgodność z wtyczką Chrome, decyzja 2026-07-19) |
| `sources` | `discovery_sources` | tabela słownikowa — **zrobione fizycznie (Etap 11d)**; ścieżka API `/sources` bez zmian |
| `date_from` | `published_on` | data publikacji — **zrobione fizycznie (Etap 11a, migracja `a2b3c4d5e6f7`)** |
| `date_from_source` | `published_on_method` | manual/html/llm/import/url — **zrobione fizycznie (Etap 11a)**; dopuszczalne wartości na razie bez zmian (manual/llm) |
| `author` | `byline` | tekst prezentacyjny; autorzy relacyjnie w `document_persons` — **zrobione fizycznie (Etap 11b, migracja `b3c4d5e6f7a8`)** |
| `author_source` | `byline_method` | sposób ustalenia byline (manual/llm/html) — **zrobione fizycznie (Etap 11b)** |
| `project` | `collection_id` | kolekcja tematyczna — **zrobione fizycznie (Etap 11c, migracja `c4d5e6f7a8b9`)**: tabela `collections` + FK, kolumna `project` usunięta (była w 100% pusta, ADR-017) |
| `created_at` dokumentu | `ingested_at` | data dodania do Lenie — **zrobione fizycznie (Etap 11g cz. 2b, migracja `b9c0d1e2f3a4`)**; inne tabele zachowują własne `created_at` |
| `uuid` | `public_id` | publiczny stabilny identyfikator — **ŚWIADOME ODSTĘPSTWO (decyzja użytkownika 2026-07-19): zostaje `uuid`** — rename złamałby utrwaloną konwencję notatek Obsidian („Lenie AI uuid=...") |
| `document_state` | `processing_status` | stan pipeline'u — **zrobione fizycznie (Etap 11g cz. 2a, migracja `a8b9c0d1e2f3`)** wraz z tabelami słownikowymi `processing_status_types`/`processing_error_types` i kluczami JSON/parametrami wire |
| `document_state_error` | `processing_error_code` | kod błędu pipeline'u — **zrobione fizycznie (Etap 11g cz. 2a)** |
| `website_similar` | `search` | właściwy endpoint wyszukiwania |
| `period_from/to` | `subject_period_start/end_year` | okres, którego dotyczy treść — filtry `/search` od Etapu 1; **kolumny `document_time_periods` przemianowane fizycznie (Etap 11g cz. 2b)**; parametry legacy `/website_similar` znikną z endpointem w Etapie 12 |

Portal publikacji jest osobnym pojęciem od `discovery_source` i `information_sources`. Docelowo dokument ma `publisher_id`, a domeny wydawcy znajdują się w `publisher_domains`.

## 4. Docelowy kontrakt wyszukiwania

### `POST /search/parse`

Przyjmuje naturalne zdanie i zwraca interpretację bez wykonywania wyszukiwania. Endpoint jest potrzebny do testów, podglądu i ponownej interpretacji.

### `POST /search`

Akceptuje jeden z wariantów:

```json
{"natural_query": "teksty o niewolnictwie w Afryce po II wojnie światowej"}
```

albo jawne kryteria bez wywołania LLM:

```json
{
  "query": "niewolnictwo w Afryce",
  "filters": {"subject_period_start_year": 1945},
  "limit": 20,
  "offset": 0,
  "sort": "relevance"
}
```

Odpowiedź zawiera `search_id`, interpretację, wyniki i paginację.

### `POST /search/{search_id}/feedback`

Zapisuje `correct`, `partially_correct` albo `incorrect`, komentarz oraz opcjonalny poprawiony obiekt zapytania.

## 5. Model interpretacji Bielika

Minimalny typ `ParsedSearchQuery`:

```text
query: string|null
author_name: string|null
publisher_name: string|null
publisher_domain: string|null
discovery_source_name: string|null
collection_name: string|null
published_on_from/to: date|null
ingested_at_from/to: datetime|null
subject_period_start/end_year: integer|null
temporal_expression: string|null
document_types: string[]
languages: string[]
sort: relevance|published_desc|published_asc|ingested_desc
interpretation_summary: string
warnings: string[]
clarification_required: boolean
clarification_question: string|null
model_confidence: high|medium|low
```

Nazwy autorów, portali, kolekcji i kanałów pozyskania backend rozwiązuje na identyfikatory. Niejednoznaczne dopasowanie generuje prośbę o doprecyzowanie, a nie losowy wybór.

## 6. Rejestr interpretacji i błędów

Nowa tabela `search_interpretation_logs` przechowuje co najmniej:

- `raw_query`, model oraz wersję parsera i promptu;
- surową odpowiedź Bielika;
- sparsowany i znormalizowany JSON;
- status: `parsed`, `ambiguous`, `invalid_json`, `validation_error`, `llm_error`, `fallback`;
- kod i bezpieczny opis błędu;
- informację o fallbacku, czasach wykonania i liczbie wyników;
- feedback, komentarz i poprawioną interpretację użytkownika;
- znaczniki czasu.

Nie zapisujemy kluczy API, nagłówków ani stack trace w polach prezentowanych frontendowi. Stack trace pozostaje w logach aplikacji. Należy ustalić retencję, ponieważ surowe zapytania użytkownika mogą zawierać dane prywatne.

### 6.1. Wspólny rejestr użycia i kosztów LLM

Kosztów nie należy implementować wyłącznie w parserze wyszukiwania. Nowa tabela `llm_usage_logs` ma rejestrować każde wywołanie Bielika, a w przyszłości także innych modeli i dostawców.

Minimalny zakres rekordu:

- `id`, `request_id`/`correlation_id` i opcjonalny `search_interpretation_log_id`;
- `operation`, np. `search_query_parse`, `document_analysis`, `time_period_classification`;
- `provider`, `model`, opcjonalnie endpoint/deployment bez sekretów;
- `prompt_tokens`, `completion_tokens`, `total_tokens`;
- jednostki dostawcy, np. `credits_used`, jeżeli nie rozlicza tokenów;
- `pricing_mode`: `per_token`, `per_request`, `credits`, `subscription`, `free`, `unknown`;
- stawki wejścia/wyjścia, waluta, `pricing_version` i data obowiązywania cennika;
- `cost_amount`, `cost_currency` oraz `cost_status`: `reported`, `estimated`, `allocated`, `unknown`;
- czas wywołania, latency, sukces/błąd i data utworzenia.

Zasady:

1. Tokeny raportowane przez API są faktem pomiarowym i zapisujemy je nawet wtedy, gdy nie znamy ceny.
2. Nie zakładamy, że Bielik ma cenę per token. CloudFerro może być rozliczane abonamentem lub kredytami; wtedy koszt pojedynczego calla jest `unknown` albo `allocated`, zgodnie z konfiguracją.
3. Cennik jest wersjonowany. Późniejsza zmiana ceny nie może zmieniać historycznych rekordów.
4. Koszt raportowany przez dostawcę ma pierwszeństwo przed lokalną estymacją.
5. Brak danych o tokenach lub cenie nie może powodować błędu biznesowego; zapisujemy `cost_status='unknown'`.
6. Koszt jest liczony centralnie przy wywołaniu LLM, a nie ponownie w modułach domenowych. Moduły otrzymują identyfikator usage i gotowe podsumowanie.
7. `search_interpretation_logs` wskazuje powiązane rekordy usage, dzięki czemu koszt parsera można agregować bez duplikowania kwot.

Agregaty powinny umożliwiać raportowanie kosztu i tokenów według dnia, operacji, modelu, providera, statusu oraz wersji promptu. Dla abonamentu można opcjonalnie alokować miesięczny koszt proporcjonalnie do liczby tokenów/calli, ale wartość taka musi mieć status `allocated`, nie `reported`.

#### Potwierdzony cennik CloudFerro

Cennik przekazany przez właściciela projektu 2026-07-18:

| Provider | Model | Tokeny wejściowe / 1 mln | Tokeny wyjściowe / 1 mln | Waluta |
|---|---|---:|---:|---|
| CloudFerro Sherlock | `Bielik-11B-v3.0-Instruct` | 0,56 | 0,56 | EUR |
| CloudFerro Sherlock | `BAAI/bge-multilingual-gemma2` (embedding) | 0,50 netto | 0,50 netto | PLN |

Wersje cennika zapisać np. jako `cloudferro-bielik-2026-07-18` i `cloudferro-bge-2026-07-18`. Uwagi:

1. Cenniki są w **różnych walutach** (EUR i PLN). `llm_usage_logs.cost_currency` musi być zapisywane per rekord, a agregaty i dashboard nie mogą sumować kwot w różnych walutach bez jawnego przeliczenia. Kwota za embedding jest **netto** — ewentualne doliczanie VAT to decyzja raportu, nie zapisu wywołania.
2. Wywołania embeddingów (`sherlock_embedding.py`, w tym batche po 32 fragmenty) **wchodzą w zakres `llm_usage_logs`** z `operation='embedding_generation'`. W praktyce embedding rozlicza tylko tokeny wejściowe; pole tokenów wyjściowych zostaje 0.

Obliczenie dla jednego wywołania:

```text
input_cost_eur  = prompt_tokens     * 0.56 / 1_000_000
output_cost_eur = completion_tokens * 0.56 / 1_000_000
cost_eur        = input_cost_eur + output_cost_eur
```

Ponieważ stawki wejścia i wyjścia są obecnie równe, wynik jest równoważny `total_tokens * 0.56 / 1_000_000`, ale implementacja ma liczyć oba składniki oddzielnie. Dzięki temu zmiana jednej stawki nie wymaga przebudowy modelu danych.

Pieniądze przechowujemy jako `NUMERIC`, a obliczenia wykonujemy przez `Decimal`. W bazie należy zachować większą precyzję, np. `NUMERIC(18, 10)`, ponieważ koszt pojedynczego krótkiego zapytania będzie znacznie mniejszy niż jeden eurocent. Zaokrąglenie do prezentacji wykonuje frontend lub raport, nie zapis wywołania.

Dla tego modelu `pricing_mode='per_token'`, `cost_currency='EUR'`, a prawidłowo obliczony koszt lokalny ma `cost_status='estimated'`, chyba że CloudFerro zacznie zwracać w odpowiedzi wiążącą kwotę — wtedy zapisujemy ją jako `reported`.

## 7. Etapy implementacji

Szacunki są orientacyjne dla jednej osoby wspieranej przez model kodujący. Jedna sesja powinna trwać 45–120 minut. Etapy oznaczone `M` można rozbić na dwie sesje. Nie należy rozpoczynać kolejnego etapu, jeśli testy bieżącego nie przechodzą.

### Etap 0 — decyzje i baseline (`S`, 45–90 min)

Zakres:

- zatwierdzić słownik nazw z sekcji 3;
- ustalić, czy kolekcja jest relacją 1:N czy M:N;
- ustalić retencję logów wyszukiwania;
- spisać 30–50 reprezentatywnych polskich zapytań;
- zapisać obecne testy i czas odpowiedzi `/website_similar` jako baseline.

Rezultat: krótki ADR oraz fixture `search_query_cases` bez zmian zachowania aplikacji.

Warunek zakończenia: decyzje niezbędne do schematu są jawne; testy bazowe przechodzą.

### Etap 1 — typy domenowe wyszukiwania (`S`, 60–120 min)

Zakres:

- dodać typowane modele request/response i `ParsedSearchQuery`;
- dodać enumy statusów, sortowania i feedbacku;
- dodać walidację dat, lat, limitu, offsetu oraz odwróconych zakresów;
- używać nowych nazw domenowych, nawet jeśli ORM nadal mapuje stare nazwy SQL.

Bez zmian w LLM, bazie i frontendzie.

Testy: unit test każdego pola, błędnych typów i granic.

Warunek zakończenia: niepoprawnego obiektu nie można przekazać do `SearchService`.

### Etap 2 — audyt wyszukiwania i użycie LLM (`M`, 90–180 min)

Zakres:

- migracja Alembic tworząca `search_interpretation_logs` i indeksy;
- migracja tworząca ogólną tabelę `llm_usage_logs` oraz powiązanie z interpretacją wyszukiwania;
- model ORM oraz małe repozytorium zapisu/feedbacku;
- kontrola długości `raw_query`, odpowiedzi i komunikatu błędu;
- konfiguracja retencji lub przynajmniej pole `expires_at`.
- model cennika niezależny od providera i obsługę `reported/estimated/allocated/unknown`;
- seed cennika CloudFerro: Bielik 11B wejście i wyjście po 0,56 EUR / 1 mln tokenów, embedding `BAAI/bge-multilingual-gemma2` 0,50 PLN netto / 1 mln tokenów;
- agregację tokenów oraz kosztów bez używania typu `float` do pieniędzy.

Testy: zapis sukcesu, błędu, fallbacku i feedbacku; migracja upgrade/downgrade; koszt raportowany, estymowany, abonamentowy i nieznany; brak podwójnego naliczenia; dokładne obliczenie Bielika dla różnych liczb tokenów wejścia i wyjścia.

Warunek zakończenia: błędy mogą być zapisane bez wpływu na transakcję wyszukiwania, a każde testowe wywołanie LLM pozostawia dokładnie jeden rekord użycia.

### Etap 3 — poprawa abstrakcji LLM (`S`, 60–120 min)

Zakres:

- rozszerzyć `ai_ask()` o osobny `system_prompt`;
- przekazać go jako rolę systemową do Sherlocka;
- dodać opcjonalny structured output/JSON Schema, jeśli CloudFerro go obsługuje;
- przy braku wsparcia zachować ścisły parser JSON i walidację;
- ustawić temperaturę parsera na `0` lub najniższą wspieraną;
- ujednolicić mapowanie `prompt/input_tokens` oraz `completion/output_tokens` do jednego obiektu usage;
- po każdym callu zapisywać usage, latency i koszt przez centralny serwis;
- obsłużyć koszt raportowany przez providera, kredyty oraz lokalny cennik z wersją;
- usage dołączać do odpowiedzi jako nowy obiekt `response.usage` (tokeny, latency, `usage_log_id`, podsumowanie kosztu ze statusem); **nie dodawać** do `AiResponse` atrybutów `cost_usd`, `cost` ani `credits_used` — `_response_usage()` w `timeline_events.py` sonduje te nazwy przez `getattr` i dziś zawsze dostaje `None`; dodanie ich obudziłoby martwą ścieżkę jako drugie, niekontrolowane źródło kosztu;
- nie zmieniać pozostałych zastosowań `ai_ask()`.

Testy: poprawne role wiadomości, propagacja parametrów, zapis usage dla sukcesu i wyjątku, brak regresji innych modeli.

Warunek zakończenia: prompt systemowy nie jest konkatenowany z tekstem użytkownika.

### Etap 3b — sprzątanie usage w modułach domenowych (`S`, 45–90 min)

Wykonać zaraz po etapie 3, przed rozbudową parsera. Dziś `timeline_events.py` definiuje `_response_usage()` (sondowanie `cost_usd`/`cost`/`credits_used` po odpowiedzi — zawsze `None`) oraz `_combine_costs()`, a `tones.py` i `time_periods.py` importują te prywatne funkcje między modułami. Po etapie 3 jest to zbędna, myląca duplikacja.

Zakres:

- `timeline_events.py`, `tones.py`, `time_periods.py`: zamiast `_response_usage(response)` czytać tokeny z centralnego `response.usage`;
- w raportach diagnostycznych zastąpić lokalnie liczone `llm_cost` polami `usage_log_ids` oraz podsumowaniem z centralnego serwisu (koszt zawsze ze statusem `estimated`/`unknown`, nigdy liczony w module);
- usunąć `_response_usage()` i `_combine_costs()` z `timeline_events.py` oraz ich importy w pozostałych modułach;
- nie zmieniać logiki ekstrakcji ani promptów tych modułów.

Testy: raporty `extract_document_tones`, `extract_fragment_events` i klasyfikacji okresów zawierają tokeny i identyfikatory usage z centralnego serwisu; grep potwierdza brak sondowania atrybutów kosztu poza centralnym wrapperem.

Warunek zakończenia: jedyne miejsce liczące koszt LLM to centralny serwis; żaden moduł domenowy nie czyta atrybutów kosztu z obiektu odpowiedzi.

### Etap 4 — samodzielny `SearchQueryParser` (`M`, 90–180 min)

Zakres:

- nowy moduł niezależny od testowego parsera komend Slacka;
- polski prompt systemowy z pełnym schematem i przykładami;
- parsowanie, walidacja i normalizacja odpowiedzi Bielika;
- statusy błędów oraz fallback do surowej frazy;
- wersjonowanie promptu i parsera;
- zapis każdej próby do tabeli audytu.

Testy:

- mockowane odpowiedzi poprawne i błędne;
- brak odpowiedzi, timeout, code fence i ucięty JSON;
- prompt injection w tekście użytkownika;
- podane zapytanie o niewolnictwo i II wojnę światową.

Warunek zakończenia: parser zawsze zwraca poprawny obiekt domenowy lub jawny fallback.

### Etap 5 — czas i okresy historyczne (`S`, 60–120 min)

Zakres:

- wydzielić wspólną normalizację lat z obecnego `time_periods.py`;
- rozróżnić datę publikacji, datę dodania i okres treści;
- dodać relacje `before`, `after`, `between`, `around`;
- dodać mały wersjonowany słownik kotwic, np. koniec II wojny = 1945;
- zachować tekst `temporal_expression` do diagnostyki;
- oznaczać przybliżenia ostrzeżeniem.

Testy: p.n.e., n.e., wojny, dekady, niepełne zakresy, odwrócone lata.

Warunek zakończenia: okres historyczny nie może przypadkowo stać się datą publikacji.

### Etap 6 — wspólne filtry SQL (`M`, 90–180 min)

Zakres:

- wprowadzić jeden builder filtrów dla lexical i vector search;
- obsłużyć daty publikacji/dodania, okres treści, typ, język i obecną kolekcję/projekt;
- przenieść filtr okresu z Pythona do SQL przed `LIMIT`;
- umożliwić wyszukiwanie wyłącznie po filtrach bez generowania embeddingu;
- zachować obecny ranking na tym etapie.

Testy: każda kombinacja filtra oraz dowód, że filtr występuje przed limitem.

Warunek zakończenia: lexical i vector search korzystają z identycznych ograniczeń.

### Etap 7 — autor, publisher i discovery source (`M`, 120–240 min)

Podzielić na maksymalnie dwie sesje.

Sesja A:

- dodać `publishers` i `publisher_domains`;
- backfill domen z URL;
- dodać indeksy;
- rozwiązywać publisher name/domain do `publisher_id`.

Sesja B:

- filtrować autora przez `document_persons.role='author'` i aliasy;
- fallback do obecnego pola byline dla dokumentów nieznormalizowanych;
- zmienić `sources` na semantykę `discovery_sources` w nowym kodzie;
- nie utożsamiać żadnego z tych pojęć z `information_sources`.

Warunek zakończenia: backend potrafi zgłosić zero, jedno lub wiele dopasowań nazwy bez losowego wyboru.

### Etap 8 — nowe endpointy wyszukiwania (`S`, 60–120 min)

Zakres:

- `POST /search/parse`;
- `POST /search`;
- `POST /search/{id}/feedback`;
- odpowiedzi zawierające `search_id`, interpretację, warnings, fallback i wyniki;
- spójne HTTP 400 dla niepoprawnego requestu oraz odporność na awarię LLM;
- stare `/website_similar` pozostawić tymczasowo tylko do czasu migracji Reacta.

Testy kontraktowe endpointów i przypadków błędów.

Warunek zakończenia: pełny przepływ działa bez frontendu przez test client/curl.

### Etap 9 — frontend: interpretacja i edycja (`M`, 120–240 min)

Podzielić na maksymalnie dwie sesje.

Sesja A:

- wysłanie `natural_query` do nowego `/search`;
- panel „Bielik zinterpretował zapytanie jako”;
- widoczne query, filtry, warnings i informacja o fallbacku;
- zachowanie interpretacji w stanie strony.

Sesja B:

- edytowalne/usuwalne znaczniki filtrów;
- ponowne wyszukiwanie bez wywołania LLM;
- przyciski feedbacku;
- zapis `corrected_query` przy wyszukaniu po korekcie;
- shareable URL dla jawnych filtrów.

Warunek zakończenia: użytkownik zawsze wie, jakie opcje zastosowano, i może je poprawić.

### Etap 10 — ewaluacja prawdziwego Bielika (`S`, 60–120 min na iterację)

Zakres:

- uruchomić fixture z etapu 0 na prawdziwym Bieliku 11B;
- mierzyć poprawność JSON-u i poszczególnych pól;
- raportować tokeny, latency i koszt całego zestawu oraz średnio na zapytanie;
- pogrupować błędy według typu;
- poprawić prompt lub deterministyczny normalizer;
- nie dostrajać modelu przed zebraniem wystarczającej liczby korekt.

Warunek zakończenia pierwszej iteracji: raport baseline i lista najczęstszych błędów.

### Etap 11 — fizyczne rename'y schematu (`L`, seria sesji 60–180 min)

Ten etap wykonywać dopiero po ustabilizowaniu nowego `/search`. Nowe nazwy domenowe mogą wcześniej istnieć jako atrybuty ORM mapowane na stare kolumny.

Podetapy, każdy jako osobny commit:

1. `date_from/author/project/source` i odpowiadające pola provenance;
2. normalizacja `discovery_source_id` i `collection_id`;
3. `websites_embeddings.website_id` na `document_embeddings.document_id`;
4. `web_documents` na `documents` oraz aktualizacja wszystkich FK;
5. `document_state` i pozostałe pola pipeline'u;
6. aktualizacja init SQL, ORM, importerów, testów i dokumentacji;
7. usunięcie aliasów zgodności.

Po każdym podetapie: migracja, testy ORM/repository i kontrola aktualnego head Alembic.

Warunek zakończenia: w aktywnym kodzie i API nie pozostają nazwy `website_*`, `date_from` ani niejednoznaczne `source` dotyczące dokumentu.

**Status 2026-07-19: ETAP 11 ZAKOŃCZONY** (sesje 11a–11g, PR #304–#312) z trzema świadomymi,
udokumentowanymi odstępstwami: (1) `uuid` zostaje (konwencja Obsidian — decyzja użytkownika);
(2) pole wire `source` (nazwa) zostaje w `/url_add`/`/website_save`/`/website_get` (zgodność z
wtyczką Chrome — decyzja użytkownika), fizycznie jest `discovery_source_id`; (3) ścieżki URL
legacy `/website_*` istnieją do czasu usunięcia `/website_similar` i przeglądu API w Etapie 12.
Enum `StalkerDocumentStatus` i moduły `library/models/stalker_*` to wewnętrzne nazwy — nie były
częścią słownika.

### Etap 12 — wydajność i porządki (`M`, 90–180 min)

Zakres:

- `EXPLAIN ANALYZE` dla typowych zapytań;
- indeksy publisher/author/date/period;
- decyzja o PostgreSQL FTS + GIN zamiast obecnego szerokiego `ILIKE`;
- paginacja i stabilne sortowanie;
- usunięcie `/website_similar` i starego parsera komend, jeśli nie ma innych konsumentów;
- dashboard lub zapytania raportowe dla błędów interpretacji.
- dashboard kosztów LLM według modelu, providera, operacji i dnia oraz alert na brakujące dane pricingowe.

Warunek zakończenia: brak znanych pełnych skanów dla podstawowych filtrów i brak martwego API.

## 8. Proponowany rytm pracy przy limitach

- Jedna sesja: dokładnie jeden etap `S` albo połowa etapu `M`.
- Jeden dzień: maksymalnie dwa etapy `S` albo jeden `M`; pozostały czas na review i testy.
- Nie łączyć migracji schematu, zmiany promptu i UI w jednym commicie.
- Na końcu sesji zapisać: wykonany zakres, uruchomione testy, otwarte ryzyka i następny krok.
- Jeśli sesja kończy się przed testami, nie zaczynać następnego etapu; zostawić plan naprawczy.
- Etap 11 traktować jako osobny mini-projekt i nie rozpoczynać go w dniu zmian parsera/endpointu.

Przykładowe dni:

| Dzień | Zakres |
|---|---|
| 1 | Etap 0 i 1 |
| 2 | Etap 2 i 3 |
| 3 | Etap 3b + etap 4, część parsera |
| 4 | Etap 4 testy + etap 5 |
| 5 | Etap 6 |
| 6–7 | Etap 7 |
| 8 | Etap 8 |
| 9–10 | Etap 9 |
| 11 | Etap 10 i korekta promptu |
| później | Etapy 11–12, po jednym podetapie na sesję |

## 9. Kryteria akceptacji całego przedsięwzięcia

1. Przykładowe zapytanie ustawia temat `niewolnictwo w Afryce` oraz okres treści od 1945 roku.
2. Frontend pokazuje interpretację i każde zastosowane ograniczenie.
3. Użytkownik może usunąć/poprawić filtr bez kolejnego wywołania Bielika.
4. Awaria lub niepoprawny JSON Bielika uruchamia fallback i zostaje zapisana w bazie.
5. Feedback i poprawiona interpretacja są powiązane przez `search_id`.
6. Filtry działają przed `LIMIT` w obu ścieżkach wyszukiwania.
7. Wyszukiwanie bez frazy, wyłącznie po filtrach, nie generuje embeddingu.
8. Autor, portal, discovery source, data publikacji, data dodania i okres treści mają odrębne znaczenia.
9. Testowy korpus prawdziwego Bielika daje powtarzalny raport jakości.
10. Nowe API nie używa nazw `website_id`, `websites` ani `date_from`.
11. Każde wywołanie Bielika zapisuje tokeny i latency, a koszt ma jawny status `reported`, `estimated`, `allocated` albo `unknown`.
12. Można policzyć dzienne i miesięczne użycie oraz koszt według modelu i operacji bez podwójnego naliczania.
13. Koszt LLM jest liczony wyłącznie w centralnym serwisie; w kodzie nie ma modułowych funkcji typu `_response_usage`/`_combine_costs` ani sondowania atrybutów kosztu na obiekcie odpowiedzi.

## 10. Ryzyka wymagające review

- Czy CloudFerro Sherlock obsługuje `response_format/json_schema` dla używanego modelu?
- Czy `project` rzeczywiście jest pojedynczą kolekcją, czy potrzebna jest relacja M:N?
- Czy `information_sources` zawiera już wiarygodny publisher, czy publisher musi być osobną tabelą?
- Jaki procent dokumentów ma poprawne `document_persons.role='author'`, datę publikacji i okres treści?
- Czy przechowywanie surowych zapytań wymaga anonimizacji lub krótkiej retencji?
- Jak często i z jakiego źródła aktualizować potwierdzony cennik CloudFerro (Bielik: 0,56 EUR / 1 mln tokenów we/wy; embedding bge: 0,50 PLN netto / 1 mln tokenów)?
- Jak prezentować łączny koszt, skoro rekordy usage będą w EUR (Bielik), PLN (embedding) i USD (istniejący `TranscriptionLog` dla AssemblyAI)? Nie sumować walut bez jawnego przeliczenia.
- Czy dane `usage` z Sherlocka są zawsze dostępne również dla błędnych lub przerwanych odpowiedzi?
- Czy fizyczne rename'y powinny objąć cały backend jednocześnie, czy przez przejściowe mapowanie ORM?
- Czy 0 wyników oznacza błąd interpretacji, brak danych, czy zbyt restrykcyjny filtr? Nie należy automatycznie klasyfikować tego jako błąd.
