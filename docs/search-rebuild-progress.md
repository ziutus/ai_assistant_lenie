# Dziennik postępu — przebudowa wyszukiwania

Plan: [search-rebuild-implementation-plan.md](search-rebuild-implementation-plan.md)
Nowe wpisy dopisywać NA GÓRZE.

---

## 2026-07-18 — Etap 9, sesja B (edycja filtrów i feedback) — ETAP 9 UKOŃCZONY

**Zakres wykonany:** panel korekty pozwala edytować temat i aktywne filtry oraz usuwać każdy
chip. „Szukaj z poprawionymi kryteriami” wysyła jawny `{query, filters, limit, sort}` do
`POST /search` bez `natural_query`, więc nie wywołuje LLM; dopiero po udanym search zapisuje
`partially_correct` z pełnym `corrected_query` do pierwotnego search_id. Przyciski Tak/Nie zapisują
feedback `correct`/`incorrect`. URL `mode=explicit&criteria=<JSON>&limit=N` round-tripuje wszystkie
jawne kryteria i po otwarciu wykonuje explicit search bez Bielika. Wyniki filter-only mają własną
etykietę i bezpiecznie obsługują brak text/similarity.

**Testy uruchomione:** TypeScript `npm run lint`: czysty; Vitest **11 passed** (5 plików);
produkcyjny `npm run build`: czysty, 312 modułów. Testy obejmują edycję/usunięcie chipów,
explicit payload bez natural_query/UI metadata i round-trip URL. E2E Flask+NAS: explicit search
→ 200; feedback partially_correct → 200; zapisany corrected_query ma query=`gospodarka` i rok
2004; rekord testowy usunięty (`cleanup=True`).

**Otwarte ryzyka:** criteria w URL jest czytelnym JSON-em i może być długie; nie umieszcza sekretów,
ale przy bardzo rozbudowanych filtrach warto później przejść na krótszy, wersjonowany codec.
UI umożliwia edycję/usunięcie filtrów rozpoznanych przez Bielika, ale nie ma jeszcze pickera do
dodawania całkiem nowego typu filtra, którego parser nie zwrócił.

**PR/merge:** PR **#298**, merge **9c82bb5**.

**Następny krok:** Etap 10 — baseline ewaluacji 43 prawdziwych zapytań na Bieliku z raportem
poprawności pól, latency, tokenów i kosztu.

## 2026-07-18 — Etap 9, sesja A (frontend interpretacji) — POŁOWA ETAPU

**Zakres wykonany:** `web_interface_react` przestawiony z legacy `/website_similar` na
`POST /search` z `{natural_query, limit}`. Hook `useSearch` przechowuje razem wyniki i pełny
`SearchResponse` (search_id, interpretation, status, fallback). Strona `/search` pokazuje panel
„Bielik zinterpretował zapytanie jako” z tematem, aktywnymi filtrami, podsumowaniem, warnings,
fallbackiem i pytaniem doprecyzowującym. Interpretacja pozostaje w stanie strony po odpowiedzi.
Legacy pola okresu/translate usunięto z naturalnego formularza, bo backend słusznie zabrania
mieszania natural_query z jawnymi filtrami; wrócą jako edytowalne filtry w sesji B.

**Testy uruchomione:** Vitest **7 passed** (3 pliki); `npm run build` czysty (TypeScript strict,
Vite: 310 modułów). Nowe testy przypinają payload natural_query bez legacy pól oraz widoczność
query/filtrów/warnings/fallback/clarification. Istniejący smoke test App emituje ostrzeżenia React
`act(...)` po asynchronicznym odświeżeniu listy, ale nie ma unhandled rejection i przechodzi.

**Otwarte ryzyka:** sesja A nie oferuje jeszcze korekty filtrów, feedbacku ani shareable URL dla
jawnych kryteriów — to dokładny zakres sesji B. Wyniki filter-only mają skromniejszy kształt niż
hybrydowe; komponent wyników będzie wymagał utwardzenia w 9B przy korektach do samego filtra.

**PR/merge:** PR **#297**, merge **ddad12c**.

**Następny krok:** Etap 9, sesja B — edytowalne/usuwalne filtry, ponowne wyszukiwanie bez LLM,
feedback z corrected_query i shareable URL jawnych filtrów.

## 2026-07-18 — Etap 8 (nowe endpointy wyszukiwania) — UKOŃCZONY

**Zakres wykonany:** nowy blueprint `library/search_routes.py`, zarejestrowany w `server.py`:
`POST /search/parse`, `POST /search`, `POST /search/<id>/feedback`. Requesty JSON są mapowane na
walidowane `SearchRequest`/`SearchFilters`/`SearchFeedback`; błędy kontraktu zwracają spójne 400.
Naturalne zapytanie korzysta z parsera i bezpiecznego fallbacku, jawne kryteria nie wywołują LLM.
Niejednoznaczne nazwy zwracają clarification i count bez uruchamiania search; awaria resolvera
jest logowana i nie daje 500. `SearchService.search()` obsługuje komplet filtrów, filter-only bez
embeddingu, hybrydową paginację i jawne sortowanie. Stary `/website_similar` pozostaje bez zmian.

**Testy uruchomione:** `tests/unit/`: **1826 passed**; `uvx ruff check backend/`: czysty.
`test_search_routes.py` pokrywa parse/search/feedback, natural/explicit/fallback, ambiguity,
błędy resolvera i bezpieczne 400/404/503. E2E Flask + Sherlock + NAS: `/search/parse` → 200,
search_id=9, rok 2004; jawne `/search` dla `HTTPS://UNKNOW.NEWS/` → dokumenty 461/460;
feedback → 200; audit i usage usunięte po teście.

**Otwarte ryzyka:** endpoint nie aktualizuje jeszcze `result_count/search_latency_ms` w już
utworzonym rekordzie audytu (pola pozostają nullable); można dodać przy dashboardzie etapu 12.
Głęboki offset hybrydowy zwiększa liczbę kandydatów i docelowo powinien przejść na cursor/keyset.

**PR/merge:** PR **#295**, merge **73cf356**.

**Następny krok:** Etap 9 — frontend interpretacji i edycji filtrów, w dwóch sesjach.

## 2026-07-18 — Etap 7, sesja B (autor i discovery source) — ETAP 7 UKOŃCZONY

**Zakres wykonany:** `build_document_filters()` obsługuje wszystkie cztery pola nazwowe.
Autor jest filtrowany przez `document_persons.role='author'`, `persons.canonical_name` i
`person_aliases.alias`; fizyczne `web_documents.author` służy jako byline fallback wyłącznie dla
dokumentów bez relacyjnego autora. `discovery_source_name` mapuje się na obecną tabelę `sources`
i `web_documents.source`; kod nie importuje ani nie odpytuje `information_sources`. Nowy
`search/name_resolution.py` jawnie zwraca 0/1/N autorów lub discovery sources i nie wystawia
pojedynczego id przy N>1. Fizycznych rename'ów nie wykonano (etap 11).

**Testy uruchomione:** `tests/unit/`: **1797 passed**; `uvx ruff check backend/`: czysty.
E2E NAS: autor `Jacek Losik` → 1 osoba i dokumenty 9245/476; discovery source
`https://unknow.news/` (zapytanie uppercase) → 1 i dokumenty 461/460/459; realna kolizja
`artur rubinstein` → 2 osoby (248, 265), pojedyncze id `None`. Sesja B nie zawiera migracji;
NAS pozostaje na zweryfikowanym w 7A head `f5a6b7c8d9e0`.

**Otwarte ryzyka:** fallback byline używa dopasowania substring dla legacy danych, więc mniej
precyzyjne przypadki mogą wymagać kuracji relacyjnych autorów. Rejestr zawiera realne duplikaty
osób (np. Artur Rubinstein); zgodnie z kontraktem są raportowane jako niejednoznaczne, nie scalane.

**PR/merge:** PR **#293**, merge **2a4d5cd**.

**Następny krok:** Etap 8 — nowe endpointy `POST /search/parse`, `POST /search` i feedback,
z jawną obsługą niejednoznacznych wyników resolverów.

## 2026-07-18 — Etap 7, sesja A (publisherzy i domeny) — UKOŃCZONA

**Zakres wykonany:** migracja `f5a6b7c8d9e0` tworzy `publishers`, globalnie unikalne
`publisher_domains`, indeksy i nullable `web_documents.publisher_id`; backfill bierze wyłącznie
hostname z `web_documents.url` (nigdy discovery `sources` ani `information_sources`). ORM dostał
`Publisher`/`PublisherDomain`. `publisher_registry.resolve_publisher()` zwraca jawne 0/1/N
dopasowań, a pojedynczy `publisher_id` tylko dla N=1. `build_document_filters()` obsługuje
`publisher_name`/`publisher_domain` przez podzapytania obejmujące wszystkie dopasowania — bez
losowego wyboru.

**Testy uruchomione:** `tests/unit/`: **1792 passed**; `uvx ruff check backend/`: czysty.
NAS: upgrade `e4f5a6b7c8d9 → f5a6b7c8d9e0`, downgrade, ponowny upgrade; head
`f5a6b7c8d9e0`. Backfill: 3904 publisherów/domen, 9219/9220 dokumentów przypiętych. E2E:
realna domena `00xbyte.github.io` → dokładnie 1; dwa transakcyjne publishery o tej samej nazwie
→ dokładnie 2 i `publisher_id=None`; rollback potwierdzony (0 śladów).

**Otwarte ryzyka:** bootstrapowa nazwa publishera jest domeną i wymaga późniejszej kuracji;
jeden dokument bez rozpoznawalnego hosta pozostaje bez publishera. `author_name` i
`discovery_source_name` nadal celowo rzucają `NotImplementedError` do sesji B.

**PR/merge:** PR **#292**, merge **828c4a1**.

**Następny krok:** etap 7, sesja B — autor przez `document_persons.role='author'` i aliasy z
fallbackiem do fizycznych pól `author`/`author_source` (docelowo byline/byline_method), oraz
semantyka discovery source oparta na obecnej tabeli `sources`, bez dotykania
`information_sources`.

## 2026-07-18 — Etap 6, sesja B (wyszukiwanie samymi filtrami, bez embeddingu) — ETAP 6 UKOŃCZONY

**Zakres wykonany:**

- `stalker_web_documents_db_postgresql.py` — nowa metoda `list_by_filters(filters, limit, offset,
  sort)`: czyste filtrowanie dokumentów bez frazy tekstowej i bez wywołania embeddingu. Używa
  TEGO SAMEGO `build_document_filters()` co `search_text()`/`get_similar()` z sesji A (trzy
  metody, jeden builder). Pusty `SearchFilters()` legalnie listuje wszystko, najnowsze pierwsze
  — zgodnie z filozofią „brak kryteriów = lista wszystkiego" już przyjętą w `ParsedSearchQuery`
  (etap 1). Sortowanie: `SearchSort.PUBLISHED_DESC/ASC` → `date_from`, `INGESTED_DESC` →
  `created_at DESC`, `RELEVANCE` → to samo co `INGESTED_DESC` (brak sygnału trafności bez frazy).
  Wynik jako uproszczony słownik (`website_id`, `title`, `url`, `document_type`, `project`,
  `language`, `date_from`, `created_at`, `similarity=None`, `search_match="filters_only"`).
- `library/search_service.py` — nowa metoda `SearchService.search_by_filters(filters, limit,
  offset, sort)`: cienki delegat do `repo.list_by_filters()`. **Nigdy nie wywołuje
  `embedding.get_embedding()`** — to jest właściwy warunek zakończenia sesji B („wyszukiwanie
  wyłącznie po filtrach bez generowania embeddingu"), zweryfikowany wprost testem
  `mock_get_embedding.assert_not_called()`.
- Dokumentacja: `backend/library/CLAUDE.md` (etap 6 oznaczony jako kompletny), `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_list_by_filters.py` (nowy, 16 testów): pusty filtr = brak `WHERE`, filtry
  stosowane przed `LIMIT`, każda wartość `SearchSort` mapuje na właściwą kolumnę/kierunek
  `ORDER BY` (w tym string `"published_desc"` zamiast enuma), `limit`/`offset` w SQL, kształt
  wynikowego słownika, `NotImplementedError` dla pól wymagających rozwiązania nazw, brak
  `session.commit()`.
- `tests/unit/test_search_service.py` — nowa klasa `TestSearchByFilters` (4 testy): delegacja
  do `repo.list_by_filters()` z poprawnymi argumentami, wartości domyślne, **embedding nigdy nie
  jest generowany**, pusty filtr jest dozwolony.
- Pełna suita `tests/unit/`: **1785 passed**; `uvx ruff check backend/`: czysty.
- **E2E na żywej bazie NAS**: `search_by_filters(SearchFilters())` zwróciło 5 najnowszych
  dokumentów; filtr `document_types=("webpage",)` zadziałał; sortowanie `PUBLISHED_DESC` dało
  posortowaną listę dat; filtr okresu 1939–1945 zwrócił dokładnie te same 2 dokumenty
  (9204, 9144) co w sesji A przez `search_similar()` — potwierdza spójność między trzema
  ścieżkami korzystającymi z tego samego buildera. Zapytania wykonały się natychmiastowo
  (brak oczekiwania na CloudFerro Sherlock/embedding) — namacalny dowód, że embedding
  rzeczywiście nie jest generowany.

**Otwarte ryzyka:**

- `search_by_filters()`/`list_by_filters()` nie mają jeszcze żadnego wywołującego z HTTP —
  podłączenie do endpointu to etap 8.
- `author_name`/`publisher_name`/`publisher_domain`/`discovery_source_name` nadal nieobsługiwane
  (`NotImplementedError`, dziedziczone z sesji A) — etap 7 to rozwiąże.
- Ranking i scoring `SearchService._merge_results()` pozostają bez zmian — `list_by_filters()`
  nie przechodzi przez ten kod wcale (nie ma czego scorować bez frazy), zgodnie z zakresem etapu.

**Warunek zakończenia etapu 6 (z planu) spełniony w całości**: lexical i vector search korzystają
z identycznych ograniczeń (sesja A, dowiedzione testem porównującym SQL), a wyszukiwanie
wyłącznie po filtrach nie generuje embeddingu (sesja B, dowiedzione testem `assert_not_called`
oraz obserwacją czasu wykonania na żywej bazie).

**Następny krok:** Etap 7 — autor, publisher i discovery source (`M`, rozbić na dwie sesje).
Sesja A: dodać `publishers`/`publisher_domains`, backfill domen z URL, rozwiązywanie
publisher name/domain → `publisher_id`. Sesja B: filtrowanie autora przez
`document_persons.role='author'` + aliasy (z fallbackiem do `byline`), `sources` →
`discovery_sources` w nowym kodzie. To rozwiąże `NotImplementedError` w `build_document_filters()`
dla czterech pól nazwowych.

## 2026-07-18 — Etap 6, sesja A (wspólny builder filtrów SQL) — POŁOWA ETAPU

**Zakres wykonany:**

- Nowy `library/search/sql_filters.py` — `build_document_filters(filters: SearchFilters)`:
  JEDEN builder zwracający listę predykatów SQLAlchemy przeciw kolumnom `WebDocument`,
  stosowany identycznie przez `search_text()` i `get_similar()`.
  - `collection_name` → `WebDocument.project` (dokładne dopasowanie; dziś to płaska kolumna
    string, nie tabela słownikowa — bezpieczne bez rozwiązywania nazw, w przeciwieństwie do
    autora/wydawcy).
  - `published_on_from/to` → `WebDocument.date_from`; `ingested_at_from/to` →
    `WebDocument.created_at`.
  - `document_types`/`languages` → klauzule `IN`.
  - `subject_period_start/end_year` → skorelowany podzapytanie `EXISTS` przeciw
    `document_time_periods` (ta sama semantyka „brak roku po dowolnej stronie = otwarty zakres"
    co poprzedni filtr pythonowy, teraz w SQL).
  - `author_name`/`publisher_name`/`publisher_domain`/`discovery_source_name` → **rzuca
    `NotImplementedError`** zamiast cicho ignorować (wymaga rozwiązania nazw na identyfikatory —
    to etap 7, jeszcze niezbudowany; cichy brak filtra byłby gorszym błędem niż głośny wyjątek).
- `stalker_web_documents_db_postgresql.py` — `search_text()` i `get_similar()` dostały nowy,
  addytywny parametr `filters: SearchFilters | None`, stosowany przez `build_document_filters()`
  PRZED `.limit()` (kolejność wywołań `.where()` w Pythonie nie wpływa na wygenerowany SQL —
  WHERE zawsze poprzedza LIMIT niezależnie od kolejności w łańcuchu). Stary parametr `project`
  zachowany bez zmian (kompatybilność wsteczna dla `test_code/embeddings_search.py`); oba się
  łączą przez AND, jeśli podane razem.
- `library/search_service.py` — `SearchService.search_similar()` (JEDYNA aktualnie żywa ścieżka
  wyszukiwania, obsługuje `/website_similar`) przepięta: buduje `SearchFilters` wewnętrznie
  z `project`/`period_from`/`period_to` i przekazuje do OBU wywołań repozytorium. Usunięto
  `_documents_in_period()` i filtr postprocessingowy w Pythonie — okres jest teraz filtrowany
  w SQL przed `LIMIT`, co naprawia realny błąd: poprzednio filtr okresu odrzucał kandydatów
  z JUŻ ograniczonej przez LIMIT listy, więc pasujące dokumenty spoza pierwszych N kandydatów
  nigdy nie miały szansy się pojawić. Odwrócony `period_from`/`period_to` jest zamieniany przez
  `normalize_year_range()` (nie odrzucany); rok spoza domeny (`MIN_SUBJECT_YEAR`/
  `MAX_SUBJECT_YEAR`) lub pusty string `project` degradują do braku filtra zamiast rzucać
  `SearchQueryValidationError` — ta metoda zawsze przyjmowała niezaufane parametry HTTP i musi
  nadal degradować się łagodnie, a nie zwracać 500.
- Leniwy re-eksport `build_document_filters` w `library/search/__init__.py`.
- Dokumentacja: `backend/library/CLAUDE.md`, `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_search_sql_filters.py` (nowy, 19 testów): każde pole `SearchFilters` mapuje
  na właściwy fragment SQL, `EXISTS`/korelacja po `web_documents.id`, semantyka otwartego zakresu,
  4 pola nierozwiązane rzucają `NotImplementedError`, wiele filtrów łączy się w wiele warunków.
- `tests/unit/test_repository_sql_filters.py` (nowy, 12 testów): **bezpośredni dowód warunku
  zakończenia etapu** — `search_text()` i `get_similar()` dają IDENTYCZNE fragmenty SQL dla tych
  samych filtrów (nie tylko „z konwencji", ale zweryfikowane porównaniem skompilowanego SQL);
  filtr pojawia się przed `LIMIT` w skompilowanym zapytaniu (indeks stringa); `project`+`filters`
  łączą się przez AND; brak filtrów = brak dodatkowych predykatów.
- `tests/unit/test_search_service.py` — przepisana klasa `TestPeriodFilter` (usunięte testy
  `_documents_in_period`, 6 nowych: okno okresu trafia jako `filters=`, brak okna = puste
  `SearchFilters()`, odwrócony zakres zamieniany, rok spoza domeny degraduje się bez wyjątku,
  pusty `project` degraduje się bez wyjątku) + zaktualizowane asercje `mock_similar.assert_called_
  once_with(..., filters=...)` zamiast `project=...`.
- Pełna suita `tests/unit/`: **1765 passed**; `uvx ruff check backend/`: czysty.
- **E2E na żywej bazie NAS** (jedyny scenariusz z realnymi danymi produkcyjnymi w całym planie
  do tej pory — to zmiana dotykająca JEDYNEGO aktualnie żywego endpointu wyszukiwania):
  `search_text()` z filtrem `document_types` działa na realnym schemacie; znaleziono realny
  wiersz `document_time_periods` (dok. 9144, 1975–2024, „współczesność") i potwierdzono, że
  filtr okresu zbudowany z tych samych granic faktycznie zwraca dokument będący właścicielem
  tego wiersza; `get_similar()` z filtrem `document_types` działa poprawnie na złączeniu
  z `pgvector`; pełne `search_similar('wojna', period 1939-1945)` zwróciło 1 trafny wynik
  (książka o kontekście historycznym pasującym do okresu) zamiast wcześniejszych 5 bez filtra —
  potwierdza, że SQL-owy filtr okresu faktycznie zawęża wyniki w praktyce, nie tylko w testach
  z mockiem.

**Otwarte ryzyka:**

- **Sesja B etapu 6 (NIEWYKONANA w tej sesji)**: „umożliwić wyszukiwanie wyłącznie po filtrach
  bez generowania embeddingu" — dziś każde wywołanie `search_similar()` nadal generuje embedding
  (nawet gdy interesują nas wyłącznie filtry, bez frazy tekstowej); potrzebna nowa metoda
  (np. `SearchService.search_by_filters()` + `WebsitesDBPostgreSQL.list_by_filters()`) omijająca
  całkowicie `embedding.get_embedding()`.
- `author_name`/`publisher_name`/`publisher_domain`/`discovery_source_name` pozostają
  nieobsługiwane (`NotImplementedError`) — żaden aktualny wywołujący ich nie ustawia, więc ryzyko
  jest czysto teoretyczne, ale blokuje pełne wykorzystanie `SearchFilters` do czasu etapu 7.
- Zgodność `languages` z konwencją zapisu w `web_documents.language` (zakładane małe litery,
  np. „pl"/„en") nie została jawnie zweryfikowana na danych NAS w tej sesji — do sprawdzenia,
  jeśli filtr językowy da nieoczekiwanie puste wyniki w przyszłości.
- Obecny ranking (`SearchService._merge_results()`) pozostał bez zmian, zgodnie z zakresem etapu.

**Następny krok:** Etap 6, sesja B — wyszukiwanie wyłącznie po filtrach (bez embeddingu):
nowa metoda w `SearchService` + `WebsitesDBPostgreSQL` zwracająca dokumenty pasujące do
`SearchFilters` bez frazy tekstowej, z sortowaniem (domyślnie `ingested_desc`). Etap `M`,
druga połowa.

## 2026-07-18 — Etap 5 (czas i okresy historyczne) — UKOŃCZONY

**Zakres wykonany:**

- Nowy `library/year_normalization.py` — `coerce_year(value, minimum, maximum)`: wydzielone
  z `time_periods.py`'s `_coerce_year` (BCE jako liczby ujemne, `bool` odrzucane mimo bycia
  podklasą `int`, digit-string coerced, poza zakresem → `None`, nigdy wyjątek). `time_periods.py`
  przepięty na tę funkcję (własne granice `MIN_YEAR=-10_000`/`MAX_YEAR=2_100` bez zmian — celowo
  NIE ujednolicone z granicami wyszukiwania, żeby nie sprzęgać dwóch niezależnych funkcji).
- Nowy `library/search/temporal.py`:
  - `TemporalRelation` (exact/before/after/between/around).
  - `HISTORICAL_ANCHORS` — mały wersjonowany słownik (`ANCHOR_DICTIONARY_VERSION="1"`) znanych
    punktów odniesienia (początek/koniec I i II wojny światowej, upadek muru berlińskiego,
    rozpad ZSRR, wejście Polski do UE/NATO, zamachy z 11 września itd.) z normalizacją
    diakrytyki/wielkości liter przez `unidecode`.
  - `resolve_anchor(text)` — dopasowanie tekstu do słownika, `None` gdy nierozpoznane (nigdy
    zgadywanie).
  - `resolve_relation(relation, year, year_end, span_years)` — deterministyczna arytmetyka:
    `exact`→(rok,rok); `before`→(None,rok) [rok DOTYCZY, nie jest wykluczony]; `after`→(rok,None);
    `between`→zamiana odwróconej kolejności przez `normalize_year_range` z etapu 1; `around`→
    ±`span_years` (domyślnie 5) z przycięciem do `MIN_SUBJECT_YEAR`/`MAX_SUBJECT_YEAR` i ZAWSZE
    ostrzeżeniem po polsku (reguła planu: oznaczać przybliżenia).
  - `enrich_subject_period(start_year, end_year, relation, anchor_text)` — funkcja bezpieczeństwa:
    wywoływana WYŁĄCZNIE gdy oba lata z LLM są `None`; jawny rok od LLM nigdy nie jest nadpisywany;
    `between` nigdy nie jest rozwiązywane z pojedynczej kotwicy (potrzebuje dwóch jawnych lat);
    nieznana kotwica zostawia granice `None` z ostrzeżeniem diagnostycznym zamiast zgadywania.
    Sygnatura dotyka WYŁĄCZNIE `subject_period_start_year`/`subject_period_end_year` — strukturalna
    gwarancja warunku zakończenia etapu (okres historyczny nie może stać się datą publikacji).
- `library/search/parser.py` — schemat JSON i prompt rozszerzone o dwa pola zapasowe:
  `subject_period_relation`, `subject_period_anchor_text` (oba wymagane w schemacie, nullable).
  Prompt instruuje: podaj jawny rok gdy go znasz, pola zapasowe wypełnij TYLKO gdy rozpoznajesz
  znany punkt odniesienia, ale nie jesteś pewien roku. Trzeci przykład w prompcie demonstruje
  wzorzec użycia (upadek muru berlińskiego → `relation="after"`, jawne lata `null`).
  `build_parsed_query()` woła `enrich_subject_period()` po normalizacji odwróconych zakresów;
  ostrzeżenie z rozstrzygnięcia kotwicy dołączane do `warnings` obok istniejących.
- Leniwe/bezpośrednie re-eksporty `library/search/temporal.py` w `library/search/__init__.py`
  (moduł lekki, bez sqlalchemy — eksport bezpośredni, nie przez `__getattr__`).
- Dokumentacja: `backend/library/CLAUDE.md`, `backend/tests/CLAUDE.md`.

**Testy uruchomione:**

- `tests/unit/test_year_normalization.py` (nowy, 13 testów).
- `tests/unit/test_search_temporal.py` (nowy, 30 testów): każda relacja, przycinanie granic,
  zamiana odwróconego `between`, każda gałąź `enrich_subject_period` (w tym „nigdy nie dotyka
  `published_on`/`ingested_at`” — zweryfikowane przez introspekcję sygnatury funkcji).
- `tests/unit/test_search_query_parser.py` — istniejące 30 testów przeszło BEZ ZMIAN (kompatybilność
  wsteczna: payloady bez nowych pól po prostu dostają `None`/`None` z `.get()`, `enrich_subject_period`
  od razu zwraca bez zmian, bo `start_year`/`end_year` są już ustawione) + nowa klasa
  `TestSubjectPeriodAnchorEnrichment` (5 testów): rozstrzygnięcie kotwicy, jawny rok nigdy nie
  nadpisywany, nierozpoznana kotwica, brak przecieku do `published_on`/`ingested_at`, pełny
  przepływ `parse_search_query()` end-to-end (zmockowany LLM).
- `tests/unit/test_time_periods.py` — bez zmian, przeszło (regresja po przepięciu na
  `coerce_year`).
- Pełna suita `tests/unit/`: **1734 passed**; `uvx ruff check backend/`: czysty.
- **E2E na żywym Sherlocku + bazie NAS** z rozszerzonym schematem (22 wymagane pola): 3 zapytania.
  1. Przykład z planu → `subject_period_start_year=1945` (LLM samo obliczyło, pola zapasowe
     puste — zgodnie z instrukcją promptu).
  2. „artykuly o gospodarce polski po wstapieniu do unii europejskiej” →
     `subject_period_start_year=2004` (LLM samo obliczyło).
  3. „cos o polityce po upadku muru berlinskiego” → **model faktycznie skorzystał z pola
     zapasowego** (zostawił `subject_period_start_year=null`, ustawił `subject_period_relation=
     "after"`, `subject_period_anchor_text="upadek muru berlinskiego"`); backend deterministycznie
     rozstrzygnął na **1989** z widocznym ostrzeżeniem „Rok ustalony na podstawie znanego
     wydarzenia: upadek muru berlińskiego = 1989.” — potwierdza, że mechanizm fallbacku działa
     naprawdę, nie tylko w testach z mockiem.
  Wszystkie 3 zostawiły dokładnie jeden wiersz audytu i jeden wiersz usage na NAS; posprzątane
  po teście.

**Otwarte ryzyka:**

- `HISTORICAL_ANCHORS` to na razie ~20 wpisów, tylko polskie/europejskie punkty odniesienia
  najczęściej pojawiające się w kontekście artykułów w bazie — rozbudowa słownika to naturalna
  praca bieżąca (bump `ANCHOR_DICTIONARY_VERSION` przy każdej zmianie).
- `resolve_anchor()` wymaga dokładnego dopasowania znormalizowanej frazy (bez fuzzy matching) —
  drobne odchylenia w sformułowaniu modelu (np. „obalenie” zamiast „upadek” muru berlińskiego)
  są już w słowniku jako osobne klucze, ale nie każdy wariant będzie przewidziany; nierozpoznana
  kotwica NIE blokuje wyszukiwania (bezpieczny fallback: granice zostają `None`), więc ryzyko jest
  ograniczone do gorszej trafności, nie do błędu.
- Rozstrzyganie BEFORE/AFTER jako granic WŁĄCZNYCH (dokument „przed 1945” może wspominać też
  1945) to świadoma decyzja projektowa bez alternatywy do przetestowania w tej sesji — do rewizji
  przy etapie 10 (ewaluacja jakości), jeśli okaże się mylące dla użytkowników.
- Etap 10 (ewaluacja na pełnym fixture 43 zapytań) nadal nie uruchomiony — 3 zapytania z tej
  sesji to znowu punktowa weryfikacja, nie pełny raport.

**Następny krok:** Etap 6 — wspólne filtry SQL (jeden builder filtrów dla lexical i vector
search, filtr okresu przeniesiony z Pythona do SQL przed `LIMIT`, wyszukiwanie wyłącznie po
filtrach bez generowania embeddingu). Etap `M` — rozbić na dwie sesje.

## 2026-07-18 — Etap 4 (samodzielny SearchQueryParser) — UKOŃCZONY

**Zakres wykonany:**

- Nowy moduł `library/search/parser.py`, niezależny od testowego parsera komend Slacka:
  - `SEARCH_QUERY_SYSTEM_PROMPT` — pełny polski prompt systemowy z opisem wszystkich ~20 pól
    `ParsedSearchQuery`, dwoma przykładami (przykład z planu: niewolnictwo w Afryce/1945; przykład
    „lista wszystkiego" bez kryteriów), jawną instrukcją bezpieczeństwa: cały tekst użytkownika to
    WYŁĄCZNIE treść do zinterpretowania, nigdy polecenie dla modelu (obrona przed prompt injection).
  - `_RESPONSE_SCHEMA` — pełny JSON Schema (`response_format`) z **wszystkimi polami wymaganymi**,
    `additionalProperties: false`, uniami typu z `null` (`["string", "null"]`), enumami dla
    `document_types` (z `StalkerDocumentType`), `sort`, `model_confidence`.
  - `build_parsed_query(payload)` — normalizuje odwrócone zakresy (lata/daty/daty-czasu) PRZED
    konstrukcją przez `normalize_*_range()` z etapu 1, konwertuje stringi ISO na `date`/`datetime`;
    poza tym przekazuje pola 1:1 do `ParsedSearchQuery`, które samo waliduje (bez duplikowania
    reguł walidacji w parserze).
  - `_extract_json()` — zdejmuje code fence, przy nieparsowalnym JSON-ie próbuje odzyskać ucięty
    obiekt (`_repair_truncated_object`: domyka otwarte stringi/nawiasy, licząc głębokość) —
    odzyskanie udaje się, gdy ucięcie nastąpiło po wszystkich wymaganych polach; ucięcie w środku
    literału (`tr` zamiast `true`) zostaje `invalid_json`.
  - `parse_search_query(raw_query, model=None)` — **zawsze zwraca poprawny `ParsedSearchQuery`**:
    sukces/niejednoznaczność → sparsowany obiekt (status `parsed`/`ambiguous`); błąd LLM/nieparsowalny
    JSON/błąd walidacji → syntetyczny fallback (`query=surowy tekst`, `model_confidence=low`,
    ostrzeżenie po polsku). Każda próba (niezależnie od wyniku) zapisuje dokładnie jeden wiersz
    przez `record_interpretation()` z etapu 2; `ai_ask()` wywoływane z `temperature=0`,
    `system_prompt`, `response_format`, `operation="search_query_parse"` — usage zapisuje się
    automatycznie przez centralny recorder z etapu 3, także przy wyjątku LLM.
  - `SearchQueryParseResult` — dataclass zwracany do wywołującego: `parsed_query`, `status`,
    `fallback_used`, `interpretation_log_id`, `model`, `raw_response`, `error_code`/`error_message`,
    `llm_latency_ms`, `usage`.
  - Leniwy re-eksport `parse_search_query`/`SearchQueryParseResult` w `library/search/__init__.py`.

**Testy uruchomione:**

- `tests/unit/test_search_query_parser.py` (nowy, 30 testów): przykład z planu (niewolnictwo/1945),
  przekazanie surowego tekstu do `ai_ask()` bez modyfikacji, prompt injection (tekst dociera
  bajt w bajt, system prompt nietknięty), niestandardowy model, domyślny model z configu,
  niejednoznaczność → `ambiguous`, pusty/`None` `response_text` → `invalid_json`, wyjątek LLM
  (timeout i ogólny) → `llm_error` z fallbackiem bez wyjątku, JSON w code fence, ucięty JSON
  odzyskiwalny i nieodzyskiwalny, odwrócone zakresy lat/dat zamieniane (nie odrzucane), nieznany
  typ dokumentu / zła literówka typu pola / zła data ISO / niespójna flaga doprecyzowania →
  `validation_error` z użytecznym fallbackiem, `build_parsed_query()` i `_fallback_query()`
  testowane też bezpośrednio, dokładnie jedno wywołanie `ai_ask()`/`record_interpretation()`
  na próbę (także przy błędzie).
- Pełna suita `tests/unit/`: **1680 passed**; `uvx ruff check backend/`: czysty.
- **E2E na żywym Sherlocku + bazie NAS** z PEŁNYM schematem (unie typu z `null`, tablice z enumami,
  20 wymaganych pól — nigdy wcześniej nie testowane na żywo, wcześniejsza sonda z etapu 3 używała
  schematu 2-polowego): 3 zapytania.
  1. Przykład z planu → `parsed`, `subject_period_start_year=1945`, `temporal_expression` po polsku
     z poprawnymi znakami diakrytycznymi mimo wejścia bez nich.
  2. „artykuly Jana Kowalskiego z onet.pl o wyborach z zeszlego miesiaca" → jednym wywołaniem
     poprawnie: `author_name="Jan Kowalski"`, `publisher_name="Onet.pl"`,
     `publisher_domain="onet.pl"`, `document_types=("webpage",)`, `languages=("pl",)`,
     `sort=published_desc`, `published_on_to` = koniec poprzedniego miesiąca.
  3. „cos zupelnie niejasnego xyz" → `ambiguous`, `clarification_required=True`,
     sensowne pytanie doprecyzowujące po polsku.
  Wszystkie 3 zostawiły dokładnie jeden wiersz w `search_interpretation_logs` i jeden w
  `llm_usage_logs` (`operation='search_query_parse'`, koszt ~0,001 EUR `estimated`);
  posprzątane po teście.

**Otwarte ryzyka:**

- `llm_usage_logs.search_interpretation_log_id` **nie jest wypełniane** — FK zostaje `NULL`.
  Wiązanie wymagałoby zapisu w dwóch krokach (najpierw `ai_ask()` bez znanego jeszcze
  `interpretation_log_id`, potem UPDATE wiersza usage po utworzeniu wiersza interpretacji) albo
  odwrócenia kolejności zapisów; świadomie odłożone — nie jest wymagane przez warunek zakończenia
  etapu 4, a `audit_repository`/`recorder` nie mają dziś funkcji do takiego UPDATE-u. Do rozważenia
  przy etapie 8 (endpoint) lub jako osobny mały PR.
- Prompt nie zawiera pełnego słownika kotwic historycznych (tylko przykład „koniec II wojny
  światowej = 1945") — pełny wersjonowany słownik to zakres etapu 5.
- `document_types`/`languages` w schemacie JSON nie są jeszcze rozwiązywane na relacje
  (`author_name`/`publisher_name`/`discovery_source_name`/`collection_name` to nadal tekst, zgodnie
  z sekcją 5 planu) — rozwiązanie nazw na identyfikatory to etap 7.
- Ewaluacja na pełnym fixture 43 zapytań (`tests/fixtures/search_query_cases.json`) z etapu 0 NIE
  została uruchomiona w tej sesji (to explicite etap 10) — dzisiejsze 3 zapytania to punktowa
  weryfikacja działania schematu na żywo, nie pełny raport jakości.
- Wersjonowanie promptu/parsera (`PARSER_VERSION="1"`, `PROMPT_VERSION="1"`) to na razie stałe
  literały bez mechanizmu bump — przy zmianie treści promptu trzeba pamiętać o ręcznym podniesieniu.

**Następny krok:** Etap 5 — czas i okresy historyczne: wydzielić wspólną normalizację lat
z `time_periods.py`, rozróżnić datę publikacji/datę dodania/okres treści (już rozróżnione
w typach z etapu 1, ale bez logiki relacji), dodać relacje `before`/`after`/`between`/`around`,
mały wersjonowany słownik kotwic (np. koniec II wojny światowej = 1945 — dziś tylko w przykładzie
promptu, nie w kodzie), oznaczać przybliżenia ostrzeżeniem. Etap `S`.

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
