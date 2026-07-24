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

Ustal korzeń repozytorium przez `git rev-parse --show-toplevel`. Używaj interpretera `backend/.venv/Scripts/python.exe` oraz modułów projektu uruchamianych z katalogu `backend` tylko dla Kroku 6 (zapis do bazy) — odczyty w Kroku "Pobranie materiału" idą przez REST API backendu, nie przez ORM.

W PowerShell sprawdź konfigurację vaulta bez wypisywania prywatnej zawartości:

```powershell
if (-not $env:LENIE_OBSIDIAN_VAULT) { throw 'Brak LENIE_OBSIDIAN_VAULT' }
$vault = (Resolve-Path -LiteralPath $env:LENIE_OBSIDIAN_VAULT).Path
```

Każdą docelową ścieżkę rozwiąż względem `$vault` i odrzuć, jeśli wychodzi poza ten katalog. Nie stosuj twardo zakodowanej ścieżki profilu użytkownika.

Sprawdź też, że serwisowy klucz API jest ustawiony:

```powershell
if (-not $env:LENIE_API_KEY) { throw 'Brak LENIE_API_KEY' }
```

Jeśli zmienna jest pusta, zatrzymaj się z instrukcją konfiguracji — nie wpisuj klucza wprost do poleceń ani do plików repozytorium.

## Pobranie materiału

Wszystkie poniższe wywołania idą do backendu REST na NAS (`http://192.168.200.7:5055`) z nagłówkiem `x-api-key` ustawionym na `$env:LENIE_API_KEY`. `Invoke-RestMethod` sam parsuje odpowiedź JSON.

Najpierw pobierz metadane:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<ARTICLE_ID>&include_text=0" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Zwraca m.in. `id`, `uuid`, `title`, `url`, `ingested_at`, `processing_status`, `document_type`, `language`, `source`, `byline`, `note`, `summary`, `reviewed_at`, `tags`, `obsidian_note_paths`, `chapter_list`, `video_description`, `text_length` — pole `text`/`text_raw`/`text_md` jest pominięte przy `include_text=0`.

Następnie sprawdź wszystkie runy analizy dla dokumentu:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_runs?doc_id=<ARTICLE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Zwraca `{"doc_id", "runs": [{"id", "mode", "status", "scope", "model", "created_at", "chunk_count", "temat_count", "analyzed_count", "approved_count", "workflow_stage"}, ...]}` — identyfikator runu to pole `id`.

- Brak runów: przejdź do pełnego tekstu.
- Jeden użyteczny run: wybierz go.
- Wiele runów: pokaż identyfikator, tryb, zakres, model, datę i liczniki. Zaproponuj run z największą liczbą przeanalizowanych chunków; remis rozstrzygnij liczbą `approved`.
- Run bez przeanalizowanych chunków traktuj jako niegotowy do pisania notatek.

Pełny tekst pobieraj tylko wtedy, gdy brak użytecznych chunków:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<ARTICLE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

(`include_text` pominięte — domyślnie `1`, więc odpowiedź zawiera też `text`/`text_raw`/`text_md`.) Użyj `text` jako treści artykułu; jeśli jest puste (stan surowy, jeszcze nieoczyszczony), sięgnij po `text_raw`.

Dla `webpage`, `link` lub podobnego typu ze stanem `URL_ADDED` albo `DOCUMENT_INTO_DATABASE` ostrzeż o surowym, zaszumionym tekście i zaczekaj na zgodę. Dla `youtube` lub `movie` zatrzymaj się, jeśli brak transkrypcji.

## Wybór treści

Dla wybranego runu pobierz chunki (nagłówek `x-api-key` jak wyżej):

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_run/<RUN_ID>/chunks?lite=1" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Zwraca `chunks: [{"position", "type", "status", "topic", "summary", "obsidian_note_paths"}, ...]` (niefiltrowane po typie — odfiltruj `type == "TEMAT"` sam) oraz `topic_sections: [{"id", "position", "title", "chunk_positions", "temat_count", "approved_count", "notes_count"}, ...]`. Pełny tekst wybranych pozycji pobierz osobno:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/analysis_run/<RUN_ID>/chunks?positions=<pozycje_po_przecinku>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Każdy element zwraca `position`, `topic`, `status`, `original_text`, `corrected_text` — wybierz pole tekstu wg reguł niżej.

Pokaż najpierw już opracowane lub pominięte, a potem nieopracowane. Nie mieszaj `REKLAMA` i `SZUM` z materiałem do notatek.

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
