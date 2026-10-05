# Foldery vaultu Obsidiana synchronizowane do Lenie

Które podfoldery vaultu worker importuje jako dokumenty `obsidian_note`
(skan dobowy, job pojedynczej notatki i watcher inotify), określa klucz
`OBSIDIAN_SYNC_SUBFOLDERS` w Vault. Dodanie folderu nie wymaga zmiany kodu ani
deployu obrazu — tylko zmiany klucza i restartu workera.

## Format

Tekst JSON (lista obiektów):

```json
[
  {"path": "02-wiedza/Informatyka", "is_private": false},
  {"path": "02-wiedza/Geopolityka i polityka", "is_private": false},
  {"path": "02-wiedza/Architektura i urbanistyka", "is_private": false},
  {"path": "Journal", "is_private": true}
]
```

Reguły (parser: `backend/library/obsidian_sync_config.py`):

- `path` — ścieżka względem vaultu, separator `/`; bez ścieżek bezwzględnych,
  `..`, `.` i backslashy.
- `is_private` — opcjonalne, **domyślnie `true`**; akceptowane tylko `true`/`false`.
  `Journal` i wszystko pod nim nie może być publiczne.
- Wpisy nie mogą się powtarzać ani zagnieżdżać (jedna notatka nie może mieć dwóch
  różnych flag prywatności).
- `[]` wyłącza synchronizację. Pusty tekst, błędny JSON, nieznane pola lub zły wpis
  **przerywają job** (`obsidian_reimport` kończy się błędem), a watcher się nie
  uruchamia — bez fallbacku, żeby literówka nie zmieniła cicho zakresu importu.
- Pliki będące symlinkiem (lub leżące za symlinkiem) są pomijane.
- Brak klucza = przejściowy fallback do wbudowanej listy (`PILOT_SUBFOLDERS`
  w `obsidian_reimport_service.py`) z ostrzeżeniem w logu.

## Dodanie folderu

1. Dopisz wpis w kluczu w Vault.
2. Zrestartuj/odtwórz worker (konfiguracja jest czytana raz na proces; watcher
   ma stałą listę watchy inotify).
3. Nowy, duży folder importuj partiami według
   [obsidian-batch-backfill.md](obsidian-batch-backfill.md) — najbliższy skan dobowy
   sam przetworzy cały folder.

## Pułapki

- Usunięcie folderu z listy **nie usuwa** już zaimportowanych dokumentów ani
  embeddingów; przestają tylko być aktualizowane.
- Flaga `is_private` jest stosowana przy imporcie notatki (skan dobowy robi to też
  dla niezmienionych). Zmiana publiczne → prywatne wymaga skanu (lub ręcznej
  aktualizacji `documents.is_private`), nie działa natychmiast.
- Folder, który nie istniał przy starcie workera, nie dostaje watcha po późniejszym
  utworzeniu — potrzebny restart (skan dobowy go obejmie).
