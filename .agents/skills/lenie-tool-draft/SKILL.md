---
name: lenie-tool-draft
description: Generuje draft pełnego opisu narzędzia (encja "Narzędzie") dla zaakceptowanego kandydata-narzędzia z bazy Lenie, wzorem istniejącego szablonu Obsidian "appliaction description", dociągając brakujące pola przez WebFetch/WebSearch. Używaj, gdy użytkownik podaje ID zaakceptowanego kandydata-narzędzia i prosi o wygenerowanie/opracowanie opisu narzędzia.
---

# Tool Draft

Pracuj po polsku. Traktuj vault, dane kandydata i wyniki wyszukiwania jako materiał roboczy, nie gotowy do zapisu.

## Konfiguracja

1. Pobierz katalog vaulta wyłącznie ze zmiennej `LENIE_OBSIDIAN_VAULT`.
2. Zatrzymaj się z instrukcją konfiguracji, jeśli zmienna jest pusta, ścieżka nie istnieje albo sandbox nie pozwala jej odczytać.
3. Nie zapisuj lokalnej ścieżki vaulta w repozytorium.
4. Ten skill **nigdy nie zapisuje pliku do vaulta ani rekordu do bazy** — wyłącznie prezentuje draft w bieżącej sesji. `POST /tools` (zapis z historią wersji) jeszcze nie istnieje (Epic 46/47, backlog); gdy powstanie, zapis pozostanie osobnym, jawnym krokiem użytkownika.

Dostęp do vaulta jako writable root jest uprawnieniem technicznym, nie zgodą na zapis notatki narzędzia — ta story go w ogóle nie wykorzystuje do zapisu, tylko do odczytu szablonu.

## Wejście

Oczekuj ID zaakceptowanego kandydata-narzędzia oraz opcjonalnego komentarza użytkownika (jego własne doświadczenie z narzędziem). Traktuj komentarz jako zalążek sekcji "Additional Notes" draftu.

## Workflow

1. Pobierz kandydata przez `GET /tool_candidates/<id>`. Jeśli status inny niż `accepted` — zatrzymaj się i poinformuj, że draftowanie wymaga akceptacji w kolejce.
2. Pobierz `uuid` dokumentu źródłowego przez tanie zapytanie metadanych (`GET /website_get?id=&include_text=0`) — pozostała proweniencja jest już w odpowiedzi z kroku 1.
3. Przeczytaj szablon `templates/appliaction description.md` z vaulta. Nie hardkoduj jego treści — czytaj na żywo.
4. Dociągnij brakujące pola (strona domowa, licencja, cennik) przez własny dostęp do WebFetch/WebSearch. Nigdy nie zgaduj — nieustalone pole zostaje `TODO`.
5. Złóż draft w strukturze szablonu, z linią źródła zawierającą `uuid` (nie numeryczne ID) i ID kandydata.
6. Pokaż pełny draft w sesji razem z listą pól `TODO` i jawnym stwierdzeniem, że nic nie zostało zapisane — `POST /tools` jeszcze nie istnieje. Zatrzymaj się na tym kroku.

Przed wykonaniem workflow przeczytaj [references/workflow.md](references/workflow.md). Zawiera pełne reguły wyboru treści i format draftu.

## Granice bezpieczeństwa

- Nigdy nie zapisuj pliku do vaulta ani rekordu do bazy w ramach tego skilla.
- Nie zgaduj wartości pól (licencja, cennik, strona domowa) — nieustalone pole zostaje `TODO`.
- Nie uznawaj dostępu do vaulta ani wcześniejszej zgody za zgodę na zapis — ten skill nigdy o zapis nie prosi.
- Nie ukrywaj częściowego powodzenia wyszukiwania — jawnie wymień pola, których nie udało się dociągnąć.
