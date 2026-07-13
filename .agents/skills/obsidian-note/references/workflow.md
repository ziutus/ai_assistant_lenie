# Workflow Lenie → Obsidian

## Spis treści

- [Środowisko](#środowisko)
- [Pobranie materiału](#pobranie-materiału)
- [Wybór treści](#wybór-treści)
- [Praca z vaultem](#praca-z-vaultem)
- [Pakiet zmian](#pakiet-zmian)
- [Synchronizacja bazy](#synchronizacja-bazy)
- [Raport](#raport)

## Środowisko

Ustal korzeń repozytorium przez `git rev-parse --show-toplevel`. Używaj interpretera `backend/.venv/Scripts/python.exe` oraz modułów projektu uruchamianych z katalogu `backend`.

W PowerShell sprawdź konfigurację vaulta bez wypisywania prywatnej zawartości:

```powershell
if (-not $env:LENIE_OBSIDIAN_VAULT) { throw 'Brak LENIE_OBSIDIAN_VAULT' }
$vault = (Resolve-Path -LiteralPath $env:LENIE_OBSIDIAN_VAULT).Path
```

Każdą docelową ścieżkę rozwiąż względem `$vault` i odrzuć, jeśli wychodzi poza ten katalog. Nie stosuj twardo zakodowanej ścieżki profilu użytkownika.

## Pobranie materiału

Najpierw pobierz metadane:

```powershell
Set-Location (Join-Path (git rev-parse --show-toplevel) 'backend')
.\.venv\Scripts\python.exe imports\article_browser.py --meta --id <ARTICLE_ID>
```

Sprawdź wszystkie `DocumentAnalysisRun` dla `document_id`, od najnowszego, wraz z liczbą chunków `TEMAT`, przeanalizowanych chunków z `topic` i chunków `approved`.

- Brak runów: przejdź do pełnego tekstu.
- Jeden użyteczny run: wybierz go.
- Wiele runów: pokaż identyfikator, tryb, zakres, model, datę i liczniki. Zaproponuj run z największą liczbą przeanalizowanych chunków; remis rozstrzygnij liczbą `approved`.
- Run bez przeanalizowanych chunków traktuj jako niegotowy do pisania notatek.

Pełny tekst pobieraj tylko wtedy, gdy brak użytecznych chunków:

```powershell
.\.venv\Scripts\python.exe imports\article_browser.py --dump --id <ARTICLE_ID>
```

Dla `webpage`, `link` lub podobnego typu ze stanem `URL_ADDED` albo `DOCUMENT_INTO_DATABASE` ostrzeż o surowym, zaszumionym tekście i zaczekaj na zgodę. Dla `youtube` lub `movie` zatrzymaj się, jeśli brak transkrypcji.

## Wybór treści

Dla wybranego runu pobierz chunki `TEMAT` w kolejności `position`. Pokaż najpierw już opracowane lub pominięte, a potem nieopracowane. Nie mieszaj `REKLAMA` i `SZUM` z materiałem do notatek.

- Dla maksymalnie 30 chunków pokaż płaską listę.
- Dla większego runu pogrupuj przez `DocumentTopicSection`; uwzględnij również chunki nieprzypisane do sekcji.
- Zaproponuj nieopracowane chunki jako domyślny zakres i pozwól użytkownikowi wybrać numery lub sekcje.
- Dla `mode=transcript` preferuj `corrected_text`, a potem `original_text`.
- Dla `mode=article` używaj `original_text`; brak `corrected_text` jest oczekiwany.
- Dla statusu `pending` lub `needs_reanalysis` ostrzeż i poproś o decyzję przed użyciem treści.
- Długi materiał bez chunków podziel na 4–8 tematów i opracowuj wybrane części, nie jedną zbiorczą notatkę.

## Praca z vaultem

Zacznij od `02-wiedza/_index.md` wewnątrz vaulta. Dopasuj temat i słowa kluczowe, a następnie przeczytaj najwyżej 1–2 najbardziej trafne notatki. Użyj wyszukiwania po całym vaulcie dopiero, gdy indeks nie daje wyniku i użytkownik potrzebuje szerszej analizy.

Notatka powinna zawierać:

- frontmatter z tagami `wiedza/...`;
- jeden nagłówek H1 i logiczne sekcje H2;
- wiki-linki Obsidian do istniejących pojęć;
- wątki finansowe lub jawne `TODO: wątek finansowy`;
- źródło z tytułem, URL-em i UUID Lenie, nie numerycznym ID;
- dla materiału chunkowego także numer i temat chunka.

Aktualizuj indeks tylko dla nowego pliku lub tematu, którego indeks jeszcze nie obejmuje. Dodawaj cross-reference tylko wtedy, gdy wynika z treści zatwierdzonego pakietu.

## Pakiet zmian

Przed zapisem pokaż:

1. listę nowych i zmienianych plików;
2. pełną propozycję treści nowych notatek oraz istotne fragmenty zmian istniejących;
3. plan zmian indeksu i cross-reference;
4. `WebDocument` oraz chunki przeznaczone do synchronizacji;
5. informację, że zgoda obejmie cały wymieniony pakiet.

Jedno potwierdzenie wystarcza dla wszystkich wymienionych notatek i odpowiadających im aktualizacji bazy. Nowy plik, dodatkowy cross-reference albo dodatkowy rekord bazy wykracza poza pakiet i wymaga ponownego potwierdzenia.

## Synchronizacja bazy

Wykonaj ją dopiero po skutecznym zapisie plików:

- dodaj względne ścieżki notatek do `WebDocument.obsidian_note_paths` bez duplikatów;
- ustaw `reviewed_at` tylko jeśli nie było ustawione;
- dla każdego użytego chunka dodaj ścieżki do `DocumentChunk.obsidian_note_paths` bez duplikatów;
- ustaw status chunka na `approved` tylko po zapisaniu odpowiadającej notatki;
- wykonaj zmiany w jednej transakcji bazy i wycofaj ją przy błędzie;
- nie cofaj automatycznie poprawnie zapisanych plików; zgłoś rozbieżność i zaproponuj naprawę.

## Raport

Po operacji pokaż:

- zapisane i zmienione względne ścieżki notatek;
- zmianę indeksu i cross-reference;
- UUID dokumentu, `reviewed_at` i zapisane ścieżki dokumentu;
- pozycje chunków, ich statusy i ścieżki;
- wszelkie niewykonane kroki, bez przedstawiania częściowego wyniku jako pełnego sukcesu.
