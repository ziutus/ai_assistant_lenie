# Workflow Kandydat → Draft narzędzia

## Spis treści

- [Środowisko](#środowisko)
- [Pobranie kandydata](#pobranie-kandydata)
- [Szablon i dociąganie pól](#szablon-i-dociąganie-pól)
- [Pakiet draftu](#pakiet-draftu)
- [Raport](#raport)

## Środowisko

W PowerShell sprawdź konfigurację vaulta bez wypisywania prywatnej zawartości:

```powershell
if (-not $env:LENIE_OBSIDIAN_VAULT) { throw 'Brak LENIE_OBSIDIAN_VAULT' }
$vault = (Resolve-Path -LiteralPath $env:LENIE_OBSIDIAN_VAULT).Path
```

Sprawdź też, że serwisowy klucz API jest ustawiony:

```powershell
if (-not $env:LENIE_API_KEY) { throw 'Brak LENIE_API_KEY' }
```

Jeśli którakolwiek zmienna jest pusta, zatrzymaj się z instrukcją konfiguracji — nie wpisuj klucza ani ścieżki wprost do poleceń ani do plików repozytorium.

## Pobranie kandydata

Wywołania idą do backendu REST na NAS (`http://192.168.200.7:5055`) z nagłówkiem `x-api-key` ustawionym na `$env:LENIE_API_KEY`.

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/tool_candidates/<CANDIDATE_ID>" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Odpowiedź pod kluczem `tool_candidate`: `id`, `name`, `status`, `context_snippet`, `detected_by`, `source_document_id`, `source_document` (proweniencja: `title`/`url`/`byline`/`discovery_source`/`published_on`/`ingested_at`, ale **bez** `uuid`).

Jeśli `status` inny niż `accepted` — zatrzymaj się. Draftowanie dotyczy wyłącznie zaakceptowanych kandydatów; nie kontynuuj do kolejnych kroków.

Dociągnij `uuid` dokumentu źródłowego (potrzebny do linii źródła, nie numeryczne `id`) jednym tanim wywołaniem:

```powershell
Invoke-RestMethod -Uri "http://192.168.200.7:5055/website_get?id=<source_document_id>&include_text=0" -Headers @{"x-api-key"=$env:LENIE_API_KEY}
```

Reszta proweniencji jest już w odpowiedzi pierwszego wywołania — nie duplikuj po nią zapytania.

## Szablon i dociąganie pól

Przeczytaj `templates/appliaction description.md` wewnątrz `$vault` (literówka w nazwie pliku jest celowa i pre-istniejąca — nie poprawiaj jej). Pola: `Purpose`, `Type of application`, `Licence`, `homepage`, `wikipedia page`, `github page`, `Pricing type`, `pricing page`, sekcje `### Key Points`, `### Important Commands`, `### Additional Notes`. Sekcja `## Source of note` w oryginale korzysta ze składni Templater (`tp.file.creation_date()`) działającej tylko wewnątrz samego Obsidiana — pomiń ją w draftcie zamiast próbować ją emulować.

Dociągnij brakujące pola (homepage, licencja, cennik, opcjonalnie wikipedia/github) przez WebFetch/WebSearch po nazwie kandydata i `context_snippet`. Nigdy nie zgaduj — nieustalone pole zostaje `TODO`, użytkownik uzupełni je przy edycji.

## Pakiet draftu

Draft powinien zawierać:

- frontmatter dokładnie `tags: [wiedza/informatyka]` z szablonu — bez hierarchicznych tagów `narzędzia/<slug>` (to `category_tags` przyszłej encji `Tool` w bazie, Epic 46, osobny mechanizm od frontmatter markdown);
- wypełnione pola szablonu lub jawne `TODO`;
- `### Additional Notes` = komentarz użytkownika (jeśli podany przy wywołaniu), inaczej pusty;
- linię źródła: `Źródło: [tytuł](url) (Lenie AI uuid=<uuid>, tool candidate id=<id>)`.

Pokaż cały draft w sesji jako gotowy do skopiowania markdown, razem z listą pól `TODO`, i jawnie stwierdź, że nic nie zostało zapisane — `POST /tools` (zapis z historią wersji) jeszcze nie istnieje. Nie zapisuj pliku do vaulta ani rekordu do bazy w żadnym wypadku — to jest ostatni krok, nie punkt pośredni do dalszego zapisu.

## Raport

Po prezentacji draftu podsumuj:

- ID kandydata i nazwę narzędzia;
- które pola zostały dociągnięte automatycznie, a które są `TODO`;
- że sesja kończy się na prezentacji — brak zapisu pliku/bazy.
