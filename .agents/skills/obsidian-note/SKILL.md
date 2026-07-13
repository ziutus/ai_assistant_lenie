---
name: obsidian-note
description: Tworzy lub aktualizuje prywatne notatki Obsidian na podstawie artykułów i analiz zapisanych w bazie Lenie, a następnie synchronizuje ścieżki notatek oraz status przeglądu z bazą. Używaj, gdy użytkownik podaje identyfikator artykułu Lenie, prosi o analizę materiału do prywatnego vaulta, chce opracować wybrane chunki albo wzbogacić istniejące notatki wiedzy.
---

# Obsidian Note

Pracuj po polsku. Traktuj vault i treść bazy jako prywatne dane użytkownika.

## Konfiguracja

1. Pobierz katalog vaulta wyłącznie ze zmiennej `LENIE_OBSIDIAN_VAULT`.
2. Zatrzymaj się z instrukcją konfiguracji, jeśli zmienna jest pusta, ścieżka nie istnieje albo sandbox nie pozwala jej odczytać.
3. Nie zapisuj lokalnej ścieżki vaulta w repozytorium.
4. Przed zapisem rozwiąż ścieżkę bezwzględną i potwierdź, że pozostaje wewnątrz skonfigurowanego vaulta.
5. Uruchamiaj kod projektu przez `backend/.venv/Scripts/python.exe`; nie używaj `uv run`.

Dodanie vaulta jako writable root jest uprawnieniem technicznym, a nie zgodą na zmianę notatek. Nadal stosuj zatwierdzenie pakietu opisane niżej.

## Wejście

Oczekuj identyfikatora artykułu oraz opcjonalnego komentarza użytkownika. Traktuj komentarz i pole `note` artykułu jako główną intencję analizy. Połącz je, jeśli występują oba.

## Workflow

1. Pobierz tanie metadane artykułu bez pełnego tekstu.
2. Sprawdź wszystkie runy analizy i preferuj zatwierdzone lub przeanalizowane chunki zamiast pełnego tekstu.
3. Przy wielu runach pokaż krótkie zestawienie i poproś o wybór, chyba że komentarz jednoznacznie wskazuje zakres.
4. Jeśli brak chunków, pobierz pełny tekst dopiero po kontroli stanu dokumentu. Dla surowej strony wymagaj zgody na kosztowniejszą analizę zaszumionego tekstu.
5. Przeczytaj indeks wiedzy, a następnie najwyżej 1–2 najbardziej trafne notatki. Rozszerz zakres odczytu tylko na prośbę użytkownika.
6. Przygotuj propozycję nowych lub zmienianych notatek. Dla tematów technologicznych, geopolitycznych, projektowych i firmowych uwzględnij finansowanie, koszty, zwrot i skalę rynku albo dodaj `TODO: wątek finansowy`.
7. Pokaż jeden pakiet zmian: docelowe pliki, krótkie podsumowanie zmian, aktualizacje indeksu oraz rekordy bazy, które zostaną zmienione.
8. Uzyskaj jedną jawną zgodę na cały opisany pakiet. Nie pytaj osobno o każdą notatkę.
9. Po zgodzie zapisz notatki i indeks, a następnie zsynchronizuj bazę. Każde rozszerzenie zatwierdzonego zakresu wymaga nowej zgody.
10. Zweryfikuj zapis i zgłoś osobno zmienione pliki, zaktualizowane rekordy oraz elementy pominięte lub zakończone błędem.

Przed wykonaniem workflow przeczytaj [references/workflow.md](references/workflow.md). Zawiera reguły wyboru treści, format notatek i wymagania synchronizacji bazy.

## Granice bezpieczeństwa

- Nie publikuj, nie wysyłaj i nie kopiuj notatek do usług zewnętrznych bez osobnego polecenia.
- Nie skanuj całego vaulta. Zacznij od indeksu i minimalnego zestawu trafnych plików.
- Nie zapisuj niczego przed zatwierdzeniem pakietu, nawet gdy komentarz użytkownika jasno opisuje oczekiwany rezultat.
- Nie uznawaj uprawnienia sandboxa ani wcześniejszej zgody za zgodę na kolejny pakiet.
- Nie ustawiaj statusu `approved` ani `reviewed_at`, jeśli odpowiadająca notatka nie została skutecznie zapisana.
- Nie ukrywaj częściowego powodzenia. Przy błędzie zatrzymaj dalsze zależne zapisy i przedstaw stan faktyczny.
