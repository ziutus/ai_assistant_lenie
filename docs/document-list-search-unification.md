# Połączenie Document List i Search — pomiary przed zmianą interfejsu

Data: 2026-09-10. Status: propozycja do wdrożenia; zbieranie danych nie jest jeszcze uruchomione.

## Kierunek

Podstawą wspólnego panelu pozostaje Document List: wygląd wyników i filtrów,
zapamiętywanie ustawień, sortowanie „Najnowsze” / „Według priorytetu” oraz
operacje na dokumentach. Search rozszerza listę o dodatkowe kryteria i opcjonalną
interpretację zapytań przez AI. Najpierw zbieramy dane z obu istniejących widoków,
a dopiero na ich podstawie ustalamy widoczność i kolejność dodatkowych filtrów.

## Stan sprawdzony w kodzie

- `pages/list.tsx` i `hooks/useList.ts` korzystają z `GET /website_list`.
  Lista filtruje po frazie, typie, statusie przetwarzania, notatkach Obsidian,
  braku embeddingu, tematach i priorytecie. Domyślne sortowanie to `newest`,
  a rozmiar strony to 100. Domyślne ustawienia nowej przeglądarki w
  `services/storage.ts` to typ `link` i status `NEED_MANUAL_REVIEW`.
- Lista przywraca część ustawień z pamięci przeglądarki i parametrów URL.
  Sama obecność aktywnego filtra nie oznacza, że użytkownik go właśnie wybrał.
- Kontrolki `Strict` / `Similar` zmieniają stan interfejsu, ale `useList.ts`
  nie przekazuje `searchType` do API. Backend wykonuje dopasowanie fragmentu
  tekstu przez `ILIKE`. Pomiar wyboru `Similar` nie dowodzi użycia semantyki.
- `pages/search.tsx` i `hooks/useSearch.ts` korzystają z `POST /search`.
  Dostępne są zapytania naturalne, jawne kryteria oraz korekty interpretacji.
  Domyślny limit to 10; jawne kryteria mają domyślne sortowanie `relevance`.
- `search_interpretation_logs` zapisuje próby interpretacji zapytań naturalnych
  i feedback. Nie jest pełną historią użycia listy i jawnych kryteriów.

## Proponowana tabela pomocnicza: `document_browse_events`

Jeden rekord opisuje wykonaną akcję z kompletem zastosowanych kryteriów.
Nie tworzymy rekordu dla każdego wpisanego znaku ani niezastosowanego wyboru.

| Pole | Proponowany typ | Znaczenie |
|---|---|---|
| `id` | bigint, PK | Identyfikator wpisu |
| `event_id` | UUID, unique | Deduplikacja ponownego przesłania tego samego zdarzenia |
| `created_at` | timestamptz | Czas zapisu po stronie serwera |
| `schema_version` | smallint | Wersja formatu pomiarów |
| `source_view` | text | `document_list` albo `search` |
| `action` | text | `initial_load`, `submit`, `filter_change`, `sort_change`, `page_change`, `page_size_change`, `clear`, `refresh`, `correction` |
| `session_id` | UUID | Losowy identyfikator sesji interfejsu, bez klucza API |
| `browse_id` | UUID | Wspólny identyfikator wyszukiwania i jego kolejnych stron |
| `query_text` | text, nullable | Pełna zastosowana fraza / zapytanie naturalne, z limitem długości |
| `effective_query` | text, nullable | Fraza faktycznie przekazana do wyszukiwarki po interpretacji |
| `requested_mode` | text | Tryb wybrany w interfejsie, np. `strict`, `similar`, `natural`, `explicit` |
| `execution_mode` | text | Faktyczna ścieżka wyszukiwania, ustalana przez backend |
| `filters` | jsonb | Znormalizowane, faktycznie zastosowane filtry wraz z wartościami |
| `changed_fields` | jsonb | Nazwy pól świadomie zmienionych i zastosowanych w tej akcji |
| `criteria_origin` | jsonb | Pochodzenie kryteriów: domyślne, zapamiętane, URL, ręczne, AI |
| `sort` | text | Faktycznie zastosowane sortowanie |
| `page_size`, `offset` | integer | Rozmiar strony i przesunięcie liczone w rekordach |
| `returned_count` | integer, nullable | Liczba pozycji na zwróconej stronie |
| `total_count` | integer, nullable | Pełna liczba wyników, tylko jeśli backend już ją zna |
| `has_more` | boolean, nullable | Informacja o kolejnej stronie |
| `outcome` | text | `success`, `error`, `clarification_required` |
| `duration_ms` | integer, nullable | Czas wykonania zapytania |
| `interpretation_log_id` | bigint, nullable, FK | Powiązanie z istniejącym logiem AI; `ON DELETE SET NULL` |
| `expires_at` | timestamptz | Retencja: proponowane 90 dni, zgodnie z kierunkiem ADR-017 |

Frazy zapisujemy w całości; raport najczęstszych wyrazów można wyprowadzić
później. Zachowanie fraz pozwala rozpoznać nazwy własne i zapytania wielowyrazowe.
W raportach normalizujemy wielkość liter i nadmiarowe odstępy, zachowując
oryginalny tekst w logu. JSON filtrów wymaga jawnej listy dozwolonych pól,
walidacji typów i ograniczeń długości. Znaczenie „wszystkie tematy”, „bez tematów”
oraz pustego świadomego wyboru musi pozostać rozróżnialne.

## Zasady pomiaru

1. Frontend przekazuje kontekst akcji; backend zapisuje zastosowane kryteria
   i rezultat. Wywołania innych klientów API bez kontekstu UI nie trafiają do
   statystyk paneli. Samo `/search/parse` nie jest wykonaniem wyszukiwania.
2. Zapis logu ma osobną, krótką transakcję. Awaria pomiarów nie blokuje listy
   ani wyszukiwania. Ograniczamy czas oczekiwania na zapis; nie dodajemy
   zapytań zliczających wszystkie wyniki wyszukiwania hybrydowego.
3. Otwarcie widoku, odświeżenie po operacji na dokumencie i paginacja są
   oznaczane osobno. Ranking fraz i filtrów obejmuje świadome zastosowanie
   kryteriów, bez nabijania liczników przez kolejne strony i odświeżenia.
4. Powtórzenie transmisji zachowuje `event_id`; nowa świadoma akcja dostaje
   nowy identyfikator, nawet gdy ma identyczną frazę.
5. Dla zapytania naturalnego odróżniamy filtry wygenerowane przez AI od
   ręcznych wyborów i późniejszych korekt. Nie liczymy filtra AI jako
   świadomego użycia jego kontrolki.
6. Zapisujemy również błędy i potrzebę doprecyzowania. Brak wyników oznacza
   udane wyszukiwanie z pustą pierwszą stroną; błąd i pusta dalsza strona
   nie są zapytaniami bez wyników.
7. Retencja wymaga działającego zadania usuwającego wygasłe rekordy.
   Dostęp do fraz pozostaje w chronionym backendzie Lenie.

## Raport do decyzji o wyglądzie

Pierwszy przegląd po 2–4 tygodniach zwykłej pracy; to termin roboczy, nie próg
statystyczny. Raport pokazuje też liczbę sesji i zdarzeń. Przy małej liczbie
użyć Search nie usuwamy jego funkcji wyłącznie na podstawie niskiego wyniku.

| Pytanie | Miara | Decyzja, którą wspiera |
|---|---|---|
| Jak zwykle zaczyna się praca? | Otwarcia paneli, odtworzone kryteria, sesje | Widok początkowy i zachowanie pamięci ustawień |
| Czego szukamy? | Frazy i wyrazy, z podziałem na panel i tryb | Wspólne pole zapytania i ewentualne ostatnie frazy |
| Jakie filtry wybieramy? | Świadome zastosowania i wartości filtrów | Kolejność widocznych filtrów |
| Jakie filtry występują razem? | Najczęstsze zestawy zastosowanych kryteriów | Układ filtrów i ewentualne zapisane widoki |
| Jak porządkujemy listę? | Zastosowane zmiany sortowania | Zachowanie domyślnego sortowania listy |
| Kiedy wyszukiwanie nie pomaga? | Puste pierwsze strony, błędy, korekty | Poprawa wyszukiwania przed eksponowaniem jego funkcji |
| Jak przeglądamy wyniki? | Głębokość paginacji i rozmiary stron | Paginacja wspólnego panelu |

## Etapy i kryteria odbioru

1. **Instrumentacja:** migracja Alembic, model, odporny na błędy zapis,
   kontekst akcji w obu widokach, zadanie retencji i raport odczytowy.
   Testy obejmują oba panele, wyszukiwanie jawne/naturalne, korektę,
   paginację, odtworzenie ustawień, deduplikację, błąd zapisu i retencję.
2. **Obserwacja:** zwykłe używanie dotychczasowych paneli; weryfikacja,
   że zapisane kryteria odpowiadają faktycznym żądaniom API i wynikom.
3. **Projekt połączonego panelu:** obecna lista jako baza, wspólne pole
   zapytania, dodatkowe filtry w rozwijanej sekcji, opcjonalna interpretacja AI.
   Domyślny układ i sortowanie wynikają z Document List. Trafność pozostaje
   dostępnym, jawnym wyborem dla wyszukiwania.
4. **Integracja:** przed zastąpieniem osobnego Search zachować jego potrzebne
   kryteria, korekty i linki. Sprawdzić zgodność filtrów listy z wyszukiwaniem;
   status, Obsidian, tematy i priorytety nie mogą zostać po cichu pominięte.

Plan nie wymaga reimportu dokumentów ani przebudowy embeddingów.
