# Usługi zewnętrzne w systemie adresów kontaktów

Prywatna książka kontaktów (`backend/library/db/models.py:Address`/`ContactAddress`, `backend/library/contact_routes.py` sekcja `# --- addresses ---`) korzysta z dwóch niezależnych, zewnętrznych usług HTTP — geokodowania i weryfikacji rejestrowej. Ten dokument opisuje, która usługa robi co, dlaczego, i co świadomie odrzucono.

## LocationIQ — geokodowanie (współrzędne)

`backend/library/locationiq_client.py`, wywoływane przez `library/address_geocoding.py` (`POST /address/<id>/geocode`). Zamienia `format_address()` na `latitude`/`longitude`/`location` (punkt PostGIS). Już wcześniej używane w projekcie do weryfikacji miejsc z NER (`place_verification.py`) — ten sam klucz API, ten sam limit darmowego tieru.

**Ograniczenie, które trzeba pamiętać**: LocationIQ to geokoder, nie walidator. Dla nieistniejącego numeru budynku i tak zwróci najbliższy znany punkt na tej samej ulicy — udane geokodowanie **nie jest dowodem**, że dokładnie ten adres istnieje. Stąd osobna usługa poniżej.

## adresy.app — weryfikacja rejestrowa (czy adres naprawdę istnieje)

`backend/library/address_validation_client.py` + `address_validation.py` (`POST /address/<id>/validate`). Darmowe REST API (`https://api.adresy.app/api/v1/match`, bez klucza: 3 req/min — wystarczające dla ręcznego, pojedynczego klikania przycisku "✓ Zweryfikuj adres"), które **agreguje oficjalne polskie rejestry publiczne**: PRG (GUGiK), TERYT (GUS), Poczta Polska. Zwraca, czy konkretna kombinacja ulica+numer+miasto+kod pocztowy to realny, zarejestrowany punkt adresowy — z dokładnością do numeru budynku — czego LocationIQ nie gwarantuje.

**Ważna pułapka odkryta przy wdrożeniu (2026-09-20)**: rzeczywiste API zwraca `status="matched"` dla trafienia, nie `"found"` jak sugerowała dokumentacja użyta przy pierwszej implementacji (Codex, bez dostępu do sieci w sandboxie, zbudował klienta na podstawie dokumentacji i się pomylił). Efekt: żaden prawdziwy adres nigdy by się nie potwierdzał — wszystko lądowałoby w `unavailable`. Znalezione i naprawione przed scaleniem PR #706 przez ręczny test na żywym API. **Wniosek na przyszłość**: przy każdej integracji z zewnętrznym API zawsze zweryfikować prawdziwy kształt odpowiedzi ręcznym zapytaniem `curl` przed zaufaniem dokumentacji — szczególnie gdy implementację robi Codex w sandboxie bez dostępu do sieci.

`address_validation.py` dodatkowo **nie ufa samemu statusowi "matched" bezkrytycznie** — porównuje zwrócony `nr_budynku` z naszym `building_number`; różnica traktowana jest jako `unavailable` (rejestr mógł dopasować inny budynek na tej samej ulicy), nie jako fałszywe potwierdzenie.

## Konto adresy.app — wyższy limit zapytań

`https://adresy.app/oferta`: nawet plan **Free (0 zł/mies.) wymaga konta i klucza API** — bez klucza działa tylko surowy limit 3 zapytania/min na adres IP (opisany w `/api/`), z kontem na planie Free: **30 zapytań/min, 3000/mies.**, dalej bezpłatnie. Kod już to obsługuje: `address_validation_client.py` czyta opcjonalny `ADRESY_APP_API_KEY` z configu (ten sam mechanizm co `LOCATIONIQ_API_KEY`) i wysyła go jako nagłówek `X-API-Key`, gdy jest ustawiony — **brak klucza nie blokuje działania**, tylko ogranicza do wolniejszego, nieautoryzowanego tieru. Gdy konto powstanie: dodać `ADRESY_APP_API_KEY` do Vault (ten sam sposób co inne sekrety w tym projekcie) — bez zmian w kodzie.

## Fallback: OpenStreetMap / Overpass (dane społecznościowe, niższa pewność)

Gdy `adresy.app` nie potwierdzi adresu (`not_found`/`unavailable`), a adres ma już współrzędne z geokodowania, `POST /address/<id>/validate` dodatkowo próbuje wąskiego zapytania Overpass (`around:400m` wokół znanych współrzędnych — **nigdy** zapytania po całym mieście/`area`, sprawdzone na żywo: zapytanie po całej Łodzi przekroczyło 57 sekund i się nie powiodło, zapytanie promieniowe wykonuje się w sekundy). Motywacja: część danych adresowych w OSM (szczególnie dla Łodzi) jest **zaimportowana bezpośrednio z EMUiA** przez lokalnych mapowiczów (tag `source:addr="EMUiA (emuia.geoportal.gov.pl)"`) i czasem zawiera dokładnie ten poziom szczegółowości osiedlowej ("blok N" jako `addr:housename`), którego brakuje dopasowaniu `adresy.app`.

**Sprawdzony na żywo przypadek** (kontakt 367, adres "Bratysławska 15, blok 31, Łódź", który `adresy.app` nie potwierdził): Overpass znalazł dokładny budynek — `way`, `addr:housenumber="15"`, `addr:housename="blok 31"`, `addr:street="Bratysławska"`, prawdziwe współrzędne — ale **bez** `addr:postcode` na tym konkretnym budynku (sąsiednie budynki przy tej samej ulicy miały `94-039`).

**To zawsze dodatkowy, słabszy sygnał, nigdy zamiennik oficjalnej weryfikacji** — `Address.verified_at` reaguje wyłącznie na wynik `adresy.app`, nigdy na dopasowanie OSM. Sugerowany kod pocztowy z sąsiedniego budynku przy tej samej ulicy jest jawnie oznaczony jako "do potwierdzenia", nigdy cicho podstawiany jako pewny.

## Ręczna weryfikacja/poprawa adresu (gdy oba automatyczne źródła zawiodą)

Gdy ani `adresy.app`, ani fallback OSM nie dadzą pewnej odpowiedzi, przydatne strony do ręcznego sprawdzenia:
- **`https://adresy.app/`** — wyszukiwarka adresów PRG w przeglądarce (ten sam rejestr co API, czasem łatwiej ręcznie doprecyzować literówkę w interfejsie niż przez API).
- **`https://www.openstreetmap.org/`** — wyszukiwanie i podgląd mapy społecznościowej; widać też dokładne tagi budynku (np. `addr:housename`), jeśli ktoś kiedyś zmapował dany blok.
- **`https://mapy.geoportal.gov.pl/`** — oficjalna przeglądarka mapowa GUGiK (ten sam PRG/EMUiA, ale z interfejsem do ręcznego wyszukiwania punktu adresowego, gdy API CAPAP jest niedostępne — zob. sekcja poniżej).

## Odrzucona alternatywa: oficjalne API GUGiK (EMUiA / CAPAP FTS)

Sprawdzone i **świadomie odrzucone** 2026-09-20 — **nie próbować ponownie bez nowych informacji**:

- **EMUiA** (`emuia.gugik.gov.pl`) to aplikacja administracyjna dla urzędników gmin do prowadzenia rejestru — **nie ma własnego publicznego API do zapytań**, tylko interfejs do edycji przez uprawnionych użytkowników.
- **CAPAP FTS** (`capap.gugik.gov.pl/api/fts/`) — to prawdziwe, oficjalne REST/JSON API GUGiK zbudowane na danych PRG/EMUiA (geokodowanie, identyfikacja, odwrotne geokodowanie). Problem: **strona dokumentacji zwracała HTTP 403 Forbidden** przy próbie odczytu z sieci deweloperskiej (prawdopodobnie blokada geo/bot) — nie dało się ani przeczytać specyfikacji, ani wykonać żywego zapytania testowego. Dostępna pośrednio dokumentacja (nieoficjalne SDK, np. `github.com/migda/gugik-php-sdk`) pokrywa głównie geokodowanie działek (`GcReqDze`) i gmin (`GcReqJpa`) oraz odwrotne geokodowanie punktów adresowych (współrzędne→adres) — **nie znaleziono potwierdzonego endpointu "sprawdź czy ten pełny adres (ulica+numer+miasto) istnieje"**, mimo że opis usługi sugeruje taką obsługę.
- **Dlaczego to nie szkodzi**: `adresy.app` (już zintegrowane) jawnie deklaruje, że jego dane pochodzą z **tych samych** źródeł (PRG/GUGiK, TERYT/GUS, Poczta Polska) — to wrapper na tym samym rejestrze, z czytelnym, przetestowanym API. Budowanie równoległej integracji z CAPAP przy niedostępnej dokumentacji i braku możliwości weryfikacji na żywo powtórzyłoby dokładnie ten sam typ błędu, co pułapka `"matched"`/`"found"` opisana wyżej — tym razem bez możliwości złapania go przed wdrożeniem.
- **Kiedy warto wrócić do tematu**: jeśli ktoś ręcznie (z innej sieci/przeglądarki, gdzie strona nie jest zablokowana) pobierze i wklei treść `https://capap.gugik.gov.pl/api/fts/` — wtedy można ponownie ocenić, czy jest tam endpoint pokrywający nasz przypadek użycia, i zaimplementować dopiero po potwierdzeniu prawdziwego kształtu odpowiedzi.
